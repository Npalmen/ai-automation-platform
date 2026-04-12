"""
Tests for the Setup UI slice endpoints.

Covers:
  GET /tenant response shape:
    - includes enabled_job_types (was missing before this slice)
    - normalises allowed_integrations from enum objects to strings
    - includes auto_actions and current_tenant

  PUT /tenant/config:
    - TenantConfigUpdateRequest schema validates required fields
    - upsert is called with correct tenant_id and payload
    - returns {"status": "ok", "tenant_id": ...}

Tests call endpoint functions directly with mocked DB sessions and
mocked get_tenant_config, matching the established pattern in this repo.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.integrations.enums import IntegrationType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db():
    return MagicMock()


def _mock_config(
    name: str = "Test Tenant",
    enabled_job_types: list | None = None,
    allowed_integrations: list | None = None,
    auto_actions: dict | None = None,
) -> dict:
    return {
        "name": name,
        "enabled_job_types": enabled_job_types or ["lead"],
        "allowed_integrations": allowed_integrations or [],
        "auto_actions": auto_actions or {},
    }


# ---------------------------------------------------------------------------
# GET /tenant — response shape
# ---------------------------------------------------------------------------

class TestGetTenantResponseShape:
    """
    Call the tenant_info function directly with a mocked config and DB.
    """

    def _call(self, config: dict) -> dict:
        from app.main import tenant_info
        db = _mock_db()
        with patch("app.main.get_tenant_config", return_value=config):
            # tenant_info(db, tenant_id) — simulate resolved FastAPI deps
            return tenant_info(db=db, tenant_id="TENANT_1001")

    def test_includes_enabled_job_types(self):
        result = self._call(_mock_config(enabled_job_types=["lead", "invoice"]))
        assert "enabled_job_types" in result
        assert "lead" in result["enabled_job_types"]
        assert "invoice" in result["enabled_job_types"]

    def test_enabled_job_types_defaults_to_empty_list(self):
        cfg = _mock_config()
        cfg["enabled_job_types"] = None
        result = self._call(cfg)
        assert result["enabled_job_types"] == []

    def test_normalises_enum_integrations_to_strings(self):
        cfg = _mock_config(
            allowed_integrations=[IntegrationType.GOOGLE_MAIL, IntegrationType.CRM]
        )
        result = self._call(cfg)
        assert "google_mail" in result["allowed_integrations"]
        assert "crm" in result["allowed_integrations"]
        for item in result["allowed_integrations"]:
            assert isinstance(item, str), f"Expected str, got {type(item)}: {item!r}"

    def test_string_integrations_pass_through(self):
        cfg = _mock_config(allowed_integrations=["google_mail", "monday"])
        result = self._call(cfg)
        assert result["allowed_integrations"] == ["google_mail", "monday"]

    def test_includes_auto_actions(self):
        cfg = _mock_config(auto_actions={"lead": True, "invoice": False})
        result = self._call(cfg)
        assert result["auto_actions"]["lead"] is True
        assert result["auto_actions"]["invoice"] is False

    def test_auto_actions_defaults_to_empty_dict(self):
        cfg = _mock_config()
        cfg["auto_actions"] = None
        result = self._call(cfg)
        assert result["auto_actions"] == {}

    def test_current_tenant_in_response(self):
        result = self._call(_mock_config())
        assert result["current_tenant"] == "TENANT_1001"

    def test_name_in_response(self):
        result = self._call(_mock_config(name="My Tenant"))
        assert result["name"] == "My Tenant"


# ---------------------------------------------------------------------------
# PUT /tenant/config — schema and upsert
# ---------------------------------------------------------------------------

class TestPutTenantConfig:
    def _valid_request(self):
        from app.main import TenantConfigUpdateRequest
        return TenantConfigUpdateRequest(
            enabled_job_types=["lead", "invoice"],
            allowed_integrations=["google_mail", "crm"],
            auto_actions={"lead": True, "invoice": False},
        )

    def test_schema_accepts_valid_body(self):
        req = self._valid_request()
        assert req.enabled_job_types == ["lead", "invoice"]
        assert req.allowed_integrations == ["google_mail", "crm"]
        assert req.auto_actions == {"lead": True, "invoice": False}

    def test_schema_requires_enabled_job_types(self):
        from pydantic import ValidationError
        from app.main import TenantConfigUpdateRequest
        with pytest.raises(ValidationError):
            TenantConfigUpdateRequest(
                allowed_integrations=["google_mail"],
                auto_actions={},
            )

    def test_schema_requires_allowed_integrations(self):
        from pydantic import ValidationError
        from app.main import TenantConfigUpdateRequest
        with pytest.raises(ValidationError):
            TenantConfigUpdateRequest(
                enabled_job_types=["lead"],
                auto_actions={},
            )

    def test_schema_requires_auto_actions(self):
        from pydantic import ValidationError
        from app.main import TenantConfigUpdateRequest
        with pytest.raises(ValidationError):
            TenantConfigUpdateRequest(
                enabled_job_types=["lead"],
                allowed_integrations=["google_mail"],
            )

    def test_schema_accepts_empty_collections(self):
        from app.main import TenantConfigUpdateRequest
        req = TenantConfigUpdateRequest(
            enabled_job_types=[],
            allowed_integrations=[],
            auto_actions={},
        )
        assert req.enabled_job_types == []
        assert req.allowed_integrations == []
        assert req.auto_actions == {}

    def test_upsert_called_with_correct_args(self):
        from app.main import update_tenant_config
        db = _mock_db()
        req = self._valid_request()

        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.upsert"
        ) as mock_upsert:
            mock_upsert.return_value = MagicMock()
            update_tenant_config(request=req, db=db, tenant_id="TENANT_1001")

        mock_upsert.assert_called_once()
        kw = mock_upsert.call_args.kwargs
        assert kw["tenant_id"] == "TENANT_1001"
        assert kw["enabled_job_types"] == ["lead", "invoice"]
        assert kw["allowed_integrations"] == ["google_mail", "crm"]
        assert kw["auto_actions"] == {"lead": True, "invoice": False}

    def test_returns_ok_with_tenant_id(self):
        from app.main import update_tenant_config
        db = _mock_db()
        req = self._valid_request()

        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.upsert",
            return_value=MagicMock(),
        ):
            result = update_tenant_config(request=req, db=db, tenant_id="TENANT_2001")

        assert result["status"] == "ok"
        assert result["tenant_id"] == "TENANT_2001"
