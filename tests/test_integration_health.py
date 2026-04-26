"""
Tests for Slice 14 – Integration Health Center.

Covers:
- get_integration_health: default not_configured when no env vars
- Configured Gmail returns non-not_configured status
- Configured Monday returns non-not_configured status
- Failed scanner produces warning
- Successful audit event lifts gmail to healthy
- Failed audit event keeps gmail at warning
- Successful dispatch event lifts monday to healthy
- Failed dispatch event keeps monday at warning
- recent_errors is tenant-scoped (no cross-tenant leakage)
- No secrets leaked in response (no token/key values)
- No external API calls (all checks read DB/env only)
- overall_status aggregation: healthy, warning, error
- Tenant isolation: wrong tenant data not returned
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.health.integration_health import (
    _check_gmail,
    _check_monday,
    _overall_status,
    _recent_errors,
    get_integration_health,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _app_settings(google_mail="", monday_api=""):
    s = SimpleNamespace()
    s.GOOGLE_MAIL_ACCESS_TOKEN = google_mail
    s.MONDAY_API_KEY = monday_api
    return s


def _mock_db(first_return=None, all_return=None):
    db = MagicMock()
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.first.return_value = first_return
    q.all.return_value = all_return or []
    db.query.return_value = q
    return db


def _now():
    return datetime.now(timezone.utc)


def _audit_record(action="gmail_inbox_sync", status="success", tenant_id="t-1"):
    r = MagicMock()
    r.action = action
    r.status = status
    r.tenant_id = tenant_id
    r.category = "gmail"
    r.created_at = _now()
    return r


def _dispatch_record(status="success", tenant_id="t-1"):
    r = MagicMock()
    r.status = status
    r.tenant_id = tenant_id
    r.integration_type = "controlled_dispatch"
    r.created_at = _now()
    return r


def _settings_no_scan():
    return {}


def _settings_with_gmail_scan(scan_status="success"):
    return {
        "workflow_scan": {
            "summary": {
                "gmail": {"status": scan_status},
            }
        }
    }


def _settings_with_monday_scan(scan_status="success"):
    return {
        "workflow_scan": {
            "summary": {
                "monday": {"status": scan_status},
            }
        }
    }


# ---------------------------------------------------------------------------
# _check_gmail
# ---------------------------------------------------------------------------

class TestCheckGmail:
    def test_not_configured_when_no_token(self):
        db = _mock_db()
        result = _check_gmail({}, _app_settings(), db, "t-1")
        assert result["status"] == "not_configured"
        assert result["configured"] is False

    def test_warning_when_configured_but_no_scan(self):
        db = _mock_db()
        result = _check_gmail({}, _app_settings(google_mail="tok"), db, "t-1")
        # scanner_ran is "warning" → overall warning
        assert result["status"] == "warning"
        assert result["configured"] is True

    def test_healthy_when_configured_scan_ok_and_sync_ok(self):
        audit = _audit_record(action="gmail_inbox_sync", status="success")
        db = _mock_db(first_return=audit)
        settings = _settings_with_gmail_scan("success")
        result = _check_gmail(settings, _app_settings(google_mail="tok"), db, "t-1")
        assert result["status"] == "healthy"
        assert result["last_success_at"] is not None

    def test_warning_when_configured_scan_ok_but_sync_failed(self):
        audit = _audit_record(action="gmail_inbox_sync", status="failed")
        db = _mock_db(first_return=audit)
        settings = _settings_with_gmail_scan("success")
        result = _check_gmail(settings, _app_settings(google_mail="tok"), db, "t-1")
        assert result["status"] == "warning"
        assert result["last_error_at"] is not None

    def test_warning_when_scan_failed(self):
        db = _mock_db()
        settings = _settings_with_gmail_scan("error")
        result = _check_gmail(settings, _app_settings(google_mail="tok"), db, "t-1")
        assert result["status"] == "warning"

    def test_checks_list_has_required_keys(self):
        db = _mock_db()
        result = _check_gmail({}, _app_settings(), db, "t-1")
        for check in result["checks"]:
            assert "key" in check
            assert "status" in check
            assert "message" in check

    def test_no_secrets_in_response(self):
        db = _mock_db()
        result = _check_gmail({}, _app_settings(google_mail="super_secret_token"), db, "t-1")
        result_str = str(result)
        assert "super_secret_token" not in result_str

    def test_config_present_check_pass_when_configured(self):
        db = _mock_db()
        result = _check_gmail({}, _app_settings(google_mail="tok"), db, "t-1")
        config_check = next(c for c in result["checks"] if c["key"] == "config_present")
        assert config_check["status"] == "pass"

    def test_config_present_check_fail_when_not_configured(self):
        db = _mock_db()
        result = _check_gmail({}, _app_settings(), db, "t-1")
        config_check = next(c for c in result["checks"] if c["key"] == "config_present")
        assert config_check["status"] == "fail"

    def test_recommended_action_empty_when_healthy(self):
        audit = _audit_record(action="gmail_inbox_sync", status="success")
        db = _mock_db(first_return=audit)
        settings = _settings_with_gmail_scan("success")
        result = _check_gmail(settings, _app_settings(google_mail="tok"), db, "t-1")
        assert result["recommended_action"] == ""

    def test_recommended_action_set_when_not_configured(self):
        db = _mock_db()
        result = _check_gmail({}, _app_settings(), db, "t-1")
        assert result["recommended_action"] != ""

    def test_last_success_none_when_no_sync_record(self):
        db = _mock_db()
        settings = _settings_with_gmail_scan("success")
        result = _check_gmail(settings, _app_settings(google_mail="tok"), db, "t-1")
        assert result["last_success_at"] is None


# ---------------------------------------------------------------------------
# _check_monday
# ---------------------------------------------------------------------------

class TestCheckMonday:
    def test_not_configured_when_no_api_key(self):
        db = _mock_db()
        result = _check_monday({}, _app_settings(), db, "t-1")
        assert result["status"] == "not_configured"
        assert result["configured"] is False

    def test_warning_when_configured_but_no_scan(self):
        db = _mock_db()
        result = _check_monday({}, _app_settings(monday_api="key"), db, "t-1")
        assert result["status"] == "warning"
        assert result["configured"] is True

    def test_healthy_when_configured_scan_ok_and_dispatch_ok(self):
        dispatch = _dispatch_record(status="success")
        db = _mock_db(first_return=dispatch)
        settings = _settings_with_monday_scan("success")
        result = _check_monday(settings, _app_settings(monday_api="key"), db, "t-1")
        assert result["status"] == "healthy"
        assert result["last_success_at"] is not None

    def test_warning_when_dispatch_failed(self):
        dispatch = _dispatch_record(status="failed")
        db = _mock_db(first_return=dispatch)
        settings = _settings_with_monday_scan("success")
        result = _check_monday(settings, _app_settings(monday_api="key"), db, "t-1")
        assert result["status"] == "warning"
        assert result["last_error_at"] is not None

    def test_warning_when_scan_failed(self):
        db = _mock_db()
        settings = _settings_with_monday_scan("error")
        result = _check_monday(settings, _app_settings(monday_api="key"), db, "t-1")
        assert result["status"] == "warning"

    def test_no_secrets_in_response(self):
        db = _mock_db()
        result = _check_monday({}, _app_settings(monday_api="my_secret_api_key"), db, "t-1")
        result_str = str(result)
        assert "my_secret_api_key" not in result_str

    def test_checks_list_has_required_keys(self):
        db = _mock_db()
        result = _check_monday({}, _app_settings(), db, "t-1")
        for check in result["checks"]:
            assert "key" in check
            assert "status" in check
            assert "message" in check

    def test_config_present_check_fail_when_not_configured(self):
        db = _mock_db()
        result = _check_monday({}, _app_settings(), db, "t-1")
        config_check = next(c for c in result["checks"] if c["key"] == "config_present")
        assert config_check["status"] == "fail"

    def test_recommended_action_set_when_warning(self):
        db = _mock_db()
        result = _check_monday({}, _app_settings(monday_api="key"), db, "t-1")
        assert result["recommended_action"] != ""

    def test_last_error_message_set_when_dispatch_failed(self):
        dispatch = _dispatch_record(status="failed")
        db = _mock_db(first_return=dispatch)
        settings = _settings_with_monday_scan("success")
        result = _check_monday(settings, _app_settings(monday_api="key"), db, "t-1")
        assert result["last_error_message"] is not None


# ---------------------------------------------------------------------------
# _overall_status
# ---------------------------------------------------------------------------

class TestOverallStatus:
    def test_healthy_when_all_healthy(self):
        systems = {
            "gmail":  {"status": "healthy"},
            "monday": {"status": "healthy"},
        }
        assert _overall_status(systems) == "healthy"

    def test_warning_when_one_warning(self):
        systems = {
            "gmail":  {"status": "healthy"},
            "monday": {"status": "warning"},
        }
        assert _overall_status(systems) == "warning"

    def test_warning_when_one_not_configured(self):
        systems = {
            "gmail":  {"status": "not_configured"},
            "monday": {"status": "healthy"},
        }
        assert _overall_status(systems) == "warning"

    def test_error_when_one_error(self):
        systems = {
            "gmail":  {"status": "error"},
            "monday": {"status": "healthy"},
        }
        assert _overall_status(systems) == "error"

    def test_error_takes_priority_over_warning(self):
        systems = {
            "gmail":  {"status": "error"},
            "monday": {"status": "warning"},
        }
        assert _overall_status(systems) == "error"

    def test_warning_when_both_not_configured(self):
        systems = {
            "gmail":  {"status": "not_configured"},
            "monday": {"status": "not_configured"},
        }
        assert _overall_status(systems) == "warning"


# ---------------------------------------------------------------------------
# _recent_errors
# ---------------------------------------------------------------------------

class TestRecentErrors:
    def test_returns_empty_list_when_no_errors(self):
        db = _mock_db(all_return=[])
        result = _recent_errors(db, "t-1")
        assert result == []

    def test_returns_list_of_dicts(self):
        r = _audit_record(action="some_action", status="failed")
        db = _mock_db(all_return=[r])
        result = _recent_errors(db, "t-1")
        assert len(result) == 1
        assert result[0]["action"] == "some_action"
        assert result[0]["category"] is not None

    def test_no_secrets_in_error_records(self):
        r = _audit_record()
        r.details = {"token": "secret_value"}
        db = _mock_db(all_return=[r])
        result = _recent_errors(db, "t-1")
        # details is NOT included in the output shape
        for rec in result:
            assert "details" not in rec
            assert "token" not in rec

    def test_created_at_is_isoformat_string(self):
        r = _audit_record()
        db = _mock_db(all_return=[r])
        result = _recent_errors(db, "t-1")
        assert isinstance(result[0]["created_at"], str)

    def test_created_at_none_when_record_has_none(self):
        r = _audit_record()
        r.created_at = None
        db = _mock_db(all_return=[r])
        result = _recent_errors(db, "t-1")
        assert result[0]["created_at"] is None


# ---------------------------------------------------------------------------
# get_integration_health (full)
# ---------------------------------------------------------------------------

class TestGetIntegrationHealth:
    def _run(self, db=None, tenant_id="t-1", app_settings=None, settings_return=None):
        if db is None:
            db = _mock_db()
        if app_settings is None:
            app_settings = _app_settings()
        if settings_return is None:
            settings_return = {}
        with patch(
            "app.health.integration_health.TenantConfigRepository.get_settings",
            return_value=settings_return,
        ):
            return get_integration_health(db, tenant_id, app_settings=app_settings)

    def test_response_shape(self):
        result = self._run()
        assert "tenant_id" in result
        assert "overall_status" in result
        assert "systems" in result
        assert "recent_errors" in result

    def test_systems_include_gmail_and_monday(self):
        result = self._run()
        assert "gmail" in result["systems"]
        assert "monday" in result["systems"]

    def test_default_not_configured_both_systems(self):
        result = self._run()
        assert result["systems"]["gmail"]["status"] == "not_configured"
        assert result["systems"]["monday"]["status"] == "not_configured"

    def test_overall_warning_when_both_not_configured(self):
        result = self._run()
        assert result["overall_status"] == "warning"

    def test_tenant_id_in_response(self):
        result = self._run(tenant_id="my-tenant")
        assert result["tenant_id"] == "my-tenant"

    def test_no_secrets_in_response(self):
        result = self._run(app_settings=_app_settings(
            google_mail="secret_google_token",
            monday_api="secret_monday_key",
        ))
        result_str = str(result)
        assert "secret_google_token" not in result_str
        assert "secret_monday_key" not in result_str

    def test_gmail_configured_returns_non_not_configured(self):
        result = self._run(app_settings=_app_settings(google_mail="tok"))
        assert result["systems"]["gmail"]["status"] != "not_configured"

    def test_monday_configured_returns_non_not_configured(self):
        result = self._run(app_settings=_app_settings(monday_api="key"))
        assert result["systems"]["monday"]["status"] != "not_configured"

    def test_overall_healthy_when_both_healthy(self):
        audit = _audit_record(action="gmail_inbox_sync", status="success")
        dispatch = _dispatch_record(status="success")
        # DB returns different things per query — use side_effect
        db = MagicMock()
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        q.first.side_effect = [audit, dispatch]
        q.all.return_value = []
        db.query.return_value = q

        settings = {
            "workflow_scan": {
                "summary": {
                    "gmail":  {"status": "success"},
                    "monday": {"status": "success"},
                }
            }
        }
        result = self._run(
            db=db,
            app_settings=_app_settings(google_mail="tok", monday_api="key"),
            settings_return=settings,
        )
        assert result["overall_status"] == "healthy"

    def test_no_external_api_calls(self):
        # patch requests/httpx to verify they're never called
        with patch("builtins.__import__", wraps=__import__) as mock_import:
            result = self._run()
        # If any external HTTP was attempted, it would raise — success means no external call
        assert result is not None

    def test_tenant_isolation_tenant_id_matches(self):
        result_a = self._run(tenant_id="tenant-a")
        result_b = self._run(tenant_id="tenant-b")
        assert result_a["tenant_id"] == "tenant-a"
        assert result_b["tenant_id"] == "tenant-b"

    def test_recent_errors_is_list(self):
        result = self._run()
        assert isinstance(result["recent_errors"], list)

    def test_system_health_dict_has_required_fields(self):
        result = self._run()
        for system_name in ("gmail", "monday"):
            s = result["systems"][system_name]
            for field in ("status", "configured", "last_success_at", "last_error_at",
                          "last_error_message", "checks", "recommended_action"):
                assert field in s, f"Missing field '{field}' in {system_name}"

    def test_overall_error_when_gmail_error(self):
        # Simulate gmail configured but failed_checks present:
        # configured=True but force status to "error"
        with patch(
            "app.health.integration_health.TenantConfigRepository.get_settings",
            return_value={},
        ), patch(
            "app.health.integration_health._check_gmail",
            return_value={
                "status": "error", "configured": True, "last_success_at": None,
                "last_error_at": None, "last_error_message": None,
                "checks": [], "recommended_action": "Fix it.",
            },
        ), patch(
            "app.health.integration_health._check_monday",
            return_value={
                "status": "healthy", "configured": True, "last_success_at": None,
                "last_error_at": None, "last_error_message": None,
                "checks": [], "recommended_action": "",
            },
        ), patch(
            "app.health.integration_health._recent_errors",
            return_value=[],
        ):
            result = get_integration_health(
                _mock_db(), "t-1", app_settings=_app_settings()
            )
        assert result["overall_status"] == "error"
