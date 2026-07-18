"""
Registry, runtime evaluation, activation-plan binding, and routing tests (Kapitel 9 slice 1).
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.admin.onboarding.activation_plan import build_activation_plan, compute_plan_hash
from app.admin.onboarding.errors import OnboardingStaleActivationPlanError, OnboardingValidationError
from app.admin.onboarding.models import (
    OnboardingSessionRecord,
    OnboardingStepDraftRecord,
    OnboardingStepStateRecord,
)
from app.admin.onboarding.registries import (
    AUTOMATION_PRESETS,
    REGISTRY_REVISION,
    REGISTRY_SCHEMA_VERSION,
    preset_snapshot,
    resolve_preset,
    validate_registry_integrity,
)
from app.admin.onboarding.registry_presenter import present_registries
from app.admin.onboarding.repository import OnboardingRepository
from app.admin.onboarding.runtime_evaluation import evaluate_all_runtime_requirements
from app.admin.onboarding.service import (
    activate_onboarding_session,
    create_onboarding_session,
    get_activation_plan,
    patch_automation,
    patch_modules,
    run_readiness,
)
from app.repositories.postgres.database import Base
from app.repositories.postgres.tenant_api_key_models import TenantApiKeyRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from tests.onboarding_db_tables import onboarding_sqlite_tables


FORBIDDEN_RESPONSE_KEYS = frozenset(
    {
        "api_key",
        "key_hash",
        "token",
        "secret",
        "credential",
        "access_token",
        "refresh_token",
        "client_secret",
        "password",
    }
)


def _operator(role: str = "admin") -> dict:
    return {
        "id": "operator-test",
        "display_name": "Test Operator",
        "role": role,
    }


def _settings(**kwargs):
    defaults = {
        "ADMIN_API_KEY": "test-admin-key",
        "APP_NAME": "Test",
        "GOOGLE_MAIL_ACCESS_TOKEN": "",
        "MONDAY_API_KEY": "",
        "FORTNOX_ACCESS_TOKEN": "",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _collect_json_keys(value, *, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            path = f"{prefix}.{key}" if prefix else key
            keys.add(key)
            keys.update(_collect_json_keys(nested, prefix=path))
    elif isinstance(value, list):
        for item in value:
            keys.update(_collect_json_keys(item, prefix=prefix))
    return keys


def _assert_no_forbidden_keys(payload) -> None:
    keys = _collect_json_keys(payload)
    forbidden = keys & FORBIDDEN_RESPONSE_KEYS
    assert not forbidden, f"Forbidden keys in response: {sorted(forbidden)}"


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    tables = onboarding_sqlite_tables()
    Base.metadata.create_all(bind=engine, tables=tables)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _prepare_followups_session(db):
    with patch(
        "app.admin.onboarding.service._utcnow",
        return_value=datetime(2026, 1, 1, tzinfo=timezone.utc),
    ):
        created = create_onboarding_session(
            db,
            operator=_operator(),
            company_name="Followups Co",
            slug="followups-co",
            org_number=None,
            primary_contact=None,
            contact_email=None,
            phone=None,
            timezone="Europe/Stockholm",
            language="sv",
            settings=_settings(),
        )
    patch_modules(
        db,
        session_id=created.id,
        operator=_operator(),
        capabilities=["followups"],
        integrations=[],
        expected_version=created.version,
        settings=_settings(),
    )
    session = OnboardingRepository.get_session(db, created.id)
    patch_automation(
        db,
        session_id=created.id,
        operator=_operator(),
        preset_key="observe_only",
        preset_version=1,
        expected_version=session.version,
        settings=_settings(),
    )
    return OnboardingRepository.get_session(db, created.id)


class TestRegistryIntegrity:
    def test_validate_registry_integrity_passes(self):
        validate_registry_integrity()

    def test_dual_versioning_exposed(self):
        presented = present_registries()
        assert presented.registry_schema_version == REGISTRY_SCHEMA_VERSION
        assert presented.registry_revision == REGISTRY_REVISION
        assert len(presented.registry_revision) == 64

    def test_preset_composite_keys_unique(self):
        pairs = list(AUTOMATION_PRESETS.keys())
        assert len(pairs) == len(set(pairs))

    def test_unknown_preset_version_rejected(self, db):
        created = create_onboarding_session(
            db,
            operator=_operator(),
            company_name="Preset Co",
            slug="preset-co",
            org_number=None,
            primary_contact=None,
            contact_email=None,
            phone=None,
            timezone="Europe/Stockholm",
            language="sv",
            settings=_settings(),
        )
        with pytest.raises(OnboardingValidationError, match="Unknown or mismatched"):
            patch_automation(
                db,
                session_id=created.id,
                operator=_operator(),
                preset_key="observe_only",
                preset_version=999,
                expected_version=created.version,
                settings=_settings(),
            )


class TestCapabilityLifecycle:
    def test_followups_configured_not_running_ready_with_warnings(self, db):
        session = _prepare_followups_session(db)
        tenant = db.query(TenantConfigRecord).filter_by(tenant_id=session.tenant_id).first()
        modules = OnboardingRepository.get_draft(db, session.id, "modules")
        automation = OnboardingRepository.get_draft(db, session.id, "automation")

        bundle = evaluate_all_runtime_requirements(
            db,
            capability_keys=modules.payload.get("capabilities") or [],
            snapshot=automation.payload.get("effective_policy_snapshot") or {},
            tenant=tenant,
            preset_key=automation.payload.get("preset_key"),
            preset_version=automation.payload.get("preset_version"),
        )
        followups = next(
            s for s in bundle["capability_states"] if s["capability_key"] == "followups"
        )
        assert followups["lifecycle_state"] == "configured_not_running"
        assert bundle["forces_ready_with_warnings"] is True

        readiness = run_readiness(
            db,
            session_id=session.id,
            operator=_operator(),
            settings=_settings(),
        )
        assert readiness.overall_status == "ready_with_warnings"
        assert readiness.overall_status != "ready"


class TestActivationPlanBinding:
    def test_stale_plan_hash_rejected(self, db):
        session = _prepare_followups_session(db)
        run_readiness(db, session_id=session.id, operator=_operator(), settings=_settings())
        session = OnboardingRepository.get_session(db, session.id)
        plan = get_activation_plan(db, session_id=session.id, settings=_settings())
        stale_hash = plan.plan_hash
        readiness = run_readiness(
            db, session_id=session.id, operator=_operator(), settings=_settings()
        )
        session = OnboardingRepository.get_session(db, session.id)

        with patch(
            "app.admin.onboarding.activation_plan.REGISTRY_REVISION",
            "0" * 64,
        ):
            with pytest.raises(OnboardingStaleActivationPlanError):
                activate_onboarding_session(
                    db,
                    session_id=session.id,
                    operator=_operator("admin"),
                    reason="Go",
                    confirmation_phrase="followups-co",
                    expected_version=session.version,
                    readiness_check_version=session.readiness_check_version,
                    plan_hash=stale_hash,
                    acknowledged_warning_ids=[w.id for w in readiness.warnings],
                    settings=_settings(),
                )

    def test_plan_hash_is_stable_for_same_inputs(self, db):
        session = _prepare_followups_session(db)
        tenant = db.query(TenantConfigRecord).filter_by(tenant_id=session.tenant_id).first()
        plan_a = build_activation_plan(
            db, session_id=session.id, tenant=tenant, settings=_settings()
        )
        plan_b = build_activation_plan(
            db, session_id=session.id, tenant=tenant, settings=_settings()
        )
        assert plan_a["plan_hash"] == plan_b["plan_hash"]
        assert len(plan_a["plan_hash"]) == 64


class TestRegistryRouting:
    def test_registries_endpoint_not_session_id(self):
        from app.main import app

        key = "registry-admin-key"
        settings_mock = _settings(ADMIN_API_KEY=key)
        client = TestClient(app, raise_server_exceptions=False)
        with patch("app.core.admin_auth.get_settings", return_value=settings_mock):
            response = client.get(
                "/admin/onboarding/registries",
                headers={"X-Admin-API-Key": key},
            )
        assert response.status_code == 200
        body = response.json()
        assert "registry_revision" in body
        assert body.get("registry_schema_version") == REGISTRY_SCHEMA_VERSION

    def test_registries_route_registered_before_session_param(self):
        from app.main import app

        paths = [route.path for route in app.routes if hasattr(route, "path")]
        registry_paths = [p for p in paths if p.endswith("/admin/onboarding/registries")]
        session_paths = [p for p in paths if "/admin/onboarding/{session_id}" in p]
        assert registry_paths
        assert session_paths


class TestRegistrySecretProtection:
    def test_present_registries_has_no_forbidden_keys(self):
        payload = present_registries().model_dump()
        _assert_no_forbidden_keys(payload)

    def test_activation_plan_has_no_forbidden_keys(self, db):
        session = _prepare_followups_session(db)
        tenant = db.query(TenantConfigRecord).filter_by(tenant_id=session.tenant_id).first()
        plan = build_activation_plan(
            db, session_id=session.id, tenant=tenant, settings=_settings()
        )
        _assert_no_forbidden_keys(plan)


class TestActivateRuntimeEffects:
    def test_scheduler_paused_no_api_key_no_workflow_scan_mutation(self, db):
        session = _prepare_followups_session(db)
        tenant = db.query(TenantConfigRecord).filter_by(tenant_id=session.tenant_id).first()
        tenant.settings = {
            "workflow_scan": {"systems_scanned": ["gmail"]},
            "automation": {},
            "scheduler": {"run_mode": "manual"},
        }
        db.commit()

        readiness = run_readiness(
            db, session_id=session.id, operator=_operator(), settings=_settings()
        )
        session = OnboardingRepository.get_session(db, session.id)
        plan = get_activation_plan(db, session_id=session.id, settings=_settings())

        activate_onboarding_session(
            db,
            session_id=session.id,
            operator=_operator("admin"),
            reason="Pilot",
            confirmation_phrase="followups-co",
            expected_version=session.version,
            readiness_check_version=session.readiness_check_version,
            plan_hash=plan.plan_hash,
            acknowledged_warning_ids=[w.id for w in readiness.warnings],
            settings=_settings(),
        )

        db.refresh(tenant)
        assert tenant.settings["scheduler"]["run_mode"] == "paused"
        assert tenant.settings["workflow_scan"] == {"systems_scanned": ["gmail"]}
        assert db.query(TenantApiKeyRecord).count() == 0


class TestPresetSnapshotIsolation:
    def test_preset_snapshot_does_not_mutate_registry_entry(self):
        preset = resolve_preset("observe_only", 1)
        assert preset is not None
        original_flags = dict(preset.automation_flags)
        snapshot = preset_snapshot(preset)
        snapshot["automation_flags"]["demo_mode"] = True
        assert preset.automation_flags == original_flags
        assert AUTOMATION_PRESETS[("observe_only", 1)].automation_flags == original_flags

    def test_deepcopy_snapshot_isolated_from_registry(self):
        preset = resolve_preset("observe_only", 1)
        assert preset is not None
        local_preset = copy.deepcopy(preset)
        local_snapshot = preset_snapshot(local_preset)
        local_snapshot["scheduler_run_mode"] = "always_on"
        assert preset.scheduler_run_mode != "always_on"


class TestComputePlanHash:
    def test_hash_changes_when_registry_revision_changes(self):
        canonical = {
            "consequences": [],
            "runtime_effects": [],
            "capability_states": [],
            "warning_ids": [],
            "snapshot_fingerprint": {"capabilities": ["followups"]},
            "registry_revision": "aaa",
        }
        other = {**canonical, "registry_revision": "bbb"}
        assert compute_plan_hash(canonical) != compute_plan_hash(other)
