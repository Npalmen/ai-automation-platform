"""
Tests for operator onboarding Slice 2B (integrations, verification, external routing).
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.admin.onboarding.activation_plan import build_activation_plan
from app.admin.onboarding.errors import OnboardingConflictError
from app.admin.onboarding.integration_draft_schemas import (
    ExternalRoutingPatchRequest,
    GmailIntegrationConfig,
    IntegrationsPatchRequest,
    MondayIntegrationConfig,
    VismaIntegrationConfig,
)
from app.admin.onboarding.integration_verification import IntegrationVerificationStore
from app.admin.onboarding.oauth_state_service import consume_oauth_state, create_oauth_state
from app.admin.onboarding.repository import OnboardingRepository
from app.admin.onboarding.resource_binding import RESOURCE_MONDAY_BOARD, ResourceBindingService
from app.admin.onboarding.draft_schemas import (
    DataStartPatchRequest,
    RoutingPatchRequest,
    ServiceProfilePatchRequest,
)
from app.admin.onboarding.service import (
    create_onboarding_session,
    get_activation_plan,
    patch_automation,
    patch_modules,
    run_readiness,
)
from app.admin.onboarding.slice2a_service import (
    patch_data_start_step,
    patch_routing_step,
    patch_service_profile_step,
)
from app.admin.onboarding.slice2b_external_routing_service import (
    patch_external_routing_step,
    preview_external_routing,
)
from app.admin.onboarding.slice2b_integrations_service import (
    connect_integration,
    get_integration_status,
    patch_integrations_step,
    verify_integration,
)
from app.admin.onboarding.audit_events import OAUTH_CONNECTION_STARTED
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.database import Base
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from tests.onboarding_db_tables import onboarding_sqlite_tables


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
        "GOOGLE_MAIL_ACCESS_TOKEN": "mail-token",
        "MONDAY_API_KEY": "monday-key",
        "FORTNOX_ACCESS_TOKEN": "",
        "VISMA_CLIENT_ID": "client",
        "VISMA_REDIRECT_URI": "http://localhost/callback",
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


def _session_with_lead_management(db):
    created = create_onboarding_session(
        db,
        operator=_operator(),
        company_name="Slice 2B Co",
        slug="slice-2b-co",
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
        integrations=["monday"],
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


def _gmail_readiness_session(db, *, verify: bool = True, token: str = "mail-token"):
    created = create_onboarding_session(
        db,
        operator=_operator(),
        company_name="Gmail Readiness Co",
        slug="gmail-readiness-co",
        org_number=None,
        primary_contact=None,
        contact_email=None,
        phone=None,
        timezone="Europe/Stockholm",
        language="sv",
        settings=_settings(GOOGLE_MAIL_ACCESS_TOKEN=token),
    )
    patch_modules(
        db,
        session_id=created.id,
        operator=_operator(),
        capabilities=["customer_inquiries"],
        integrations=["gmail"],
        expected_version=created.version,
        settings=_settings(GOOGLE_MAIL_ACCESS_TOKEN=token),
    )
    session = OnboardingRepository.get_session(db, created.id)
    patch_automation(
        db,
        session_id=session.id,
        operator=_operator(),
        preset_key="observe_only",
        preset_version=1,
        expected_version=session.version,
        settings=_settings(GOOGLE_MAIL_ACCESS_TOKEN=token),
    )
    session = OnboardingRepository.get_session(db, session.id)
    patch_service_profile_step(
        db,
        session_id=session.id,
        operator=_operator(),
        body=ServiceProfilePatchRequest(
            version=session.version,
            selected_profiles=["generic_support"],
            lead_requirements={},
        ),
        settings=_settings(GOOGLE_MAIL_ACCESS_TOKEN=token),
    )
    session = OnboardingRepository.get_session(db, session.id)
    patch_routing_step(
        db,
        session_id=session.id,
        operator=_operator(),
        body=RoutingPatchRequest(
            version=session.version,
            route_overrides={"generic_support": "support"},
        ),
        settings=_settings(GOOGLE_MAIL_ACCESS_TOKEN=token),
    )
    session = OnboardingRepository.get_session(db, session.id)
    patch_data_start_step(
        db,
        session_id=session.id,
        operator=_operator(),
        body=DataStartPatchRequest(version=session.version, mode="new_incoming_only"),
        settings=_settings(GOOGLE_MAIL_ACCESS_TOKEN=token),
    )
    session = OnboardingRepository.get_session(db, session.id)
    patch_integrations_step(
        db,
        session_id=session.id,
        operator=_operator(),
        body=IntegrationsPatchRequest(
            version=session.version,
            requested_integrations=["gmail"],
            gmail=GmailIntegrationConfig(requested=True, label_scope_slug="gmail-readiness-co"),
        ),
        settings=_settings(GOOGLE_MAIL_ACCESS_TOKEN=token),
    )
    session = OnboardingRepository.get_session(db, session.id)
    if verify:
        verify_integration(
            db,
            session_id=session.id,
            operator=_operator(),
            integration_key="gmail",
            settings=_settings(GOOGLE_MAIL_ACCESS_TOKEN=token),
        )
    return OnboardingRepository.get_session(db, session.id)


class TestSlice2bGmailReadiness:
    def test_gmail_readiness_returns_200_typed_checks(self, db):
        session = _gmail_readiness_session(db)
        settings = _settings(GOOGLE_MAIL_ACCESS_TOKEN="super-secret-mail-token")
        readiness = run_readiness(
            db, session_id=session.id, operator=_operator(), settings=settings
        )

        assert readiness.overall_status in ("ready_with_warnings", "ready")
        all_checks = (
            list(readiness.passed_checks)
            + list(readiness.warnings)
            + list(readiness.not_verifiable)
            + list(readiness.blocking_checks)
        )
        by_id = {c.id: c for c in all_checks}

        assert by_id["integration.gmail.platform_credential"].source_class == "platform_level"
        assert by_id["integration.gmail.platform_credential"] in readiness.passed_checks

        assert by_id["integration.gmail.label_query"].source_class == "locally_verified"
        assert by_id["integration.gmail.label_query"] in readiness.passed_checks
        assert "is:unread" in by_id["integration.gmail.label_query"].message.lower()

        mailbox = by_id["integration.gmail.tenant_mailbox_access"]
        assert mailbox.source_class == "not_verifiable"
        assert mailbox in readiness.not_verifiable
        assert "verified" not in mailbox.message.lower()

        live = by_id["integration.gmail.live_intake"]
        assert live in readiness.warnings
        assert "configured_not_running" in live.message.lower() or "pausad" in live.message.lower()

        cap = by_id["integration.gmail.capability_operational"]
        assert cap in readiness.warnings
        assert cap.source_class == "not_verifiable"

        response_blob = readiness.model_dump_json()
        assert "super-secret-mail-token" not in response_blob
        assert "mail-token" not in response_blob

    def test_gmail_readiness_missing_verification_record_fail_closed(self, db):
        session = _gmail_readiness_session(db, verify=False)
        readiness = run_readiness(
            db,
            session_id=session.id,
            operator=_operator(),
            settings=_settings(),
        )
        not_verifiable_ids = {c.id for c in readiness.not_verifiable}
        assert "integration.gmail.verification_record" in not_verifiable_ids
        assert readiness.overall_status in ("ready_with_warnings", "not_ready")

    def test_gmail_readiness_legacy_draft_blocks_typed(self, db):
        session = _gmail_readiness_session(db, verify=True)
        OnboardingRepository.upsert_draft(
            db,
            session_id=session.id,
            step_key="integrations",
            payload={"gmail": {"label_scope_slug": 12345}, "requested_integrations": "gmail"},
        )
        readiness = run_readiness(
            db,
            session_id=session.id,
            operator=_operator(),
            settings=_settings(),
        )
        blocking_ids = {c.id for c in readiness.blocking_checks}
        assert "integration.gmail.draft_invalid" in blocking_ids
        assert readiness.overall_status == "not_ready"

    def test_gmail_readiness_activation_plan_and_stale_revision(self, db):
        session = _gmail_readiness_session(db)
        readiness = run_readiness(
            db, session_id=session.id, operator=_operator(), settings=_settings()
        )
        plan = get_activation_plan(db, session_id=session.id, settings=_settings())
        assert plan.plan_hash

        session = OnboardingRepository.get_session(db, session.id)
        with pytest.raises(OnboardingConflictError):
            from app.admin.onboarding.service import activate_onboarding_session

            activate_onboarding_session(
                db,
                session_id=session.id,
                operator=_operator("admin"),
                reason="Go",
                confirmation_phrase="gmail-readiness-co",
                expected_version=session.version,
                readiness_check_version=session.readiness_check_version - 1,
                plan_hash=plan.plan_hash,
                acknowledged_warning_ids=[w.id for w in readiness.warnings],
                settings=_settings(),
            )


class TestSlice2bGmailVerify:
    def test_gmail_verify_marks_locally_verified(self, db):
        created = create_onboarding_session(
            db,
            operator=_operator(),
            company_name="Gmail Co",
            slug="gmail-co",
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
            settings=_settings(),
        )
        session = OnboardingRepository.get_session(db, created.id)
        patch_integrations_step(
            db,
            session_id=session.id,
            operator=_operator(),
            body=IntegrationsPatchRequest(
                version=session.version,
                requested_integrations=["gmail"],
                gmail=GmailIntegrationConfig(requested=True, label_scope_slug="gmail-co"),
            ),
            settings=_settings(),
        )
        session = OnboardingRepository.get_session(db, session.id)
        status = verify_integration(
            db,
            session_id=session.id,
            operator=_operator(),
            integration_key="gmail",
            settings=_settings(),
        )
        assert status["lifecycle_status"] == "configured_not_running"
        assert status["verified"] is True
        assert status["source_class"] == "locally_verified"


class TestSlice2bVerificationInvalidation:
    def test_patch_integrations_invalidates_verification(self, db):
        session = _session_with_lead_management(db)
        patch_integrations_step(
            db,
            session_id=session.id,
            operator=_operator(),
            body=IntegrationsPatchRequest(
                version=session.version,
                requested_integrations=["monday"],
                monday=MondayIntegrationConfig(requested=True),
            ),
            settings=_settings(),
        )
        session = OnboardingRepository.get_session(db, session.id)
        patch_external_routing_step(
            db,
            session_id=session.id,
            operator=_operator(),
            body=ExternalRoutingPatchRequest(
                version=session.version,
                targets={
                    "lead": {
                        "target_type": "monday_board",
                        "board_id": "123",
                        "board_name": "Leads",
                    }
                },
            ),
            settings=_settings(),
        )
        session = OnboardingRepository.get_session(db, session.id)
        with patch("app.admin.onboarding.slice2b_integrations_service.MondayClient") as mock_client:
            mock_client.return_value.get_boards.return_value = [{"id": "123", "name": "Leads"}]
            verify_integration(
                db,
                session_id=session.id,
                operator=_operator(),
                integration_key="monday",
                settings=_settings(),
            )
        record = IntegrationVerificationStore.get(db, session.id, "monday")
        assert record.verification_status == "verified"

        session = OnboardingRepository.get_session(db, session.id)
        patch_integrations_step(
            db,
            session_id=session.id,
            operator=_operator(),
            body=IntegrationsPatchRequest(
                version=session.version,
                requested_integrations=["monday"],
                monday=MondayIntegrationConfig(requested=True),
            ),
            settings=_settings(),
        )
        record = IntegrationVerificationStore.get(db, session.id, "monday")
        assert record.verification_status == "invalidated"


class TestSlice2bResourceBinding:
    def test_resource_already_bound_returns_conflict(self, db):
        session = _session_with_lead_management(db)
        ResourceBindingService.bind(
            db,
            resource_type=RESOURCE_MONDAY_BOARD,
            resource_id="999",
            tenant_id=session.tenant_id,
            session_id=session.id,
            operator_id="operator-test",
        )
        db.commit()

        other = create_onboarding_session(
            db,
            operator=_operator(),
            company_name="Other Co",
            slug="other-co",
            org_number=None,
            primary_contact=None,
            contact_email=None,
            phone=None,
            timezone="Europe/Stockholm",
            language="sv",
            settings=_settings(),
        )
        with pytest.raises(OnboardingConflictError) as exc:
            ResourceBindingService.bind(
                db,
                resource_type=RESOURCE_MONDAY_BOARD,
                resource_id="999",
                tenant_id=other.tenant_id,
                session_id=other.id,
                operator_id="operator-test",
            )
        assert exc.value.code == "resource_already_bound"


class TestSlice2bOAuthState:
    def test_oauth_state_one_time_consume(self, db):
        session = _session_with_lead_management(db)
        state_id, _ = create_oauth_state(
            db,
            session=session,
            operator_id="operator-test",
            provider="visma",
            redirect_target=f"/ops/customers/{session.tenant_id}/onboarding",
            settings=_settings(),
        )
        db.commit()
        consume_oauth_state(db, state_id=state_id, settings=_settings())
        db.commit()
        with pytest.raises(Exception):
            consume_oauth_state(db, state_id=state_id, settings=_settings())

    def test_oauth_state_expired(self, db):
        from datetime import timedelta

        from app.admin.onboarding.models import OnboardingOAuthStateRecord

        session = _session_with_lead_management(db)
        state_id, record = create_oauth_state(
            db,
            session=session,
            operator_id="operator-test",
            provider="visma",
            redirect_target=f"/ops/customers/{session.tenant_id}/onboarding",
            settings=_settings(),
        )
        record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
        with pytest.raises(OnboardingConflictError) as exc:
            consume_oauth_state(db, state_id=state_id, settings=_settings())
        assert exc.value.code == "oauth_state_expired"

    def test_oauth_state_invalid_redirect(self, db):
        from app.admin.onboarding.errors import OnboardingValidationError

        session = _session_with_lead_management(db)
        with pytest.raises(OnboardingValidationError):
            create_oauth_state(
                db,
                session=session,
                operator_id="operator-test",
                provider="visma",
                redirect_target="/evil/path",
                settings=_settings(),
            )

    def test_oauth_state_cancelled_session_blocks_consume(self, db):
        session = _session_with_lead_management(db)
        state_id, _ = create_oauth_state(
            db,
            session=session,
            operator_id="operator-test",
            provider="visma",
            redirect_target=f"/ops/customers/{session.tenant_id}/onboarding",
            settings=_settings(),
        )
        session.status = "cancelled"
        db.commit()
        with pytest.raises(OnboardingConflictError) as exc:
            consume_oauth_state(db, state_id=state_id, settings=_settings())
        assert exc.value.code == "oauth_session_stale"


class TestSlice2bExternalRouting:
    def test_preview_external_routing_read_only(self, db):
        session = _session_with_lead_management(db)
        patch_external_routing_step(
            db,
            session_id=session.id,
            operator=_operator(),
            body=ExternalRoutingPatchRequest(
                version=session.version,
                targets={
                    "lead": {
                        "target_type": "monday_board",
                        "board_id": "42",
                        "board_name": "Lead Board",
                    }
                },
            ),
            settings=_settings(),
        )
        preview = preview_external_routing(db, session.id, settings=_settings())
        assert preview["preview"][0]["status"] == "ready"
        assert preview["mutated"] is False


class TestSlice2bVismaLifecycle:
    def test_visma_authorization_required_when_requested_not_connected(self, db):
        session = _session_with_lead_management(db)
        patch_integrations_step(
            db,
            session_id=session.id,
            operator=_operator(),
            body=IntegrationsPatchRequest(
                version=session.version,
                requested_integrations=["visma"],
                visma=VismaIntegrationConfig(requested=True),
            ),
            settings=_settings(),
        )
        status = get_integration_status(db, session.id, "visma", settings=_settings())
        assert status["lifecycle_status"] == "authorization_required"
        assert status["connected"] is False


class TestSlice2bConnectAudit:
    def test_connect_emits_oauth_started_without_tokens(self, db):
        session = _session_with_lead_management(db)
        connect_integration(
            db,
            session_id=session.id,
            operator=_operator(),
            integration_key="visma",
            settings=_settings(),
            redirect_target=f"/ops/customers/{session.tenant_id}/onboarding",
        )
        row = db.query(AuditEventRecord).filter_by(action=OAUTH_CONNECTION_STARTED).first()
        assert row is not None
        assert "token" not in str(row.details).lower()
        assert "code" not in str(row.details).lower()


class TestSlice2bPlanHash:
    def test_plan_hash_includes_slice2b_fingerprint(self, db):
        session = _session_with_lead_management(db)
        tenant = db.query(TenantConfigRecord).filter_by(tenant_id=session.tenant_id).first()
        plan_before = build_activation_plan(
            db, session_id=session.id, tenant=tenant, settings=_settings()
        )
        patch_integrations_step(
            db,
            session_id=session.id,
            operator=_operator(),
            body=IntegrationsPatchRequest(
                version=session.version,
                requested_integrations=["monday"],
                monday=MondayIntegrationConfig(requested=True),
            ),
            settings=_settings(),
        )
        tenant = db.query(TenantConfigRecord).filter_by(tenant_id=session.tenant_id).first()
        session = OnboardingRepository.get_session(db, session.id)
        plan_after = build_activation_plan(
            db, session_id=session.id, tenant=tenant, settings=_settings()
        )
        assert plan_before["plan_hash"] != plan_after["plan_hash"]
