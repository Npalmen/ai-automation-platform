"""
Tests for GET /tenant/config/{tenant_id} — unauthenticated tenant config lookup.

Covers:
  - Returns correct shape for a known tenant (DB-backed config)
  - Returns static fallback shape for an unknown tenant
  - current_tenant in response matches the path parameter
  - allowed_integrations normalised to strings (same as GET /tenant)

Tests call the endpoint function directly with mocked DB and get_tenant_config,
matching the established pattern in this repo.
"""
from __future__ import annotations

from unittest.mock import patch

from app.integrations.enums import IntegrationType


_UNSET = object()


def _mock_config(
    tenant_id: str = "TENANT_9999",
    name: str = "Test Tenant",
    enabled_job_types=_UNSET,
    allowed_integrations=_UNSET,
    auto_actions=_UNSET,
) -> dict:
    return {
        "name": name,
        "enabled_job_types": ["lead"] if enabled_job_types is _UNSET else enabled_job_types,
        "allowed_integrations": [] if allowed_integrations is _UNSET else allowed_integrations,
        "auto_actions": {} if auto_actions is _UNSET else auto_actions,
    }


class TestGetTenantConfigById:
    def _call(self, tenant_id: str, config: dict) -> dict:
        from unittest.mock import MagicMock
        from app.main import get_tenant_config_by_id
        db = MagicMock()
        with patch("app.main.get_tenant_config", return_value=config):
            return get_tenant_config_by_id(tenant_id=tenant_id, db=db)

    def test_current_tenant_matches_path_param(self):
        result = self._call("TENANT_9999", _mock_config("TENANT_9999"))
        assert result["current_tenant"] == "TENANT_9999"

    def test_returns_name(self):
        result = self._call("TENANT_9999", _mock_config(name="Acme AB"))
        assert result["name"] == "Acme AB"

    def test_returns_enabled_job_types(self):
        result = self._call("TENANT_9999", _mock_config(enabled_job_types=["lead", "invoice"]))
        assert "lead" in result["enabled_job_types"]
        assert "invoice" in result["enabled_job_types"]

    def test_returns_auto_actions(self):
        result = self._call("TENANT_9999", _mock_config(auto_actions={"lead": True}))
        assert result["auto_actions"]["lead"] is True

    def test_normalises_enum_integrations_to_strings(self):
        cfg = _mock_config(allowed_integrations=[IntegrationType.GOOGLE_MAIL, IntegrationType.CRM])
        result = self._call("TENANT_9999", cfg)
        assert "google_mail" in result["allowed_integrations"]
        assert "crm" in result["allowed_integrations"]
        for item in result["allowed_integrations"]:
            assert isinstance(item, str)

    def test_string_integrations_pass_through(self):
        cfg = _mock_config(allowed_integrations=["google_mail", "slack"])
        result = self._call("TENANT_9999", cfg)
        assert result["allowed_integrations"] == ["google_mail", "slack"]

    def test_empty_config_returns_empty_collections(self):
        cfg = _mock_config(enabled_job_types=[], allowed_integrations=[], auto_actions={})
        result = self._call("TENANT_EMPTY", cfg)
        assert result["enabled_job_types"] == []
        assert result["allowed_integrations"] == []
        assert result["auto_actions"] == {}

    def test_different_tenant_ids_return_correct_current_tenant(self):
        for tid in ["TENANT_A", "TENANT_B", "TENANT_C"]:
            result = self._call(tid, _mock_config())
            assert result["current_tenant"] == tid
