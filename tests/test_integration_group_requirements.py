"""Integration group requirement tests (Slice B commit 3)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.admin.onboarding.integration_draft_schemas import (
    GroupImplementationDraft,
    IntegrationsPatchRequest,
)
from app.admin.onboarding.integration_groups import (
    evaluate_required_integration_groups,
    has_valid_accounting_routing,
)
from app.admin.onboarding.repository import OnboardingRepository
from app.admin.onboarding.service import create_onboarding_session, patch_modules
from app.admin.onboarding.slice2b_integrations_service import patch_integrations_step
from app.admin.onboarding.steps import evaluate_integrations_step
from app.repositories.postgres.database import Base
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


def _session_with_invoice_handling(db):
    created = create_onboarding_session(
        db,
        operator=_operator(),
        company_name="Invoice Co",
        slug="invoice-co",
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
    return OnboardingRepository.get_session(db, created.id)


class TestFinanceDestinationGroups:
    def test_manual_accounting_routing_without_accounting_routing_blocks(self, db):
        session = _session_with_invoice_handling(db)
        patch_integrations_step(
            db,
            session_id=session.id,
            operator=_operator(),
            body=IntegrationsPatchRequest(
                version=session.version,
                group_implementations={
                    "finance_destination": GroupImplementationDraft(
                        type="manual_accounting_routing"
                    )
                },
            ),
            settings=_settings(),
        )
        modules = OnboardingRepository.get_draft(db, session.id, "modules")
        tenant = db.query(TenantConfigRecord).filter_by(tenant_id=session.tenant_id).first()
        evaluation = evaluate_integrations_step(
            db,
            modules_draft=(modules.payload if modules else {}) or {},
            tenant=tenant,
            settings=_settings(),
            session_id=session.id,
        )
        assert evaluation["blocks_activation"] is True
        assert evaluation["step_status"] == "blocked"
        assert "group:finance_destination" in (evaluation.get("details") or {}).get("blocking", [])
        groups = (evaluation.get("details") or {}).get("integration_groups") or []
        finance = next(item for item in groups if item["group_key"] == "finance_destination")
        assert finance["satisfied"] is False
        assert finance["reason"] == "manual_accounting_routing_missing_routing"

    def test_manual_accounting_routing_with_valid_routing_satisfies_group(self, db):
        session = _session_with_invoice_handling(db)
        OnboardingRepository.upsert_draft(
            db,
            session_id=session.id,
            step_key="service_profile",
            payload={"selected_profiles": ["invoice_generic"], "lead_requirements": {}},
        )
        OnboardingRepository.upsert_draft(
            db,
            session_id=session.id,
            step_key="routing",
            payload={"route_overrides": {"invoice_generic": "finance"}},
        )
        patch_integrations_step(
            db,
            session_id=session.id,
            operator=_operator(),
            body=IntegrationsPatchRequest(
                version=session.version,
                group_implementations={
                    "finance_destination": GroupImplementationDraft(
                        type="manual_accounting_routing"
                    )
                },
            ),
            settings=_settings(),
        )
        modules = OnboardingRepository.get_draft(db, session.id, "modules")
        integrations = OnboardingRepository.get_draft(db, session.id, "integrations")
        assert has_valid_accounting_routing(
            modules_draft=(modules.payload if modules else {}) or {},
            service_profile_draft={"selected_profiles": ["invoice_generic"]},
            routing_draft={"route_overrides": {"invoice_generic": "finance"}},
        )
        evaluations = evaluate_required_integration_groups(
            capability_keys=["invoice_handling"],
            integrations_draft=integrations.payload if integrations else {},
            modules_draft=(modules.payload if modules else {}) or {},
            service_profile_draft={"selected_profiles": ["invoice_generic"]},
            routing_draft={"route_overrides": {"invoice_generic": "finance"}},
        )
        finance = next(item for item in evaluations if item.group_key == "finance_destination")
        assert finance.satisfied is True
        assert finance.implementation == "manual_accounting_routing"
