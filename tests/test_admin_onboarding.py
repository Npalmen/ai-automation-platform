"""
Tests for operator onboarding (Kapitel 9 slice 1).
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.admin.onboarding.models import (
    OnboardingSessionRecord,
    OnboardingStepDraftRecord,
    OnboardingStepStateRecord,
)
from app.admin.onboarding.readiness import compute_readiness
from app.admin.onboarding.repository import OnboardingRepository
from app.admin.onboarding.service import (
    activate_onboarding_session,
    create_onboarding_session,
    get_activation_plan,
    patch_automation,
    patch_modules,
    run_readiness,
)
from app.admin.onboarding.steps import evaluate_integrations_step
from app.admin.onboarding.tenant_id import generate_tenant_id, normalize_slug
from tests.onboarding_db_tables import onboarding_sqlite_tables
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.database import Base
from app.repositories.postgres.tenant_api_key_models import TenantApiKeyRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord


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


class TestOnboardingSchemaRegistration:
    def test_startup_import_creates_onboarding_tables(self):
        import app.admin.onboarding.models  # noqa: F401

        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        tables = set(inspect(engine).get_table_names())
        assert "onboarding_sessions" in tables
        assert "onboarding_step_states" in tables
        assert "onboarding_step_drafts" in tables


class TestTenantIdGeneration:
    def test_tenant_id_is_not_slug_based(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(
            bind=engine,
            tables=[TenantConfigRecord.__table__],
        )
        Session = sessionmaker(bind=engine)
        db = Session()
        tenant_id = generate_tenant_id(db)
        db.close()
        assert tenant_id.startswith("T_")
        assert tenant_id != f"T_{normalize_slug('acme-demo')}"

    def test_slug_normalization(self):
        assert normalize_slug("Acme Demo AB") == "acme-demo-ab"


class TestOnboardingServiceSqlite:
    @pytest.fixture
    def db(self):
        engine = create_engine("sqlite:///:memory:")
        tables = onboarding_sqlite_tables()
        Base.metadata.create_all(bind=engine, tables=tables)
        Session = sessionmaker(bind=engine)
        session = Session()
        yield session
        session.close()

    def test_create_does_not_issue_api_key(self, db):
        with patch("app.admin.onboarding.service._utcnow", return_value=datetime(2026, 1, 1, tzinfo=timezone.utc)):
            result = create_onboarding_session(
                db,
                operator=_operator("operations"),
                company_name="Slice One AB",
                slug="slice-one",
                org_number=None,
                primary_contact=None,
                contact_email=None,
                phone=None,
                timezone="Europe/Stockholm",
                language="sv",
                settings=_settings(),
            )
        assert result.tenant_id
        keys = db.query(TenantApiKeyRecord).all()
        assert keys == []
        tenant = db.query(TenantConfigRecord).filter_by(tenant_id=result.tenant_id).first()
        assert tenant.status == "inactive"

    def test_repository_allows_only_one_open_session_when_index_present(self, db):
        created = create_onboarding_session(
            db,
            operator=_operator(),
            company_name="First",
            slug="first-co",
            org_number=None,
            primary_contact=None,
            contact_email=None,
            phone=None,
            timezone="Europe/Stockholm",
            language="sv",
            settings=_settings(),
        )
        existing = OnboardingRepository.get_open_session_for_tenant(db, created.tenant_id)
        assert existing is not None
        assert existing.id == created.id

    def test_readiness_blocks_mandatory_not_implemented_steps(self, db):
        created = create_onboarding_session(
            db,
            operator=_operator(),
            company_name="Lead Co",
            slug="lead-co",
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
            capabilities=["lead_management"],
            integrations=[],
            expected_version=created.version,
            settings=_settings(),
        )
        patch_automation(
            db,
            session_id=created.id,
            operator=_operator(),
            preset_key="observe_only",
            preset_version=1,
            expected_version=created.version + 1,
            settings=_settings(),
        )
        session = OnboardingRepository.get_session(db, created.id)
        readiness = run_readiness(
            db,
            session_id=created.id,
            operator=_operator(),
            settings=_settings(),
        )
        assert readiness.overall_status == "not_ready"
        blocking_ids = {item.id for item in readiness.blocking_checks}
        assert "step.service_profile" in blocking_ids

    def test_global_platform_health_not_tenant_verified(self, db):
        created = create_onboarding_session(
            db,
            operator=_operator(),
            company_name="Mail Co",
            slug="mail-co",
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
            capabilities=["customer_inquiries"],
            integrations=["gmail"],
            expected_version=created.version,
            settings=_settings(GOOGLE_MAIL_ACCESS_TOKEN="platform-token"),
        )
        tenant = db.query(TenantConfigRecord).filter_by(tenant_id=created.tenant_id).first()
        modules = OnboardingRepository.get_draft(db, created.id, "modules")
        evaluation = evaluate_integrations_step(
            db,
            modules_draft=modules.payload,
            tenant=tenant,
            settings=_settings(GOOGLE_MAIL_ACCESS_TOKEN="platform-token"),
            session_id=created.id,
        )
        assert evaluation["step_status"] == "blocked"
        assert evaluation["blocks_activation"] is True

    def test_activation_transaction_sets_active_and_audit(self, db):
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
        session = OnboardingRepository.get_session(db, created.id)
        readiness = run_readiness(
            db,
            session_id=created.id,
            operator=_operator(),
            settings=_settings(),
        )
        assert readiness.overall_status == "ready_with_warnings"
        session = OnboardingRepository.get_session(db, created.id)
        plan = get_activation_plan(db, session_id=created.id, settings=_settings())
        response = activate_onboarding_session(
            db,
            session_id=created.id,
            operator=_operator("admin"),
            reason="Pilot go-live",
            confirmation_phrase="followups-co",
            expected_version=session.version,
            readiness_check_version=session.readiness_check_version,
            plan_hash=plan.plan_hash,
            acknowledged_warning_ids=[w.id for w in readiness.warnings],
            settings=_settings(),
        )
        assert response.status == "activated"
        tenant = db.query(TenantConfigRecord).filter_by(tenant_id=created.tenant_id).first()
        assert tenant.status == "active"
        audits = db.query(AuditEventRecord).filter_by(action="onboarding.activation_succeeded").all()
        assert len(audits) == 1
        assert "api_key" not in str(audits[0].details).lower()

    def test_stale_readiness_version_rejected(self, db):
        created = create_onboarding_session(
            db,
            operator=_operator(),
            company_name="Stale Co",
            slug="stale-co",
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
        run_readiness(db, session_id=created.id, operator=_operator(), settings=_settings())
        session = OnboardingRepository.get_session(db, created.id)
        plan = get_activation_plan(db, session_id=created.id, settings=_settings())
        from app.admin.onboarding.errors import OnboardingStaleReadinessError

        with pytest.raises(OnboardingStaleReadinessError):
            activate_onboarding_session(
                db,
                session_id=created.id,
                operator=_operator("admin"),
                reason="Go",
                confirmation_phrase="stale-co",
                expected_version=session.version,
                readiness_check_version=session.readiness_check_version - 1,
                plan_hash=plan.plan_hash,
                acknowledged_warning_ids=[],
                settings=_settings(),
            )

    def test_compute_readiness_classifies_sources(self, db):
        created = create_onboarding_session(
            db,
            operator=_operator(),
            company_name="Classify Co",
            slug="classify-co",
            org_number=None,
            primary_contact=None,
            contact_email=None,
            phone=None,
            timezone="Europe/Stockholm",
            language="sv",
            settings=_settings(),
        )
        tenant = db.query(TenantConfigRecord).filter_by(tenant_id=created.tenant_id).first()
        result = compute_readiness(
            db,
            session_id=created.id,
            tenant=tenant,
            settings=_settings(),
            check_version=1,
        )
        for check in (
            result["blocking_checks"]
            + result["passed_checks"]
            + result["warnings"]
            + result["not_applicable"]
            + result["not_verifiable"]
        ):
            assert check["source_class"] in {
                "tenant_specific",
                "platform_level",
                "declared",
                "locally_verified",
                "externally_verified",
                "not_verifiable",
                "not_applicable",
            }
