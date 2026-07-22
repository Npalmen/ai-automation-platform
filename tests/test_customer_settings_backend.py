"""Customer settings backend tests (Slice C Commit 2)."""

from __future__ import annotations

import copy

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.admin.customer_settings.domains import collect_forbidden_keys
from app.admin.customer_settings.service import (
    ConfigVersionConflict,
    get_customer_settings_view,
    get_domain_settings,
    patch_domain_settings,
    preview_domain_settings,
)
from app.admin.customer_settings.validation import DomainValidationError, validate_domain_config
from app.admin.tenant_lifecycle.models import TenantActivationSnapshotRecord
from app.admin.onboarding.models import OnboardingSessionRecord
from app.admin.tenant_lifecycle.service import patch_settings_section
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.database import Base
from app.repositories.postgres.oauth_credential_models import OAuthCredentialRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from tests.onboarding_db_tables import onboarding_sqlite_tables


def _operator(role: str = "admin", operator_id: str = "op-test") -> dict:
    return {"id": operator_id, "display_name": "Test Operator", "role": role}


def _active_tenant(
    tenant_id: str = "T_ACTIVE",
    *,
    config_version: int = 3,
    settings: dict | None = None,
) -> TenantConfigRecord:
    base_settings = {
        "company": {
            "timezone": "Europe/Stockholm",
            "language": "sv",
            "industries": ["electrical"],
        },
        "capabilities": {"customer_inquiries": True, "invoice_handling": True},
        "memory": {
            "service_profile": {
                "selected_profiles": ["invoice_generic"],
                "lead_requirements": {},
            },
            "internal_routing_hints": {},
        },
        "routing": {
            "route_overrides": {
                "invoice_generic": "finance",
            }
        },
        "integrations": {
            "selections": {
                "google_mail": {
                    "integration_key": "google_mail",
                    "selection_status": "selected_required",
                    "migration_review_required": False,
                    "requirement_source": "manual",
                    "configured_at": "2026-07-21T00:00:00Z",
                    "configured_by": "operator:seed",
                },
                "visma": {
                    "integration_key": "visma",
                    "selection_status": "selected_required",
                    "migration_review_required": False,
                    "requirement_source": "manual",
                    "configured_at": "2026-07-21T00:00:00Z",
                    "configured_by": "operator:seed",
                },
                "fortnox": {
                    "integration_key": "fortnox",
                    "selection_status": "not_selected",
                    "migration_review_required": False,
                    "requirement_source": "manual",
                    "configured_at": "2026-07-21T00:00:00Z",
                    "configured_by": "operator:seed",
                },
            },
            "enabled_external_writes": [],
            "group_implementations": {},
        },
        "automation": {"approval_first": True},
        "scheduler": {"run_mode": "paused"},
    }
    if settings:
        base_settings.update(settings)
    return TenantConfigRecord(
        tenant_id=tenant_id,
        name="Active Co",
        slug="active-co",
        status="active",
        lifecycle_status="active",
        config_version=config_version,
        readiness_config_version=config_version,
        enabled_job_types=["customer_inquiry", "invoice"],
        allowed_integrations=["google_mail", "visma"],
        auto_actions={"lead": "semi"},
        settings=base_settings,
    )


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    tables = onboarding_sqlite_tables()
    Base.metadata.create_all(bind=engine, tables=tables)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def tenant(db):
    record = _active_tenant()
    db.add(record)
    db.add(
        OAuthCredentialRecord(
            tenant_id=record.tenant_id,
            provider="visma",
            access_token="static-visma-access",
            refresh_token="static-visma-refresh",
        )
    )
    db.add(
        TenantActivationSnapshotRecord(
            id="snap-1",
            tenant_id=record.tenant_id,
            config_version=1,
            plan_hash="abc",
            readiness_check_version=1,
            snapshot_json={"seed": True},
            activated_by_operator_id="op-seed",
        )
    )
    db.add(
        OnboardingSessionRecord(
            id="sess-1",
            tenant_id=record.tenant_id,
            status="active",
            current_step="complete",
            version=1,
            created_by_operator_id="op-seed",
            last_updated_by_operator_id="op-seed",
        )
    )
    db.commit()
    return record


class TestAggregateAndDomainGet:
    def test_aggregate_get_active_tenant(self, db, tenant):
        view = get_customer_settings_view(db, tenant.tenant_id, _operator())
        assert view["tenant_id"] == tenant.tenant_id
        assert view["config_version"] == 3
        assert "integrations" in view["domains"]
        assert view["permissions"]["routing"]["write"] is True

    def test_domain_get(self, db, tenant):
        result = get_domain_settings(db, tenant.tenant_id, "integrations", _operator())
        assert result["domain"] == "integrations"
        assert "google_mail" in result["payload"]["selections"]


class TestPatchAndVersioning:
    def test_patch_requires_expected_config_version(self, db, tenant):
        with pytest.raises(HTTPException) as exc:
            patch_domain_settings(
                db,
                tenant_id=tenant.tenant_id,
                domain="identity",
                expected_config_version=0,
                payload={"timezone": "Europe/Oslo"},
                operator=_operator(),
            )
        assert exc.value.status_code in {409, 422}

    def test_stale_version_returns_409(self, db, tenant):
        with pytest.raises(HTTPException) as exc:
            patch_domain_settings(
                db,
                tenant_id=tenant.tenant_id,
                domain="identity",
                expected_config_version=999,
                payload={"timezone": "Europe/Oslo"},
                operator=_operator(),
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["config_version"] == 3

    def test_successful_patch_bumps_version_once(self, db, tenant):
        result = patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="identity",
            expected_config_version=3,
            payload={"timezone": "Europe/Oslo"},
            operator=_operator(),
            change_reason="Pilot test",
        )
        assert result["config_version"] == 4
        db.refresh(tenant)
        assert tenant.config_version == 4
        assert tenant.settings["company"]["timezone"] == "Europe/Oslo"

    def test_partial_domain_patch_does_not_wipe_other_domain(self, db, tenant):
        before_routing = copy.deepcopy(tenant.settings["routing"])
        patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="identity",
            expected_config_version=3,
            payload={"primary_contact": "Niklas"},
            operator=_operator(),
        )
        db.refresh(tenant)
        assert tenant.settings["routing"] == before_routing


class TestLegacyBypass:
    def test_unknown_section_rejected(self, db, tenant):
        with pytest.raises(HTTPException) as exc:
            patch_settings_section(
                db,
                tenant_id=tenant.tenant_id,
                section="arbitrary",
                operator_id="op",
                config_version=3,
                payload={"foo": "bar"},
            )
        assert exc.value.status_code == 404

    def test_direct_allowed_integrations_rejected(self, db, tenant):
        with pytest.raises(HTTPException) as exc:
            patch_settings_section(
                db,
                tenant_id=tenant.tenant_id,
                section="modules",
                operator_id="op",
                config_version=3,
                payload={"allowed_integrations": ["fortnox"]},
                operator_role="admin",
            )
        assert exc.value.status_code == 422

    def test_direct_enabled_external_writes_rejected(self, db, tenant):
        with pytest.raises(HTTPException) as exc:
            patch_domain_settings(
                db,
                tenant_id=tenant.tenant_id,
                domain="integrations",
                expected_config_version=3,
                payload={"enabled_external_writes": ["visma"]},
                operator=_operator(),
            )
        assert exc.value.status_code == 422

    def test_direct_scheduler_rejected(self, db, tenant):
        with pytest.raises(HTTPException) as exc:
            patch_domain_settings(
                db,
                tenant_id=tenant.tenant_id,
                domain="automation",
                expected_config_version=3,
                payload={"scheduler": {"run_mode": "scheduled"}},
                operator=_operator(),
            )
        assert exc.value.status_code == 422

    def test_direct_config_version_rejected(self, db, tenant):
        forbidden = collect_forbidden_keys({"config_version": 99})
        assert "config_version" in forbidden


class TestPermissionsAndIsolation:
    def test_read_only_patch_forbidden(self, db, tenant):
        with pytest.raises(HTTPException) as exc:
            patch_domain_settings(
                db,
                tenant_id=tenant.tenant_id,
                domain="identity",
                expected_config_version=3,
                payload={"timezone": "Europe/Oslo"},
                operator=_operator(role="read_only"),
            )
        assert exc.value.status_code == 403

    def test_operations_routing_write_allowed(self, db, tenant):
        result = patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="routing",
            expected_config_version=3,
            payload={"route_overrides": {"invoice_generic": "finance"}},
            operator=_operator(role="operations"),
        )
        assert result["config_version"] == 4

    def test_operations_integrations_write_denied(self, db, tenant):
        with pytest.raises(HTTPException) as exc:
            patch_domain_settings(
                db,
                tenant_id=tenant.tenant_id,
                domain="integrations",
                expected_config_version=3,
                payload={
                    "selections": {
                        "fortnox": {"selection_status": "not_selected"},
                    }
                },
                operator=_operator(role="operations"),
            )
        assert exc.value.status_code == 403

    def test_unknown_tenant_fail_closed(self, db):
        with pytest.raises(HTTPException) as exc:
            get_domain_settings(db, "T_MISSING", "identity", _operator())
        assert exc.value.status_code == 404


class TestIntegrations:
    def test_fortnox_not_selected_stays_neutral(self, db, tenant):
        view = get_domain_settings(db, tenant.tenant_id, "integrations", _operator())
        assert view["payload"]["selections"]["fortnox"]["selection_status"] == "not_selected"

    def test_coming_later_rejected(self, db, tenant):
        with pytest.raises(HTTPException) as exc:
            patch_domain_settings(
                db,
                tenant_id=tenant.tenant_id,
                domain="integrations",
                expected_config_version=3,
                payload={
                    "selections": {
                        "fortnox": {"selection_status": "selected_required"},
                    }
                },
                operator=_operator(),
            )
        assert exc.value.status_code == 422

    def test_manual_routing_requires_visma_disposition(self, db, tenant):
        with pytest.raises(HTTPException) as exc:
            patch_domain_settings(
                db,
                tenant_id=tenant.tenant_id,
                domain="integrations",
                expected_config_version=3,
                payload={
                    "finance_destination": {
                        "choice": "manual_accounting_routing",
                    }
                },
                operator=_operator(),
            )
        assert exc.value.status_code == 422

    def test_visma_credential_preserved(self, db, tenant):
        before = db.get(
            OAuthCredentialRecord,
            {"tenant_id": tenant.tenant_id, "provider": "visma"},
        )
        patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="integrations",
            expected_config_version=3,
            payload={
                "finance_destination": {
                    "choice": "manual_accounting_routing",
                    "visma_disposition": "selected_optional",
                }
            },
            operator=_operator(),
        )
        after = db.get(
            OAuthCredentialRecord,
            {"tenant_id": tenant.tenant_id, "provider": "visma"},
        )
        assert before.access_token == after.access_token
        assert before.refresh_token == after.refresh_token

    def test_selection_does_not_auto_enable_external_write(self, db, tenant):
        patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="integrations",
            expected_config_version=3,
            payload={
                "selections": {
                    "google_sheets": {
                        "selection_status": "selected_optional",
                        "migration_review_required": True,
                    }
                }
            },
            operator=_operator(),
        )
        db.refresh(tenant)
        assert "google_sheets" not in (tenant.settings["integrations"].get("enabled_external_writes") or [])


class TestModules:
    def test_module_change_updates_job_types_projection(self, db, tenant):
        patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="modules",
            expected_config_version=3,
            payload={"capabilities": ["customer_inquiries"]},
            operator=_operator(),
        )
        db.refresh(tenant)
        assert tenant.enabled_job_types == ["customer_inquiry"]

    def test_direct_enabled_job_types_forbidden(self, db, tenant):
        with pytest.raises(DomainValidationError):
            validate_domain_config(
                db,
                domain="modules",
                payload={"enabled_job_types": ["invoice"]},
                record=tenant,
            )


class TestAuditAndHistory:
    def test_audit_created_secret_free(self, db, tenant):
        patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="identity",
            expected_config_version=3,
            payload={"phone": "+46701234567"},
            operator=_operator(),
            change_reason="update phone",
        )
        audit = (
            db.query(AuditEventRecord)
            .filter(AuditEventRecord.tenant_id == tenant.tenant_id)
            .order_by(AuditEventRecord.created_at.desc())
            .first()
        )
        assert audit is not None
        assert audit.details["change_reason"] == "update phone"
        assert "changed_paths" in audit.details
        raw = str(audit.details)
        assert "static-visma" not in raw
        assert "token" not in raw.lower() or "[REDACTED]" in raw

    def test_activation_snapshot_unchanged(self, db, tenant):
        before = db.query(TenantActivationSnapshotRecord).count()
        patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="identity",
            expected_config_version=3,
            payload={"language": "en"},
            operator=_operator(),
        )
        after = db.query(TenantActivationSnapshotRecord).count()
        assert before == after == 1

    def test_onboarding_session_unchanged(self, db, tenant):
        before = db.get(OnboardingSessionRecord, "sess-1").version
        patch_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="identity",
            expected_config_version=3,
            payload={"language": "sv"},
            operator=_operator(),
        )
        after = db.get(OnboardingSessionRecord, "sess-1").version
        assert before == after


class TestPreview:
    def test_preview_writes_nothing(self, db, tenant):
        version_before = tenant.config_version
        settings_before = copy.deepcopy(tenant.settings)
        preview = preview_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="modules",
            payload={"capabilities": ["customer_inquiries"]},
            operator=_operator(),
        )
        db.refresh(tenant)
        assert preview["valid"] is True
        assert tenant.config_version == version_before
        assert tenant.settings == settings_before

    def test_preview_shows_readiness_domains(self, db, tenant):
        preview = preview_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="integrations",
            payload={
                "finance_destination": {
                    "choice": "manual_accounting_routing",
                    "visma_disposition": "not_selected",
                }
            },
            operator=_operator(),
        )
        assert "integrations" in preview["readiness_domains_affected"]

    def test_preview_and_patch_share_validation(self, db, tenant):
        payload = {
            "finance_destination": {
                "choice": "manual_accounting_routing",
                "visma_disposition": "selected_optional",
            }
        }
        preview = preview_domain_settings(
            db,
            tenant_id=tenant.tenant_id,
            domain="integrations",
            payload=payload,
            operator=_operator(),
        )
        if preview["blocking"]:
            with pytest.raises(HTTPException):
                patch_domain_settings(
                    db,
                    tenant_id=tenant.tenant_id,
                    domain="integrations",
                    expected_config_version=3,
                    payload=payload,
                    operator=_operator(),
                )
        else:
            patch_domain_settings(
                db,
                tenant_id=tenant.tenant_id,
                domain="integrations",
                expected_config_version=3,
                payload=payload,
                operator=_operator(),
            )
