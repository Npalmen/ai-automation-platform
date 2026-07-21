"""Integration group requirement tests (Slice B commit 3+4)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.admin.onboarding.integration_draft_schemas import (
    FinanceDestinationPatch,
    GroupImplementationDraft,
    IntegrationSelectionDraft,
    IntegrationsDraftPayload,
    IntegrationsPatchRequest,
)
from app.admin.onboarding.integration_groups import (
    apply_finance_destination_patch,
    evaluate_required_integration_groups,
    get_active_finance_implementation,
    has_valid_accounting_routing,
    reject_coming_later_group_implementation,
)
from app.admin.onboarding.readiness import compute_readiness
from app.admin.onboarding.repository import OnboardingRepository
from app.admin.onboarding.service import create_onboarding_session, patch_modules
from app.admin.onboarding.slice2b_integrations_service import patch_integrations_step
from app.admin.onboarding.steps import evaluate_integrations_step
from app.admin.integrations.selection_sync import sync_allowed_integrations_from_selections
from app.repositories.postgres.database import Base
from app.repositories.postgres.oauth_credential_models import OAuthCredentialRecord
from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository
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


def _upsert_visma_credential(db, tenant_id: str) -> OAuthCredentialRecord:
    cred = OAuthCredentialRecord(
        tenant_id=tenant_id,
        provider="visma",
        access_token="encrypted-access-token",
        refresh_token="encrypted-refresh-token",
    )
    db.add(cred)
    db.commit()
    db.refresh(cred)
    return cred


def _credential_identity(cred: OAuthCredentialRecord) -> tuple[str, str, str, str | None]:
    return (cred.tenant_id, cred.provider, cred.access_token, cred.refresh_token)


def _load_integrations_draft(db, session_id: str) -> IntegrationsDraftPayload:
    record = OnboardingRepository.get_draft(db, session_id, "integrations")
    return IntegrationsDraftPayload.model_validate((record.payload if record else {}) or {})


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


class TestFinanceDestinationPatchRules:
    def test_manual_accounting_routing_requires_visma_disposition(self):
        draft = IntegrationsDraftPayload()
        with pytest.raises(ValueError, match="visma_disposition"):
            apply_finance_destination_patch(
                draft,
                choice="manual_accounting_routing",
                visma_disposition=None,
            )

    def test_manual_accounting_routing_sets_explicit_visma_disposition(self):
        draft = IntegrationsDraftPayload(
            selections={
                "visma": IntegrationSelectionDraft(
                    selection_status="selected_required",
                    migration_review_required=False,
                )
            }
        )
        updated = apply_finance_destination_patch(
            draft,
            choice="manual_accounting_routing",
            visma_disposition="selected_optional",
        )
        assert updated.group_implementations["finance_destination"].type == "manual_accounting_routing"
        assert updated.selections["visma"].selection_status == "selected_optional"

    def test_patch_endpoint_rejects_manual_without_disposition(self, db):
        from pydantic import ValidationError

        session = _session_with_invoice_handling(db)
        with pytest.raises(ValidationError, match="visma_disposition"):
            IntegrationsPatchRequest(
                version=session.version,
                finance_destination=FinanceDestinationPatch(
                    choice="manual_accounting_routing"
                ),
            )

    def test_coming_later_integration_rejected_as_group_implementation(self):
        with pytest.raises(ValueError, match="not selectable"):
            reject_coming_later_group_implementation("fortnox")

    def test_removing_accounting_route_blocks_manual_finance_group(self, db):
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
                finance_destination=FinanceDestinationPatch(
                    choice="manual_accounting_routing",
                    visma_disposition="not_selected",
                ),
            ),
            settings=_settings(),
        )
        OnboardingRepository.upsert_draft(
            db,
            session_id=session.id,
            step_key="routing",
            payload={"route_overrides": {"invoice_generic": "support"}},
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
        assert "group:finance_destination" in (evaluation.get("details") or {}).get("blocking", [])


class TestFinanceDestinationConflictAndSafety:
    def test_only_one_finance_implementation_active(self, db):
        session = _session_with_invoice_handling(db)
        patch_integrations_step(
            db,
            session_id=session.id,
            operator=_operator(),
            body=IntegrationsPatchRequest(
                version=session.version,
                selections={
                    "visma": IntegrationSelectionDraft(
                        selection_status="selected_required",
                        migration_review_required=False,
                    )
                },
            ),
            settings=_settings(),
        )
        draft = _load_integrations_draft(db, session.id)
        assert get_active_finance_implementation(draft) == "visma"

        session = OnboardingRepository.get_session(db, session.id)
        patch_integrations_step(
            db,
            session_id=session.id,
            operator=_operator(),
            body=IntegrationsPatchRequest(
                version=session.version,
                finance_destination=FinanceDestinationPatch(
                    choice="manual_accounting_routing",
                    visma_disposition="not_selected",
                ),
            ),
            settings=_settings(),
        )
        draft = _load_integrations_draft(db, session.id)
        assert get_active_finance_implementation(draft) == "manual_accounting_routing"
        assert draft.group_implementations["finance_destination"].type == "manual_accounting_routing"

        session = OnboardingRepository.get_session(db, session.id)
        patch_integrations_step(
            db,
            session_id=session.id,
            operator=_operator(),
            body=IntegrationsPatchRequest(
                version=session.version,
                finance_destination=FinanceDestinationPatch(choice="visma"),
            ),
            settings=_settings(),
        )
        draft = _load_integrations_draft(db, session.id)
        assert "finance_destination" not in draft.group_implementations
        assert get_active_finance_implementation(draft) == "none"

    def test_switch_to_manual_requires_explicit_visma_disposition(self):
        with pytest.raises(ValueError, match="visma_disposition"):
            apply_finance_destination_patch(
                IntegrationsDraftPayload(),
                choice="manual_accounting_routing",
                visma_disposition=None,
            )

        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="visma_disposition"):
            FinanceDestinationPatch(choice="manual_accounting_routing")

    def test_switch_to_manual_sets_visma_not_selected(self, db):
        session = _session_with_invoice_handling(db)
        patch_integrations_step(
            db,
            session_id=session.id,
            operator=_operator(),
            body=IntegrationsPatchRequest(
                version=session.version,
                finance_destination=FinanceDestinationPatch(
                    choice="manual_accounting_routing",
                    visma_disposition="not_selected",
                ),
            ),
            settings=_settings(),
        )
        draft = _load_integrations_draft(db, session.id)
        assert draft.selections["visma"].selection_status == "not_selected"

    def test_switch_to_manual_sets_visma_selected_optional(self, db):
        session = _session_with_invoice_handling(db)
        patch_integrations_step(
            db,
            session_id=session.id,
            operator=_operator(),
            body=IntegrationsPatchRequest(
                version=session.version,
                finance_destination=FinanceDestinationPatch(
                    choice="manual_accounting_routing",
                    visma_disposition="selected_optional",
                ),
            ),
            settings=_settings(),
        )
        draft = _load_integrations_draft(db, session.id)
        assert draft.selections["visma"].selection_status == "selected_optional"

    def test_manual_routing_does_not_delete_visma_credential(self, db, monkeypatch):
        session = _session_with_invoice_handling(db)
        before = _upsert_visma_credential(db, session.tenant_id)
        before_identity = _credential_identity(before)

        delete_mock = MagicMock(side_effect=OAuthCredentialRepository.delete)
        monkeypatch.setattr(OAuthCredentialRepository, "delete", staticmethod(delete_mock))

        patch_integrations_step(
            db,
            session_id=session.id,
            operator=_operator(),
            body=IntegrationsPatchRequest(
                version=session.version,
                finance_destination=FinanceDestinationPatch(
                    choice="manual_accounting_routing",
                    visma_disposition="not_selected",
                ),
            ),
            settings=_settings(),
        )

        after = OAuthCredentialRepository.get(db, session.tenant_id, "visma")
        assert after is not None
        assert _credential_identity(after) == before_identity
        delete_mock.assert_not_called()

    def test_switch_to_manual_preserves_visma_credential(self, db, monkeypatch):
        session = _session_with_invoice_handling(db)
        before = _upsert_visma_credential(db, session.tenant_id)
        before_identity = _credential_identity(before)

        unlink_mock = MagicMock()
        monkeypatch.setattr(
            "app.admin.onboarding.slice2b_integrations_service.local_unlink_integration",
            unlink_mock,
        )

        patch_integrations_step(
            db,
            session_id=session.id,
            operator=_operator(),
            body=IntegrationsPatchRequest(
                version=session.version,
                finance_destination=FinanceDestinationPatch(
                    choice="manual_accounting_routing",
                    visma_disposition="selected_optional",
                ),
            ),
            settings=_settings(),
        )

        after = OAuthCredentialRepository.get(db, session.tenant_id, "visma")
        assert after is not None
        assert _credential_identity(after) == before_identity
        unlink_mock.assert_not_called()

    def test_coming_later_cannot_be_group_implementation(self):
        with pytest.raises(ValueError, match="not selectable"):
            reject_coming_later_group_implementation("fortnox")

    def test_removing_accounting_route_blocks_readiness(self, db):
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
                finance_destination=FinanceDestinationPatch(
                    choice="manual_accounting_routing",
                    visma_disposition="not_selected",
                ),
            ),
            settings=_settings(),
        )
        OnboardingRepository.upsert_draft(
            db,
            session_id=session.id,
            step_key="routing",
            payload={"route_overrides": {"invoice_generic": "support"}},
        )
        tenant = db.query(TenantConfigRecord).filter_by(tenant_id=session.tenant_id).first()
        session = OnboardingRepository.get_session(db, session.id)
        readiness = compute_readiness(
            db,
            session_id=session.id,
            tenant=tenant,
            settings=_settings(),
            check_version=session.readiness_check_version,
        )
        blocking_ids = [item["id"] for item in readiness["blocking_checks"]]
        assert "step.integrations" in blocking_ids

    def test_selection_change_does_not_enable_external_write(self, db):
        session = _session_with_invoice_handling(db)
        _upsert_visma_credential(db, session.tenant_id)
        patch_integrations_step(
            db,
            session_id=session.id,
            operator=_operator(),
            body=IntegrationsPatchRequest(
                version=session.version,
                selections={
                    "visma": IntegrationSelectionDraft(
                        selection_status="selected_required",
                        migration_review_required=False,
                    )
                },
            ),
            settings=_settings(),
        )
        tenant = db.query(TenantConfigRecord).filter_by(tenant_id=session.tenant_id).first()
        gates = sync_allowed_integrations_from_selections(
            db,
            tenant,
            dry_run=True,
            fail_closed=True,
        )
        assert gates.enabled_external_writes == []
