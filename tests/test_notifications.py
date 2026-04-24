"""Tests for GET/PUT /notifications/settings and POST /notifications/daily-digest/send."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


# ── helpers ───────────────────────────────────────────────────────────────────

def _get(tenant_id: str = "T1", stored: dict | None = None):
    from app.main import get_notification_settings

    db = MagicMock()
    with patch(
        "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
        return_value=stored or {},
    ):
        return get_notification_settings(db=db, tenant_id=tenant_id)


def _put(body: dict, tenant_id: str = "T1", existing_ctrl: dict | None = None):
    from app.main import put_notification_settings, NotificationSettingsRequest

    db = MagicMock()
    request = NotificationSettingsRequest(**body)
    with (
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value=existing_ctrl or {},
        ),
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings",
        ) as mock_save,
    ):
        result = put_notification_settings(request=request, db=db, tenant_id=tenant_id)
        return result, mock_save


def _send(
    tenant_id: str = "T1",
    stored_notif: dict | None = None,
    summary: dict | None = None,
    roi: dict | None = None,
    dispatch_raises: Exception | None = None,
):
    from app.main import send_daily_digest

    db = MagicMock()
    ctrl = {"notifications": stored_notif} if stored_notif else {}

    _summary = summary or {
        "leads_today": 2, "inquiries_today": 1, "invoices_today": 0,
        "waiting_customer": 1, "ready_cases": 2, "completed_today": 3,
    }
    _roi = roi or {
        "estimated_hours_saved": 0.5, "estimated_value_sek": 250,
    }

    with (
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value=ctrl,
        ),
        patch("app.main._compute_summary", return_value=_summary),
        patch("app.main._compute_roi", return_value=_roi),
        patch(
            "app.main.dispatch_action",
            side_effect=dispatch_raises if dispatch_raises else None,
        ) as mock_dispatch,
    ):
        result = send_daily_digest(db=db, tenant_id=tenant_id)
        return result, mock_dispatch


def _send_expect_error(tenant_id: str = "T1", stored_notif: dict | None = None):
    from app.main import send_daily_digest

    db = MagicMock()
    ctrl = {"notifications": stored_notif} if stored_notif else {}

    with (
        patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value=ctrl,
        ),
        patch("app.main._compute_summary", return_value={}),
        patch("app.main._compute_roi", return_value={}),
        patch("app.main.dispatch_action"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            send_daily_digest(db=db, tenant_id=tenant_id)
        return exc_info.value


# ══════════════════════════════════════════════════════════════════════════════
# GET /notifications/settings — shape and defaults
# ══════════════════════════════════════════════════════════════════════════════

class TestGetNotificationSettings:
    def test_returns_all_required_keys(self):
        r = _get()
        for key in ("enabled", "recipient_email", "frequency", "send_hour"):
            assert key in r, f"Missing: {key}"

    def test_default_enabled_false(self):
        assert _get()["enabled"] is False

    def test_default_recipient_email_empty(self):
        assert _get()["recipient_email"] == ""

    def test_default_frequency_daily(self):
        assert _get()["frequency"] == "daily"

    def test_default_send_hour_8(self):
        assert _get()["send_hour"] == 8

    def test_stored_values_returned(self):
        stored = {"notifications": {
            "enabled": True, "recipient_email": "ops@x.com",
            "frequency": "weekly", "send_hour": 9,
        }}
        r = _get(stored=stored)
        assert r["enabled"] is True
        assert r["recipient_email"] == "ops@x.com"
        assert r["frequency"] == "weekly"
        assert r["send_hour"] == 9


# ══════════════════════════════════════════════════════════════════════════════
# PUT /notifications/settings — persists and validates
# ══════════════════════════════════════════════════════════════════════════════

class TestPutNotificationSettings:
    def test_persists_enabled_and_email(self):
        body = {"enabled": True, "recipient_email": "ops@ex.com",
                "frequency": "daily", "send_hour": 7}
        result, mock_save = _put(body)
        assert result["enabled"] is True
        assert result["recipient_email"] == "ops@ex.com"

    def test_upsert_called_with_notifications_key(self):
        body = {"enabled": True, "recipient_email": "a@b.com",
                "frequency": "daily", "send_hour": 8}
        _, mock_save = _put(body)
        saved_settings = mock_save.call_args[0][2]
        assert "notifications" in saved_settings

    def test_response_reflects_saved_values(self):
        body = {"enabled": False, "recipient_email": "",
                "frequency": "off", "send_hour": 0}
        result, _ = _put(body)
        assert result["enabled"] is False
        assert result["frequency"] == "off"
        assert result["send_hour"] == 0

    def test_all_valid_frequencies_accepted(self):
        for freq in ("daily", "weekly", "off"):
            body = {"enabled": False, "recipient_email": "",
                    "frequency": freq, "send_hour": 8}
            result, _ = _put(body)
            assert result["frequency"] == freq

    def test_send_hour_boundaries_accepted(self):
        for hour in (0, 12, 23):
            body = {"enabled": False, "recipient_email": "",
                    "frequency": "daily", "send_hour": hour}
            result, _ = _put(body)
            assert result["send_hour"] == hour

    def test_disabled_allows_empty_email(self):
        body = {"enabled": False, "recipient_email": "",
                "frequency": "daily", "send_hour": 8}
        result, _ = _put(body)
        assert result["recipient_email"] == ""


class TestPutNotificationSettingsValidation:
    def _put_422(self, body: dict) -> str:
        with pytest.raises(HTTPException) as exc_info:
            _put(body)
        assert exc_info.value.status_code == 422
        return exc_info.value.detail

    def test_invalid_frequency_rejected(self):
        body = {"enabled": False, "recipient_email": "",
                "frequency": "monthly", "send_hour": 8}
        detail = self._put_422(body)
        assert "frequency" in detail

    def test_send_hour_negative_rejected(self):
        body = {"enabled": False, "recipient_email": "",
                "frequency": "daily", "send_hour": -1}
        detail = self._put_422(body)
        assert "send_hour" in detail

    def test_send_hour_24_rejected(self):
        body = {"enabled": False, "recipient_email": "",
                "frequency": "daily", "send_hour": 24}
        self._put_422(body)

    def test_enabled_requires_email(self):
        body = {"enabled": True, "recipient_email": "",
                "frequency": "daily", "send_hour": 8}
        detail = self._put_422(body)
        assert "recipient_email" in detail

    def test_invalid_email_format_rejected(self):
        body = {"enabled": True, "recipient_email": "not-an-email",
                "frequency": "daily", "send_hour": 8}
        detail = self._put_422(body)
        assert "email" in detail.lower()

    def test_valid_email_accepted(self):
        body = {"enabled": True, "recipient_email": "ops@company.com",
                "frequency": "daily", "send_hour": 8}
        result, _ = _put(body)
        assert result["recipient_email"] == "ops@company.com"


# ══════════════════════════════════════════════════════════════════════════════
# POST /notifications/daily-digest/send — success
# ══════════════════════════════════════════════════════════════════════════════

class TestSendDailyDigest:
    def test_returns_success_status(self):
        notif = {"enabled": True, "recipient_email": "ops@x.com",
                 "frequency": "daily", "send_hour": 8}
        result, _ = _send(stored_notif=notif)
        assert result["status"] == "success"

    def test_returns_recipient(self):
        notif = {"enabled": True, "recipient_email": "ops@x.com"}
        result, _ = _send(stored_notif=notif)
        assert result["recipient"] == "ops@x.com"

    def test_returns_subject(self):
        notif = {"recipient_email": "ops@x.com"}
        result, _ = _send(stored_notif=notif)
        assert "subject" in result
        assert isinstance(result["subject"], str)

    def test_returns_message(self):
        notif = {"recipient_email": "ops@x.com"}
        result, _ = _send(stored_notif=notif)
        assert "message" in result

    def test_dispatch_action_called_once(self):
        notif = {"recipient_email": "ops@x.com"}
        _, mock_dispatch = _send(stored_notif=notif)
        mock_dispatch.assert_called_once()

    def test_dispatch_sends_to_correct_recipient(self):
        notif = {"recipient_email": "ceo@company.com"}
        _, mock_dispatch = _send(stored_notif=notif)
        call_arg = mock_dispatch.call_args[0][0]
        assert call_arg["to"] == "ceo@company.com"

    def test_dispatch_action_type_send_email(self):
        notif = {"recipient_email": "ops@x.com"}
        _, mock_dispatch = _send(stored_notif=notif)
        call_arg = mock_dispatch.call_args[0][0]
        assert call_arg["type"] == "send_email"

    def test_body_contains_summary_values(self):
        notif = {"recipient_email": "ops@x.com"}
        summary = {"leads_today": 5, "inquiries_today": 3, "invoices_today": 2,
                   "waiting_customer": 1, "ready_cases": 4, "completed_today": 7}
        _, mock_dispatch = _send(stored_notif=notif, summary=summary)
        body = mock_dispatch.call_args[0][0]["body"]
        assert "5" in body  # leads
        assert "3" in body  # inquiries
        assert "2" in body  # invoices

    def test_body_contains_roi_values(self):
        notif = {"recipient_email": "ops@x.com"}
        roi = {"estimated_hours_saved": 2.5, "estimated_value_sek": 1250}
        _, mock_dispatch = _send(stored_notif=notif, roi=roi)
        body = mock_dispatch.call_args[0][0]["body"]
        assert "2.5" in body
        assert "1250" in body

    def test_subject_contains_report_keyword(self):
        notif = {"recipient_email": "ops@x.com"}
        result, _ = _send(stored_notif=notif)
        assert "AI Automation Report" in result["subject"] or "rapport" in result["subject"].lower()


# ══════════════════════════════════════════════════════════════════════════════
# Missing recipient → 400
# ══════════════════════════════════════════════════════════════════════════════

class TestSendDailyDigestMissingRecipient:
    def test_no_settings_returns_400(self):
        exc = _send_expect_error()
        assert exc.status_code == 400

    def test_empty_recipient_returns_400(self):
        exc = _send_expect_error(stored_notif={"recipient_email": ""})
        assert exc.status_code == 400

    def test_400_detail_has_status_failed(self):
        exc = _send_expect_error()
        assert exc.detail["status"] == "failed"

    def test_400_detail_has_message(self):
        exc = _send_expect_error()
        assert "message" in exc.detail


# ══════════════════════════════════════════════════════════════════════════════
# Dispatch failure → 500
# ══════════════════════════════════════════════════════════════════════════════

class TestSendDailyDigestDispatchFails:
    def test_dispatch_exception_raises_500(self):
        notif = {"recipient_email": "ops@x.com"}
        with pytest.raises(HTTPException) as exc_info:
            _send(stored_notif=notif, dispatch_raises=RuntimeError("SMTP error"))
        assert exc_info.value.status_code == 500

    def test_500_detail_status_failed(self):
        notif = {"recipient_email": "ops@x.com"}
        with pytest.raises(HTTPException) as exc_info:
            _send(stored_notif=notif, dispatch_raises=RuntimeError("timeout"))
        assert exc_info.value.detail["status"] == "failed"


# ══════════════════════════════════════════════════════════════════════════════
# Tenant isolation
# ══════════════════════════════════════════════════════════════════════════════

class TestNotificationTenantIsolation:
    def test_get_settings_passes_tenant_id(self):
        from app.main import get_notification_settings

        db = MagicMock()
        with patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value={},
        ) as mock_get:
            get_notification_settings(db=db, tenant_id="TENANT_XYZ")
            mock_get.assert_called_once_with(db, "TENANT_XYZ")

    def test_put_settings_persists_to_correct_tenant(self):
        from app.main import put_notification_settings, NotificationSettingsRequest

        db = MagicMock()
        req = NotificationSettingsRequest(
            enabled=False, recipient_email="", frequency="daily", send_hour=8,
        )
        with (
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
                return_value={},
            ),
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.update_settings",
            ) as mock_save,
        ):
            put_notification_settings(request=req, db=db, tenant_id="TENANT_ABC")
            assert mock_save.call_args[0][1] == "TENANT_ABC"
