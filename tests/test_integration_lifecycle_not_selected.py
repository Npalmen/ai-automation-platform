"""Regression: not_selected integrations in finance_destination group must stay neutral."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.admin.onboarding.integration_draft_schemas import (
    IntegrationSelectionDraft,
    IntegrationsPatchRequest,
)
from app.admin.onboarding.repository import OnboardingRepository
from app.admin.onboarding.service import create_onboarding_session, patch_modules
from app.admin.onboarding.slice2b_integrations_service import get_integrations_step
from app.admin.onboarding.steps import _required_integrations_for_capabilities
from app.repositories.postgres.database import Base
from app.repositories.postgres.oauth_credential_models import OAuthCredentialRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from tests.onboarding_db_tables import onboarding_sqlite_tables


def _operator() -> dict:
    return {"id": "operator-test", "display_name": "Test Operator", "role": "admin"}


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


def _niklas_like_selections() -> dict[str, IntegrationSelectionDraft]:
    return {
        "google_mail": IntegrationSelectionDraft(
            integration_key="google_mail",
            selection_status="selected_required",
            migration_review_required=False,
            requirement_source="migration",
            configured_by="system:migration_016",
        ),
        "visma": IntegrationSelectionDraft(
            integration_key="visma",
            selection_status="selected_required",
            migration_review_required=False,
            requirement_source="migration",
            configured_by="system:migration_016",
        ),
        "fortnox": IntegrationSelectionDraft(
            integration_key="fortnox",
            selection_status="not_selected",
            migration_review_required=False,
            requirement_source="migration",
            configured_by="system:migration_016",
        ),
        "google_sheets": IntegrationSelectionDraft(
            integration_key="google_sheets",
            selection_status="selected_optional",
            migration_review_required=True,
            requirement_source="migration",
            configured_by="system:migration_016",
        ),
    }


def _session_invoice_handling_with_niklas_selections(db):
    created = create_onboarding_session(
        db,
        operator=_operator(),
        company_name="Niklas Gate Co",
        slug="niklas-gate-co",
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
        capabilities=["invoice_handling"],
        integrations=[],
        expected_version=created.version,
        settings=_settings(),
    )
    session = OnboardingRepository.get_session(db, created.id)
    from app.admin.onboarding.slice2b_integrations_service import patch_integrations_step

    patch_integrations_step(
        db,
        session_id=session.id,
        operator=_operator(),
        body=IntegrationsPatchRequest(
            version=session.version,
            selections=_niklas_like_selections(),
        ),
        settings=_settings(),
    )
    tenant = db.query(TenantConfigRecord).filter_by(tenant_id=session.tenant_id).one()
    db.add(
        OAuthCredentialRecord(
            tenant_id=tenant.tenant_id,
            provider="visma",
            access_token="visma-access",
            refresh_token="visma-refresh",
        )
    )
    db.commit()
    return OnboardingRepository.get_session(db, session.id)


class TestFinanceGroupNotSelectedLifecycle:
    def test_invoice_handling_does_not_require_group_providers(self):
        required = _required_integrations_for_capabilities(["invoice_handling"])
        assert "fortnox" not in required
        assert "visma" not in required
        assert "bokio" not in required

    def test_get_integrations_step_with_fortnox_not_selected(self, db):
        session = _session_invoice_handling_with_niklas_selections(db)
        result = get_integrations_step(db, session.id, settings=_settings())

        fortnox = next(
            item for item in result["integrations"] if item["integration_key"] == "fortnox"
        )
        assert fortnox["selection_status"] == "not_selected"
        assert fortnox["required"] is False
        assert fortnox["requested"] is False
        assert fortnox["lifecycle_status"] == "not_applicable"
        assert fortnox["connection_status"] == "not_requested"

        visma = next(
            item for item in result["integrations"] if item["integration_key"] == "visma"
        )
        assert visma["selection_status"] == "selected_required"
        assert visma["requested"] is True

        finance = result["finance_destination"]
        assert finance["active_implementation"] == "visma"
        assert finance["satisfied"] is True
        assert finance["blocks_activation"] is False

    def test_bokio_not_selected_registry_entry_is_neutral(self, db):
        session = _session_invoice_handling_with_niklas_selections(db)
        selections = _niklas_like_selections()
        selections["bokio"] = IntegrationSelectionDraft(
            integration_key="bokio",
            selection_status="not_selected",
            migration_review_required=False,
            requirement_source="migration",
            configured_by="system:migration_016",
        )
        session = OnboardingRepository.get_session(db, session.id)
        from app.admin.onboarding.slice2b_integrations_service import patch_integrations_step

        patch_integrations_step(
            db,
            session_id=session.id,
            operator=_operator(),
            body=IntegrationsPatchRequest(
                version=session.version,
                selections=selections,
            ),
            settings=_settings(),
        )
        result = get_integrations_step(db, session.id, settings=_settings())
        bokio = next(
            item for item in result["integrations"] if item["integration_key"] == "bokio"
        )
        assert bokio["selection_status"] == "not_selected"
        assert bokio["required"] is False
        assert bokio["lifecycle_status"] in ("not_applicable", "not_supported")
