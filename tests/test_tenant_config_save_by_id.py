"""
Tests for PUT /tenant/config/{tenant_id} — unauthenticated tenant config save.

Covers:
  - Saves to the explicitly named tenant (not the API-key tenant)
  - Returns {status: ok, tenant_id} with the path tenant_id
  - 404 when tenant does not exist
  - Accepts automation level strings ('manual', 'semi', 'auto') in auto_actions
  - Upsert called with correct args

Tests call the endpoint function directly with mocked DB sessions,
matching the established pattern in this repo.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


def _mock_db():
    return MagicMock()


def _valid_request(auto_actions=None):
    from app.main import TenantConfigUpdateRequest
    return TenantConfigUpdateRequest(
        enabled_job_types=["lead", "invoice"],
        allowed_integrations=["google_mail"],
        auto_actions=auto_actions or {"lead": "auto", "invoice": "manual"},
    )


class TestUpdateTenantConfigById:
    def _call(self, tenant_id, request, existing_record=MagicMock()):
        from app.main import update_tenant_config_by_id
        db = _mock_db()
        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=existing_record,
        ), patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.upsert",
            return_value=MagicMock(),
        ) as mock_upsert:
            result = update_tenant_config_by_id(tenant_id=tenant_id, request=request, db=db)
            return result, mock_upsert

    def test_returns_ok_status(self):
        result, _ = self._call("TENANT_X", _valid_request())
        assert result["status"] == "ok"

    def test_returns_correct_tenant_id(self):
        result, _ = self._call("TENANT_X", _valid_request())
        assert result["tenant_id"] == "TENANT_X"

    def test_saves_to_explicit_tenant_not_api_key_tenant(self):
        """The path param tenant_id is used, not a derived API-key tenant."""
        result, mock_upsert = self._call("TENANT_OTHER", _valid_request())
        kw = mock_upsert.call_args.kwargs
        assert kw["tenant_id"] == "TENANT_OTHER"

    def test_upsert_receives_correct_job_types(self):
        _, mock_upsert = self._call("TENANT_X", _valid_request())
        kw = mock_upsert.call_args.kwargs
        assert kw["enabled_job_types"] == ["lead", "invoice"]

    def test_upsert_receives_correct_integrations(self):
        _, mock_upsert = self._call("TENANT_X", _valid_request())
        kw = mock_upsert.call_args.kwargs
        assert kw["allowed_integrations"] == ["google_mail"]

    def test_upsert_receives_auto_actions(self):
        _, mock_upsert = self._call("TENANT_X", _valid_request())
        kw = mock_upsert.call_args.kwargs
        assert kw["auto_actions"] == {"lead": "auto", "invoice": "manual"}

    def test_404_when_tenant_does_not_exist(self):
        from app.main import update_tenant_config_by_id
        db = _mock_db()
        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc_info:
                update_tenant_config_by_id(
                    tenant_id="TENANT_MISSING",
                    request=_valid_request(),
                    db=db,
                )
        assert exc_info.value.status_code == 404

    def test_404_detail_mentions_tenant_id(self):
        from app.main import update_tenant_config_by_id
        db = _mock_db()
        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=None,
        ):
            with pytest.raises(HTTPException) as exc_info:
                update_tenant_config_by_id(
                    tenant_id="TENANT_MISSING",
                    request=_valid_request(),
                    db=db,
                )
        assert "TENANT_MISSING" in exc_info.value.detail

    def test_upsert_not_called_when_404(self):
        from app.main import update_tenant_config_by_id
        db = _mock_db()
        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=None,
        ), patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.upsert",
        ) as mock_upsert:
            with pytest.raises(HTTPException):
                update_tenant_config_by_id(
                    tenant_id="TENANT_MISSING",
                    request=_valid_request(),
                    db=db,
                )
        mock_upsert.assert_not_called()


class TestAutomationLevelsInAutoActions:
    """Verify that string automation levels pass through the schema correctly."""

    def test_schema_accepts_string_auto_actions(self):
        from app.main import TenantConfigUpdateRequest
        req = TenantConfigUpdateRequest(
            enabled_job_types=["lead"],
            allowed_integrations=[],
            auto_actions={"lead": "manual"},
        )
        assert req.auto_actions["lead"] == "manual"

    def test_schema_accepts_semi_level(self):
        from app.main import TenantConfigUpdateRequest
        req = TenantConfigUpdateRequest(
            enabled_job_types=["invoice"],
            allowed_integrations=[],
            auto_actions={"invoice": "semi"},
        )
        assert req.auto_actions["invoice"] == "semi"

    def test_schema_accepts_auto_level(self):
        from app.main import TenantConfigUpdateRequest
        req = TenantConfigUpdateRequest(
            enabled_job_types=["lead"],
            allowed_integrations=[],
            auto_actions={"lead": "auto"},
        )
        assert req.auto_actions["lead"] == "auto"

    def test_schema_accepts_bool_for_backwards_compat(self):
        """Existing bool values must still be accepted (schema is dict[str, bool|str] effectively)."""
        from app.main import TenantConfigUpdateRequest
        # Pydantic will coerce bool to bool — just verify no crash.
        req = TenantConfigUpdateRequest(
            enabled_job_types=["lead"],
            allowed_integrations=[],
            auto_actions={"lead": True},
        )
        assert req.auto_actions["lead"] is True

    def test_schema_accepts_mixed_levels(self):
        from app.main import TenantConfigUpdateRequest
        req = TenantConfigUpdateRequest(
            enabled_job_types=["lead", "invoice", "customer_inquiry"],
            allowed_integrations=["google_mail"],
            auto_actions={"lead": "auto", "invoice": "semi", "customer_inquiry": "manual"},
        )
        assert req.auto_actions["lead"] == "auto"
        assert req.auto_actions["invoice"] == "semi"
        assert req.auto_actions["customer_inquiry"] == "manual"
