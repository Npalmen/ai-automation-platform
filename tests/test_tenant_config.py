"""
Tests for DB-driven tenant config slice.

Covers:
  - TenantConfigRepository.get returns None when no row exists
  - TenantConfigRepository.get returns row when present
  - TenantConfigRepository.upsert creates a new row
  - TenantConfigRepository.upsert updates an existing row
  - TenantConfigRepository.to_dict returns correct shape
  - get_tenant_config falls back to static TENANT_CONFIGS when db=None
  - get_tenant_config falls back to static when DB returns no row
  - get_tenant_config returns DB row when one exists
  - get_tenant_config falls back gracefully when DB raises
  - is_job_type_enabled_for_tenant still works (no regression)
  - is_integration_enabled_for_tenant still works (no regression)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.config import TENANT_CONFIGS, get_tenant_config, _tenant_config_from_static
from app.domain.workflows.enums import JobType
from app.integrations.enums import IntegrationType
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
from app.workflows.policies import is_job_type_enabled_for_tenant
from app.integrations.policies import is_integration_enabled_for_tenant


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_record(
    tenant_id: str = "TENANT_1001",
    name: str = "DB Tenant",
    enabled_job_types: list | None = None,
    allowed_integrations: list | None = None,
    auto_actions: dict | None = None,
) -> MagicMock:
    rec = MagicMock()
    rec.tenant_id = tenant_id
    rec.name = name
    rec.enabled_job_types = enabled_job_types or ["lead"]
    rec.allowed_integrations = allowed_integrations or ["google_mail"]
    rec.auto_actions = auto_actions or {}
    return rec


def _mock_db() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# TenantConfigRepository
# ---------------------------------------------------------------------------

class TestTenantConfigRepository:
    def test_get_returns_none_when_no_row(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None
        result = TenantConfigRepository.get(db, "TENANT_UNKNOWN")
        assert result is None

    def test_get_returns_record_when_present(self):
        db = _mock_db()
        rec = _fake_record()
        db.query.return_value.filter.return_value.first.return_value = rec
        result = TenantConfigRepository.get(db, "TENANT_1001")
        assert result is rec

    def test_upsert_creates_new_row(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.first.return_value = None

        fake_record = MagicMock()
        from app.repositories.postgres.tenant_config_models import TenantConfigRecord
        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRecord",
            return_value=fake_record,
        ):
            TenantConfigRepository.upsert(
                db, "TENANT_NEW", name="New", enabled_job_types=["lead"]
            )

        db.add.assert_called_once_with(fake_record)
        db.commit.assert_called_once()

    def test_upsert_updates_existing_row(self):
        db = _mock_db()
        rec = _fake_record()
        db.query.return_value.filter.return_value.first.return_value = rec

        TenantConfigRepository.upsert(
            db, "TENANT_1001", name="Updated Name", enabled_job_types=["lead", "invoice"]
        )

        assert rec.name == "Updated Name"
        assert rec.enabled_job_types == ["lead", "invoice"]
        db.add.assert_not_called()
        db.commit.assert_called_once()

    def test_to_dict_shape(self):
        rec = _fake_record(
            name="Test",
            enabled_job_types=["lead", "invoice"],
            allowed_integrations=["google_mail"],
            auto_actions={"lead": True},
        )
        result = TenantConfigRepository.to_dict(rec)
        assert result["name"] == "Test"
        assert "lead" in result["enabled_job_types"]
        assert "invoice" in result["enabled_job_types"]
        assert result["auto_actions"] == {"lead": True}

    def test_to_dict_none_fields_become_empty(self):
        rec = MagicMock()
        rec.name = None
        rec.enabled_job_types = None
        rec.allowed_integrations = None
        rec.auto_actions = None
        result = TenantConfigRepository.to_dict(rec)
        assert result["enabled_job_types"] == []
        assert result["allowed_integrations"] == []
        assert result["auto_actions"] == {}


# ---------------------------------------------------------------------------
# get_tenant_config
# ---------------------------------------------------------------------------

class TestGetTenantConfig:
    def test_returns_static_when_db_is_none(self):
        result = get_tenant_config("TENANT_1001", db=None)
        assert result == TENANT_CONFIGS["TENANT_1001"]

    def test_returns_static_fallback_no_db(self):
        # No db arg — original call signature
        result = get_tenant_config("TENANT_1001")
        assert result == TENANT_CONFIGS["TENANT_1001"]

    def test_fallback_to_default_tenant_for_unknown(self):
        result = get_tenant_config("TENANT_UNKNOWN")
        assert result == TENANT_CONFIGS["TENANT_1001"]

    def test_returns_db_row_when_present(self):
        db = _mock_db()
        rec = _fake_record(enabled_job_types=["lead", "invoice"])

        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=rec,
        ):
            result = get_tenant_config("TENANT_1001", db=db)

        assert "lead" in result["enabled_job_types"]
        assert "invoice" in result["enabled_job_types"]

    def test_falls_back_to_static_when_db_returns_none(self):
        db = _mock_db()

        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=None,
        ):
            result = get_tenant_config("TENANT_1001", db=db)

        assert result == TENANT_CONFIGS["TENANT_1001"]

    def test_falls_back_gracefully_when_db_raises(self):
        db = _mock_db()

        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            side_effect=Exception("DB unavailable"),
        ):
            result = get_tenant_config("TENANT_1001", db=db)

        # Must not raise; must return static config
        assert result == TENANT_CONFIGS["TENANT_1001"]


# ---------------------------------------------------------------------------
# Policy regression — static fallback unchanged (no db arg)
# ---------------------------------------------------------------------------

class TestPoliciesRegression:
    def test_is_job_type_enabled_lead_tenant_1001(self):
        assert is_job_type_enabled_for_tenant(JobType.LEAD, "TENANT_1001") is True

    def test_is_job_type_enabled_invoice_tenant_2001_false(self):
        assert is_job_type_enabled_for_tenant(JobType.INVOICE, "TENANT_2001") is False

    def test_is_job_type_enabled_invoice_tenant_3001(self):
        assert is_job_type_enabled_for_tenant(JobType.INVOICE, "TENANT_3001") is True

    def test_is_integration_enabled_google_mail_tenant_1001(self):
        assert is_integration_enabled_for_tenant("TENANT_1001", IntegrationType.GOOGLE_MAIL) is True

    def test_is_integration_enabled_accounting_tenant_2001_false(self):
        # TENANT_2001 does not have ACCOUNTING
        assert is_integration_enabled_for_tenant("TENANT_2001", IntegrationType.ACCOUNTING) is False


# ---------------------------------------------------------------------------
# DB-backed runtime policy — db row overrides static config
# ---------------------------------------------------------------------------

class TestRuntimePolicyWithDb:
    """
    Proves that when a db is provided and a TenantConfigRecord exists,
    the policy functions use DB config instead of TENANT_CONFIGS.
    """

    def _db_with_record(self, record) -> MagicMock:
        """Return a mock db session whose query chain returns the given record."""
        db = _mock_db()
        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=record,
        ):
            return db

    def test_job_type_allowed_via_db_config(self):
        """DB row enables 'invoice' for a tenant that has only 'lead' in static config."""
        db = _mock_db()
        rec = _fake_record(enabled_job_types=["lead", "invoice"])

        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=rec,
        ):
            # TENANT_2001 has only lead/customer_inquiry in static — DB adds invoice
            result = is_job_type_enabled_for_tenant(JobType.INVOICE, "TENANT_2001", db=db)

        assert result is True

    def test_job_type_blocked_via_db_config(self):
        """DB row restricts a tenant to only 'invoice', blocking 'lead'."""
        db = _mock_db()
        rec = _fake_record(enabled_job_types=["invoice"])

        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=rec,
        ):
            # TENANT_1001 has lead in static — DB restricts to invoice only
            result = is_job_type_enabled_for_tenant(JobType.LEAD, "TENANT_1001", db=db)

        assert result is False

    def test_integration_allowed_via_db_config(self):
        """DB row enables ACCOUNTING for a tenant that lacks it in static config."""
        db = _mock_db()
        rec = _fake_record(allowed_integrations=["accounting", "google_mail"])

        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=rec,
        ):
            # TENANT_2001 has no ACCOUNTING in static — DB adds it
            result = is_integration_enabled_for_tenant("TENANT_2001", IntegrationType.ACCOUNTING, db=db)

        assert result is True

    def test_integration_blocked_via_db_config(self):
        """DB row removes GOOGLE_MAIL from a tenant that has it in static config."""
        db = _mock_db()
        rec = _fake_record(allowed_integrations=["accounting"])  # no google_mail

        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=rec,
        ):
            # TENANT_1001 has GOOGLE_MAIL in static — DB restricts
            result = is_integration_enabled_for_tenant("TENANT_1001", IntegrationType.GOOGLE_MAIL, db=db)

        assert result is False

    def test_job_type_falls_back_to_static_when_no_db_row(self):
        """When db is provided but no row exists, static config is used."""
        db = _mock_db()

        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=None,
        ):
            result = is_job_type_enabled_for_tenant(JobType.LEAD, "TENANT_1001", db=db)

        # TENANT_1001 has lead in static — should still return True
        assert result is True

    def test_integration_falls_back_to_static_when_no_db_row(self):
        """When db is provided but no row exists, static config is used."""
        db = _mock_db()

        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=None,
        ):
            result = is_integration_enabled_for_tenant("TENANT_1001", IntegrationType.GOOGLE_MAIL, db=db)

        assert result is True
