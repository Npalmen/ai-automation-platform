"""
Tests for operator onboarding Slice 2A (service profile, routing, data start).
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.admin.onboarding.activation_plan import build_activation_plan, compute_plan_hash
from app.admin.onboarding.draft_schemas import (
    DataStartPatchRequest,
    RoutingPatchRequest,
    ServiceProfilePatchRequest,
)
from app.admin.onboarding.effective_config import materialize_lead_config, materialize_slice2a_config
from app.admin.onboarding.models import (
    OnboardingSessionRecord,
    OnboardingStepDraftRecord,
    OnboardingStepStateRecord,
)
from app.admin.onboarding.registry_presenter import present_registries
from app.admin.onboarding.repository import OnboardingRepository
from app.admin.onboarding.service import (
    activate_onboarding_session,
    create_onboarding_session,
    get_activation_plan,
    patch_automation,
    patch_modules,
    run_readiness,
)
from app.admin.onboarding.slice2a_service import (
    get_routing_step,
    patch_data_start_step,
    patch_routing_step,
    patch_service_profile_step,
)
from app.lead.tenant_context import load_tenant_context
from tests.onboarding_db_tables import onboarding_sqlite_tables
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.database import Base
from app.repositories.postgres.tenant_api_key_models import TenantApiKeyRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from app.service_profiles.qualification import apply_tenant_overrides
from app.service_profiles.registry import get_profile


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


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    tables = onboarding_sqlite_tables()
    Base.metadata.create_all(bind=engine, tables=tables)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _advance_to_automation(db, capabilities=None):
    created = create_onboarding_session(
        db,
        operator=_operator(),
        company_name="Slice 2A Co",
        slug="slice-2a-co",
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
        capabilities=capabilities or ["lead_management"],
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


def _complete_slice2a(db, session_id: str, version: int):
    patch_service_profile_step(
        db,
        session_id=session_id,
        operator=_operator(),
        body=ServiceProfilePatchRequest(
            version=version,
            selected_profiles=["generic_lead"],
            lead_requirements={
                "generic_lead": {
                    "contact_name": "inherit",
                    "phone_or_email": "required",
                }
            },
        ),
        settings=_settings(),
    )
    session = OnboardingRepository.get_session(db, session_id)
    patch_routing_step(
        db,
        session_id=session_id,
        operator=_operator(),
        body=RoutingPatchRequest(
            version=session.version,
            route_overrides={"generic_lead": "sales"},
        ),
        settings=_settings(),
    )
    session = OnboardingRepository.get_session(db, session_id)
    patch_data_start_step(
        db,
        session_id=session_id,
        operator=_operator(),
        body=DataStartPatchRequest(version=session.version, mode="new_incoming_only"),
        settings=_settings(),
    )
    return OnboardingRepository.get_session(db, session_id)


class TestSlice2aRegistries:
    def test_registries_include_slice2a_sections(self):
        reg = present_registries()
        assert reg.registry_schema_version >= 2
        assert len(reg.service_profiles) > 0
        assert len(reg.lead_field_registry) > 0
        assert len(reg.routing_destinations) >= 4
        assert any(m.key == "new_incoming_only" for m in reg.data_start_modes)

    def test_session_route_does_not_duplicate_global_lists(self, db):
        session = _advance_to_automation(db)
        step = get_routing_step(db, session.id, settings=_settings())
        assert "service_profiles" not in step
        assert "routing_destinations" not in step
        assert "draft" in step
        assert "effective" in step


class TestSlice2aMaterialization:
    def test_inherit_stripped_from_lead_requirements(self):
        effective = {
            "valid": True,
            "profiles": [
                {
                    "service_type": "generic_lead",
                    "required_fields": ["phone_or_email", "contact_name", "address", "service_type"],
                    "optional_fields": ["notes", "installation_timeline"],
                }
            ],
        }
        lead_config = materialize_lead_config(effective)
        reqs = lead_config["lead_requirements"]["generic_lead"]
        assert "contact_name" in reqs["required"]
        assert "phone_or_email" in reqs["required"]
        assert "notes" in reqs["optional"]

    def test_materialize_writes_internal_routing_and_intake(self, db):
        session = _advance_to_automation(db)
        session = _complete_slice2a(db, session.id, session.version)
        modules = OnboardingRepository.get_draft(db, session.id, "modules")
        sp = OnboardingRepository.get_draft(db, session.id, "service_profile")
        routing = OnboardingRepository.get_draft(db, session.id, "routing")
        data_start = OnboardingRepository.get_draft(db, session.id, "data_start")
        tenant = db.query(TenantConfigRecord).filter_by(tenant_id=session.tenant_id).first()
        now = datetime(2026, 7, 17, tzinfo=timezone.utc)
        merged = materialize_slice2a_config(
            tenant.settings or {},
            modules_payload=modules.payload,
            sp_payload=sp.payload,
            routing_payload=routing.payload,
            data_start_payload=data_start.payload,
            activation_cutoff_at=now,
        )
        memory = merged["memory"]
        assert merged["schema_version"] == 2
        assert any(s.get("name") == "Generic Lead" for s in memory["lead_config"]["services"])
        assert memory["internal_routing_hints"]["generic_lead"] == "sales"
        assert merged["intake"]["mode"] == "new_incoming_only"
        assert merged["intake"]["enforcement"] == "metadata_only"
        assert merged["intake"]["activation_cutoff_at"] == now.isoformat()


class TestSlice2aReadiness:
    def test_lead_management_not_ready_without_integration(self, db):
        session = _advance_to_automation(db, capabilities=["lead_management"])
        session = _complete_slice2a(db, session.id, session.version)
        readiness = run_readiness(
            db, session_id=session.id, operator=_operator(), settings=_settings()
        )
        assert readiness.overall_status == "not_ready"
        passed_ids = {c.id for c in readiness.passed_checks}
        blocking_ids = {c.id for c in readiness.blocking_checks}
        assert "step.service_profile" in passed_ids
        assert "step.routing" in passed_ids
        assert "step.integrations" in blocking_ids or any(
            "integration" in c.id for c in readiness.blocking_checks
        )

    def test_followups_ready_with_warnings(self, db):
        session = _advance_to_automation(db, capabilities=["followups"])
        session = _complete_slice2a(db, session.id, session.version)
        readiness = run_readiness(
            db, session_id=session.id, operator=_operator(), settings=_settings()
        )
        assert readiness.overall_status == "ready_with_warnings"
        assert any(c.id == "data_start.runtime_enforcement" for c in readiness.passed_checks)


class TestSlice2aRoutingStep:
    def test_get_routing_does_not_create_step_state(self, db):
        session = _advance_to_automation(db)
        patch_service_profile_step(
            db,
            session_id=session.id,
            operator=_operator(),
            body=ServiceProfilePatchRequest(
                version=session.version,
                selected_profiles=["generic_lead"],
            ),
            settings=_settings(),
        )
        before = OnboardingRepository.get_step_states(db, session.id)
        routing_states = [s for s in before if s.step_key == "routing"]
        get_routing_step(db, session.id, settings=_settings())
        after = OnboardingRepository.get_step_states(db, session.id)
        routing_after = [s for s in after if s.step_key == "routing"]
        assert len(routing_states) == len(routing_after)

    def test_patch_routing_creates_step_state(self, db):
        session = _advance_to_automation(db)
        patch_service_profile_step(
            db,
            session_id=session.id,
            operator=_operator(),
            body=ServiceProfilePatchRequest(
                version=session.version,
                selected_profiles=["generic_lead"],
            ),
            settings=_settings(),
        )
        session = OnboardingRepository.get_session(db, session.id)
        patch_routing_step(
            db,
            session_id=session.id,
            operator=_operator(),
            body=RoutingPatchRequest(version=session.version, route_overrides={}),
            settings=_settings(),
        )
        states = OnboardingRepository.get_step_states(db, session.id)
        routing = next(s for s in states if s.step_key == "routing")
        assert routing.step_status == "completed"


class TestSlice2aPlanHash:
    def test_plan_hash_changes_with_slice2a_drafts(self, db):
        session = _advance_to_automation(db)
        plan1 = get_activation_plan(db, session_id=session.id, settings=_settings())
        session = _complete_slice2a(db, session.id, session.version)
        plan2 = get_activation_plan(db, session_id=session.id, settings=_settings())
        assert plan1.plan_hash != plan2.plan_hash


class TestRuntimeRoutingRead:
    def test_apply_tenant_overrides_prefers_internal_routing_hints(self):
        profile = get_profile("generic_lead")
        assert profile is not None
        ctx = load_tenant_context(
            "T_test",
            {
                "memory": {
                    "internal_routing_hints": {"generic_lead": "support"},
                    "routing_hints": {"generic_lead": "sales"},
                }
            },
        )
        result = apply_tenant_overrides(profile, ctx)
        assert result.default_route == "support"

    def test_legacy_string_routing_hints_fallback(self):
        profile = get_profile("generic_lead")
        assert profile is not None
        ctx = load_tenant_context(
            "T_test",
            {"memory": {"routing_hints": {"generic_lead": "invoice"}}},
        )
        result = apply_tenant_overrides(profile, ctx)
        assert result.default_route == "invoice"

    def test_dict_dispatch_hints_ignored_for_profile_routing(self):
        profile = get_profile("generic_lead")
        assert profile is not None
        ctx = load_tenant_context(
            "T_test",
            {"memory": {"routing_hints": {"lead": {"destination": "external"}}}},
        )
        result = apply_tenant_overrides(profile, ctx)
        assert result.default_route == profile.default_route


class TestSlice2aActivationAudit:
    def test_activation_emits_slice2a_audit_events(self, db):
        session = _advance_to_automation(db, capabilities=["followups"])
        session = _complete_slice2a(db, session.id, session.version)
        readiness = run_readiness(
            db, session_id=session.id, operator=_operator(), settings=_settings()
        )
        session = OnboardingRepository.get_session(db, session.id)
        plan = get_activation_plan(db, session_id=session.id, settings=_settings())
        activate_onboarding_session(
            db,
            session_id=session.id,
            operator=_operator("admin"),
            reason="Slice 2A go-live",
            confirmation_phrase="slice-2a-co",
            expected_version=session.version,
            readiness_check_version=session.readiness_check_version,
            plan_hash=plan.plan_hash,
            acknowledged_warning_ids=[w.id for w in readiness.warnings],
            settings=_settings(),
        )
        actions = {a.action for a in db.query(AuditEventRecord).all()}
        assert "onboarding.service_config_materialized" in actions
        assert "onboarding.routing_config_materialized" in actions
        assert "onboarding.intake_cutoff_created" in actions
