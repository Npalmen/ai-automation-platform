"""Slice B integration selection tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.admin.integrations.selection_backfill import backfill_tenant_selections
from app.admin.integrations.selection_models import parse_selections_map
from app.admin.integrations.selection_resolver import derive_integration_selection
from app.admin.integrations.selection_sync import sync_allowed_integrations_from_selections
from app.integrations.keys import normalize_integration_key, validate_unique_canonical_keys


def _niklas_record(**overrides):
    base = {
        "tenant_id": "T_NIKLAS_DEMO_001",
        "allowed_integrations": ["google_mail", "google_sheets", "visma"],
        "enabled_job_types": ["customer_inquiry", "invoice"],
        "settings": {},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.fixture
def mock_db(monkeypatch):
    db = MagicMock()

    def _oauth(db, tenant_id, provider):
        if provider in ("google_mail", "visma"):
            return object()
        return None

    from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

    monkeypatch.setattr(OAuthCredentialRepository, "get", staticmethod(_oauth))
    monkeypatch.setattr(TenantConfigRepository, "get_settings", staticmethod(lambda db, tid: {}))
    return db


class TestCanonicalKeys:
    def test_gmail_normalizes_to_google_mail(self):
        assert normalize_integration_key("gmail") == "google_mail"

    def test_duplicate_alias_blocked(self):
        with pytest.raises(ValueError):
            validate_unique_canonical_keys(["gmail", "google_mail"])


class TestNiklasBackfillGate:
    def test_niklas_backfill_minimum_requirements(self, mock_db, monkeypatch):
        from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

        record = _niklas_record()
        monkeypatch.setattr(TenantConfigRepository, "get", staticmethod(lambda db, tid: record))

        report = backfill_tenant_selections(mock_db, "T_NIKLAS_DEMO_001", dry_run=True)
        decisions = {d.integration_key: d for d in report.decisions}

        assert decisions["google_mail"].selection_status == "selected_required"
        assert decisions["google_mail"].migration_review_required is False

        assert decisions["visma"].selection_status == "selected_required"
        assert decisions["visma"].migration_review_required is False

        assert decisions["fortnox"].selection_status == "not_selected"
        assert decisions["fortnox"].migration_review_required is False

        sheets = decisions["google_sheets"]
        assert sheets.selection_status == "selected_optional"
        assert sheets.migration_review_required is True

    def test_niklas_backfill_persists_system_actor(self, mock_db, monkeypatch):
        from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

        record = _niklas_record()
        monkeypatch.setattr(TenantConfigRepository, "get", staticmethod(lambda db, tid: record))

        backfill_tenant_selections(mock_db, "T_NIKLAS_DEMO_001", dry_run=False)
        selections = parse_selections_map(record.settings["integrations"]["selections"])
        assert selections["google_mail"].configured_by == "system:migration_016"
        assert selections["google_mail"].requirement_source == "legacy_backfill"


class TestRuntimeSyncFailClosed:
    def test_selection_alone_does_not_enable_external_writes(self, mock_db):
        record = _niklas_record(
            settings={
                "integrations": {
                    "selections": {
                        "google_mail": {
                            "integration_key": "google_mail",
                            "selection_status": "selected_required",
                            "migration_review_required": False,
                            "requirement_source": "manual",
                            "configured_at": "2026-07-21T00:00:00Z",
                            "configured_by": "operator:ops",
                        }
                    },
                    "enabled_external_writes": [],
                }
            }
        )
        gates = sync_allowed_integrations_from_selections(
            mock_db, record, dry_run=True, fail_closed=True
        )
        assert gates.enabled_external_writes == []

    def test_optional_without_verification_stays_neutral_in_resolver(self, mock_db):
        record = _niklas_record(
            allowed_integrations=["google_mail", "visma"],
            settings={
                "integrations": {
                    "selections": {
                        "google_mail": {
                            "integration_key": "google_mail",
                            "selection_status": "selected_optional",
                            "migration_review_required": False,
                            "requirement_source": "manual",
                            "configured_at": "2026-07-21T00:00:00Z",
                            "configured_by": "operator:ops",
                        }
                    }
                }
            },
        )
        view = derive_integration_selection(mock_db, record, "google_mail")
        assert view.selection_status == "selected_optional"

    def test_explicit_selection_overrides_legacy_fallback(self, mock_db):
        record = _niklas_record(
            allowed_integrations=["fortnox"],
            settings={
                "integrations": {
                    "selections": {
                        "fortnox": {
                            "integration_key": "fortnox",
                            "selection_status": "not_selected",
                            "migration_review_required": False,
                            "requirement_source": "manual",
                            "configured_at": "2026-07-21T00:00:00Z",
                            "configured_by": "operator:ops",
                        }
                    }
                }
            },
        )
        view = derive_integration_selection(mock_db, record, "fortnox")
        assert view.selection_status == "not_selected"
