"""Tests for GET/PUT /dashboard/control and POST /dashboard/inbox-sync.

Uses direct function calls with mocked DB — consistent with repo test pattern.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_db(stored_settings: dict | None = None):
    """Return a mocked DB whose TenantConfigRepository returns stored_settings."""
    db = MagicMock()
    return db


def _get(tenant_id: str = "T1", stored_settings: dict | None = None):
    from app.main import get_control_panel

    db = MagicMock()
    with patch(
        "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
        return_value=stored_settings or {},
    ):
        return get_control_panel(db=db, tenant_id=tenant_id)


def _put(body: dict, tenant_id: str = "T1", stored_settings: dict | None = None):
    from app.main import put_control_panel, ControlPanelRequest

    db = MagicMock()
    request = ControlPanelRequest(**body)
    with (
        patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings", return_value=stored_settings or {}),
        patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings") as mock_save,
    ):
        result = put_control_panel(request=request, db=db, tenant_id=tenant_id)
        return result, mock_save


def _post_sync(tenant_id: str = "T1"):
    from app.main import trigger_inbox_sync

    db = MagicMock()
    return trigger_inbox_sync(db=db, tenant_id=tenant_id)


# ══════════════════════════════════════════════════════════════════════════════
# GET /dashboard/control — shape
# ══════════════════════════════════════════════════════════════════════════════

class TestGetControlShape:
    def test_returns_all_required_keys(self):
        r = _get()
        assert "automation" in r
        assert "support_email" in r
        assert "scheduler" in r

    def test_automation_has_all_flags(self):
        auto = _get()["automation"]
        assert "leads_enabled" in auto
        assert "support_enabled" in auto
        assert "invoices_enabled" in auto
        assert "followups_enabled" in auto

    def test_scheduler_has_run_mode(self):
        assert "run_mode" in _get()["scheduler"]

    def test_defaults_all_enabled(self):
        auto = _get()["automation"]
        assert auto["leads_enabled"] is True
        assert auto["support_enabled"] is True
        assert auto["invoices_enabled"] is True
        assert auto["followups_enabled"] is True

    def test_default_run_mode_is_manual(self):
        assert _get()["scheduler"]["run_mode"] == "manual"

    def test_default_support_email_empty(self):
        assert _get()["support_email"] == ""


# ══════════════════════════════════════════════════════════════════════════════
# GET — stored settings returned correctly
# ══════════════════════════════════════════════════════════════════════════════

class TestGetControlStoredSettings:
    def test_persisted_booleans_returned(self):
        stored = {
            "automation": {
                "leads_enabled": False,
                "support_enabled": True,
                "invoices_enabled": False,
                "followups_enabled": True,
            },
            "support_email": "ops@example.com",
            "scheduler": {"run_mode": "paused"},
        }
        r = _get(stored_settings=stored)
        assert r["automation"]["leads_enabled"] is False
        assert r["automation"]["invoices_enabled"] is False
        assert r["support_email"] == "ops@example.com"
        assert r["scheduler"]["run_mode"] == "paused"

    def test_partial_settings_use_defaults_for_missing_keys(self):
        stored = {"automation": {"leads_enabled": False}}
        r = _get(stored_settings=stored)
        assert r["automation"]["leads_enabled"] is False
        assert r["automation"]["support_enabled"] is True  # default


# ══════════════════════════════════════════════════════════════════════════════
# PUT /dashboard/control — persists correctly
# ══════════════════════════════════════════════════════════════════════════════

class TestPutControl:
    def test_persists_automation_flags(self):
        body = {
            "automation": {
                "leads_enabled": False,
                "support_enabled": True,
                "invoices_enabled": False,
                "followups_enabled": True,
            },
            "support_email": "help@company.com",
            "scheduler": {"run_mode": "scheduled"},
        }
        result, mock_save = _put(body)
        mock_save.assert_called_once()
        saved = mock_save.call_args[0][2]  # positional: db, tenant_id, settings
        assert saved["automation"]["leads_enabled"] is False
        assert saved["automation"]["invoices_enabled"] is False
        assert saved["scheduler"]["run_mode"] == "scheduled"
        assert saved["support_email"] == "help@company.com"

    def test_response_reflects_saved_values(self):
        body = {
            "automation": {"leads_enabled": False, "support_enabled": False,
                           "invoices_enabled": True, "followups_enabled": True},
            "support_email": "x@y.com",
            "scheduler": {"run_mode": "paused"},
        }
        result, _ = _put(body)
        assert result["automation"]["leads_enabled"] is False
        assert result["scheduler"]["run_mode"] == "paused"

    def test_empty_support_email_accepted(self):
        body = {"automation": {}, "support_email": "", "scheduler": {"run_mode": "manual"}}
        result, mock_save = _put(body)
        saved = mock_save.call_args[0][2]
        assert saved["support_email"] == ""

    def test_null_support_email_stored_as_empty(self):
        body = {"automation": {}, "support_email": None, "scheduler": {"run_mode": "manual"}}
        result, mock_save = _put(body)
        saved = mock_save.call_args[0][2]
        assert saved["support_email"] == ""


# ══════════════════════════════════════════════════════════════════════════════
# PUT — validation
# ══════════════════════════════════════════════════════════════════════════════

class TestPutControlValidation:
    def _put_expect_422(self, body: dict) -> str:
        from fastapi import HTTPException
        import pytest
        with pytest.raises(HTTPException) as exc_info:
            _put(body)
        assert exc_info.value.status_code == 422
        return exc_info.value.detail

    def test_invalid_run_mode_rejected(self):
        body = {"automation": {}, "support_email": None, "scheduler": {"run_mode": "auto"}}
        detail = self._put_expect_422(body)
        assert "run_mode" in detail

    def test_all_valid_run_modes_accepted(self):
        for mode in ("manual", "scheduled", "paused"):
            body = {"automation": {}, "support_email": None, "scheduler": {"run_mode": mode}}
            result, _ = _put(body)
            assert result["scheduler"]["run_mode"] == mode

    def test_invalid_email_rejected(self):
        body = {"automation": {}, "support_email": "not-an-email", "scheduler": {"run_mode": "manual"}}
        detail = self._put_expect_422(body)
        assert "email" in detail.lower()

    def test_valid_email_accepted(self):
        body = {"automation": {}, "support_email": "ops@example.com", "scheduler": {"run_mode": "manual"}}
        result, _ = _put(body)
        assert result["support_email"] == "ops@example.com"


# ══════════════════════════════════════════════════════════════════════════════
# Tenant isolation
# ══════════════════════════════════════════════════════════════════════════════

class TestControlTenantIsolation:
    def test_get_passes_tenant_id_to_repository(self):
        from app.main import get_control_panel

        db = MagicMock()
        with patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings", return_value={}) as mock_get:
            get_control_panel(db=db, tenant_id="TENANT_XYZ")
            mock_get.assert_called_once_with(db, "TENANT_XYZ")

    def test_put_passes_tenant_id_to_repository(self):
        from app.main import put_control_panel, ControlPanelRequest

        db = MagicMock()
        request = ControlPanelRequest()
        with (
            patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings", return_value={}),
            patch("app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings") as mock_save,
        ):
            put_control_panel(request=request, db=db, tenant_id="TENANT_ABC")
            assert mock_save.call_args[0][1] == "TENANT_ABC"


# ══════════════════════════════════════════════════════════════════════════════
# POST /dashboard/inbox-sync
# ══════════════════════════════════════════════════════════════════════════════

class TestInboxSync:
    def test_returns_not_available_status(self):
        r = _post_sync()
        assert r["status"] == "not_available"

    def test_returns_message(self):
        r = _post_sync()
        assert "message" in r
        assert isinstance(r["message"], str)
        assert len(r["message"]) > 0

    def test_message_mentions_process_inbox(self):
        r = _post_sync()
        assert "process-inbox" in r["message"]
