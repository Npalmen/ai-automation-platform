"""
Tests for Production Alerting Engine (Slice 3).

Covers:
- Alert disabled when config.enabled=False
- Alert skipped when no recipient configured
- repeated_failed_jobs alert fires above threshold
- repeated_failed_jobs alert skipped below threshold
- gmail_oauth_failure alert fires on recent failed audit event
- scheduler_failure alert fires when last_status=failed
- repeated_dispatch_failures alert fires above threshold
- stale_approvals alert fires when pending > threshold hours
- integration_health_critical alert fires on error status
- Dedup: alert not re-sent within dedup window
- Dedup: alert re-sent after window expires
- last_sent timestamp persisted after send
- audit event emitted with category="alert"
- HTTP endpoints require auth / return correct structure
- get/put alert config round-trip
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest

from app.alerts.engine import (
    run_alert_pass,
    get_alerts_config_for_tenant,
    save_alerts_config_for_tenant,
    _should_send,
    _mark_sent,
    _eval_repeated_failed_jobs,
    _eval_gmail_oauth_failure,
    _eval_scheduler_failure,
    _eval_repeated_dispatch_failures,
    _eval_stale_approvals,
    _eval_integration_health_critical,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _db_with_count(count: int = 0):
    db = MagicMock()
    q = db.query.return_value
    q.filter.return_value = q
    q.order_by.return_value = q
    q.first.return_value = None
    q.count.return_value = count
    return db


def _alert_cfg(
    enabled: bool = True,
    recipient: str = "admin@example.com",
    dedup_hours: int = 4,
    thresholds: dict | None = None,
    last_sent: dict | None = None,
) -> dict:
    return {
        "enabled": enabled,
        "recipient_email": recipient,
        "dedup_window_hours": dedup_hours,
        "thresholds": thresholds or {"failed_jobs_count": 3, "dispatch_failures": 3, "stale_approval_hours": 24},
        "last_sent": last_sent or {},
    }


# ---------------------------------------------------------------------------
# Dedup logic
# ---------------------------------------------------------------------------

class TestDedupLogic:
    def test_no_last_sent_means_should_send(self):
        cfg = _alert_cfg(last_sent={})
        assert _should_send(cfg, "some_alert") is True

    def test_recent_send_blocks_resend(self):
        recent = (_utcnow() - timedelta(hours=1)).isoformat()
        cfg = _alert_cfg(dedup_hours=4, last_sent={"some_alert": recent})
        assert _should_send(cfg, "some_alert") is False

    def test_expired_window_allows_resend(self):
        old = (_utcnow() - timedelta(hours=5)).isoformat()
        cfg = _alert_cfg(dedup_hours=4, last_sent={"some_alert": old})
        assert _should_send(cfg, "some_alert") is True

    def test_mark_sent_sets_timestamp(self):
        cfg = _alert_cfg()
        updated = _mark_sent(cfg, "test_alert")
        assert "test_alert" in updated["last_sent"]
        ts = datetime.fromisoformat(updated["last_sent"]["test_alert"])
        assert (_utcnow() - ts).total_seconds() < 5

    def test_mark_sent_preserves_other_entries(self):
        old_time = (_utcnow() - timedelta(hours=1)).isoformat()
        cfg = _alert_cfg(last_sent={"existing_alert": old_time})
        updated = _mark_sent(cfg, "new_alert")
        assert "existing_alert" in updated["last_sent"]
        assert "new_alert" in updated["last_sent"]


# ---------------------------------------------------------------------------
# Individual evaluators
# ---------------------------------------------------------------------------

class TestEvaluators:
    def test_failed_jobs_above_threshold(self):
        db = _db_with_count(5)
        cfg = _alert_cfg(thresholds={"failed_jobs_count": 3})
        result = _eval_repeated_failed_jobs(db, "T_TEST", cfg)
        assert result is not None
        assert result["type"] == "repeated_failed_jobs"
        assert result["count"] == 5

    def test_failed_jobs_below_threshold_returns_none(self):
        db = _db_with_count(2)
        cfg = _alert_cfg(thresholds={"failed_jobs_count": 3})
        result = _eval_repeated_failed_jobs(db, "T_TEST", cfg)
        assert result is None

    def test_gmail_oauth_failure_hit(self):
        db = MagicMock()
        mock_event = MagicMock()
        mock_event.category = "oauth"
        mock_event.action = "gmail_refresh"
        mock_event.created_at = _utcnow()
        q = db.query.return_value
        q.filter.return_value = q
        q.order_by.return_value = q
        q.first.return_value = mock_event
        result = _eval_gmail_oauth_failure(db, "T_TEST")
        assert result is not None
        assert result["type"] == "gmail_oauth_failure"
        assert result["severity"] == "critical"

    def test_gmail_oauth_no_failure_returns_none(self):
        db = MagicMock()
        q = db.query.return_value
        q.filter.return_value = q
        q.order_by.return_value = q
        q.first.return_value = None
        result = _eval_gmail_oauth_failure(db, "T_TEST")
        assert result is None

    def test_scheduler_failure_fires(self):
        settings = {"scheduler_state": {"last_status": "failed", "last_error": "boom"}}
        result = _eval_scheduler_failure(settings)
        assert result is not None
        assert result["type"] == "scheduler_failure"

    def test_scheduler_success_no_alert(self):
        settings = {"scheduler_state": {"last_status": "success"}}
        result = _eval_scheduler_failure(settings)
        assert result is None

    def test_scheduler_no_state_no_alert(self):
        result = _eval_scheduler_failure({})
        assert result is None

    def test_dispatch_failures_above_threshold(self):
        db = _db_with_count(5)
        cfg = _alert_cfg(thresholds={"dispatch_failures": 3})
        result = _eval_repeated_dispatch_failures(db, "T_TEST", cfg)
        assert result is not None
        assert result["type"] == "repeated_dispatch_failures"

    def test_dispatch_failures_below_threshold(self):
        db = _db_with_count(1)
        cfg = _alert_cfg(thresholds={"dispatch_failures": 3})
        result = _eval_repeated_dispatch_failures(db, "T_TEST", cfg)
        assert result is None

    def test_stale_approvals_fires(self):
        db = _db_with_count(2)
        cfg = _alert_cfg(thresholds={"stale_approval_hours": 24})
        result = _eval_stale_approvals(db, "T_TEST", cfg)
        assert result is not None
        assert result["type"] == "stale_approvals"
        assert result["count"] == 2

    def test_stale_approvals_zero_returns_none(self):
        db = _db_with_count(0)
        cfg = _alert_cfg(thresholds={"stale_approval_hours": 24})
        result = _eval_stale_approvals(db, "T_TEST", cfg)
        assert result is None

    def test_integration_health_critical(self):
        db = MagicMock()
        health_data = {
            "overall_status": "error",
            "systems": {"gmail": {"status": "error"}, "monday": {"status": "healthy"}},
        }
        with patch("app.alerts.engine.get_integration_health", return_value=health_data):
            result = _eval_integration_health_critical(db, "T_TEST", MagicMock())
        assert result is not None
        assert result["type"] == "integration_health_critical"
        assert result["severity"] == "critical"
        assert "gmail" in result["title"]

    def test_integration_health_all_healthy_no_alert(self):
        db = MagicMock()
        health_data = {
            "overall_status": "healthy",
            "systems": {"gmail": {"status": "healthy"}},
        }
        with patch("app.alerts.engine.get_integration_health", return_value=health_data):
            result = _eval_integration_health_critical(db, "T_TEST", MagicMock())
        assert result is None


# ---------------------------------------------------------------------------
# run_alert_pass
# ---------------------------------------------------------------------------

class TestRunAlertPass:
    def _settings_with_alerts(self, cfg: dict) -> dict:
        return {"alerts": cfg}

    def test_disabled_skips_evaluation(self):
        db = MagicMock()
        settings = self._settings_with_alerts(_alert_cfg(enabled=False))
        with patch("app.alerts.engine.TenantConfigRepository.get_settings", return_value=settings):
            result = run_alert_pass(db, "T_TEST", MagicMock())
        assert result["skipped"] is True
        assert result["reason"] == "alerts_disabled"

    def test_no_recipient_skips_evaluation(self):
        db = MagicMock()
        settings = self._settings_with_alerts(_alert_cfg(recipient=""))
        with patch("app.alerts.engine.TenantConfigRepository.get_settings", return_value=settings):
            result = run_alert_pass(db, "T_TEST", MagicMock())
        assert result["skipped"] is True
        assert result["reason"] == "no_recipient_configured"

    def test_alert_sent_when_threshold_breached(self):
        db = _db_with_count(5)
        settings = self._settings_with_alerts(_alert_cfg(thresholds={"failed_jobs_count": 3}))
        sent_emails: list[dict] = []

        with patch("app.alerts.engine.TenantConfigRepository.get_settings", return_value=dict(settings)), \
             patch("app.alerts.engine.TenantConfigRepository.update_settings"), \
             patch("app.alerts.engine.create_audit_event"), \
             patch("app.alerts.engine.get_integration_health", return_value={"systems": {}}), \
             patch("app.alerts.engine._send_alert", side_effect=lambda db, tid, alert, rec, s: sent_emails.append(alert) or True):
            result = run_alert_pass(db, "T_TEST", MagicMock())

        assert len(sent_emails) > 0
        assert "repeated_failed_jobs" in result["sent"]

    def test_dedup_prevents_resend_within_window(self):
        db = _db_with_count(5)
        recent = (_utcnow() - timedelta(hours=1)).isoformat()
        cfg = _alert_cfg(
            thresholds={"failed_jobs_count": 3},
            last_sent={"repeated_failed_jobs": recent},
        )
        settings = self._settings_with_alerts(cfg)
        sent_emails: list[dict] = []

        with patch("app.alerts.engine.TenantConfigRepository.get_settings", return_value=dict(settings)), \
             patch("app.alerts.engine.TenantConfigRepository.update_settings"), \
             patch("app.alerts.engine.create_audit_event"), \
             patch("app.alerts.engine.get_integration_health", return_value={"systems": {}}), \
             patch("app.alerts.engine._send_alert", side_effect=lambda db, tid, alert, rec, s: sent_emails.append(alert) or True):
            result = run_alert_pass(db, "T_TEST", MagicMock())

        # Should be skipped for dedup, not sent
        assert "repeated_failed_jobs" not in result["sent"]
        assert "repeated_failed_jobs" in result["skipped_dedup"]

    def test_dedup_allows_resend_after_window(self):
        db = _db_with_count(5)
        old = (_utcnow() - timedelta(hours=6)).isoformat()
        cfg = _alert_cfg(
            dedup_hours=4,
            thresholds={"failed_jobs_count": 3},
            last_sent={"repeated_failed_jobs": old},
        )
        settings = self._settings_with_alerts(cfg)

        with patch("app.alerts.engine.TenantConfigRepository.get_settings", return_value=dict(settings)), \
             patch("app.alerts.engine.TenantConfigRepository.update_settings"), \
             patch("app.alerts.engine.create_audit_event"), \
             patch("app.alerts.engine.get_integration_health", return_value={"systems": {}}), \
             patch("app.alerts.engine._send_alert", return_value=True):
            result = run_alert_pass(db, "T_TEST", MagicMock())

        assert "repeated_failed_jobs" in result["sent"]

    def test_audit_event_emitted_on_send(self):
        db = _db_with_count(5)
        settings = self._settings_with_alerts(_alert_cfg(thresholds={"failed_jobs_count": 3}))
        audit_calls = []

        with patch("app.alerts.engine.TenantConfigRepository.get_settings", return_value=dict(settings)), \
             patch("app.alerts.engine.TenantConfigRepository.update_settings"), \
             patch("app.alerts.engine.create_audit_event", side_effect=lambda **kw: audit_calls.append(kw)), \
             patch("app.alerts.engine.get_integration_health", return_value={"systems": {}}), \
             patch("app.alerts.engine._send_alert", return_value=True):
            run_alert_pass(db, "T_TEST", MagicMock())

        alert_audits = [c for c in audit_calls if c.get("category") == "alert"]
        assert len(alert_audits) > 0

    def test_send_failure_recorded_in_errors(self):
        db = _db_with_count(5)
        settings = self._settings_with_alerts(_alert_cfg(thresholds={"failed_jobs_count": 3}))

        with patch("app.alerts.engine.TenantConfigRepository.get_settings", return_value=dict(settings)), \
             patch("app.alerts.engine.TenantConfigRepository.update_settings"), \
             patch("app.alerts.engine.create_audit_event"), \
             patch("app.alerts.engine.get_integration_health", return_value={"systems": {}}), \
             patch("app.alerts.engine._send_alert", return_value=False):
            result = run_alert_pass(db, "T_TEST", MagicMock())

        assert "repeated_failed_jobs" in result["errors"]

    def test_last_sent_persisted_after_send(self):
        db = _db_with_count(5)
        settings = self._settings_with_alerts(_alert_cfg(thresholds={"failed_jobs_count": 3}))
        saved_settings: list[dict] = []

        with patch("app.alerts.engine.TenantConfigRepository.get_settings", return_value=dict(settings)), \
             patch("app.alerts.engine.TenantConfigRepository.update_settings", side_effect=lambda db, tid, s: saved_settings.append(s)), \
             patch("app.alerts.engine.create_audit_event"), \
             patch("app.alerts.engine.get_integration_health", return_value={"systems": {}}), \
             patch("app.alerts.engine._send_alert", return_value=True):
            run_alert_pass(db, "T_TEST", MagicMock())

        # Should have called update_settings with updated last_sent
        assert len(saved_settings) > 0
        saved_cfg = saved_settings[-1].get("alerts") or {}
        assert "repeated_failed_jobs" in (saved_cfg.get("last_sent") or {})


# ---------------------------------------------------------------------------
# Config get/put
# ---------------------------------------------------------------------------

class TestAlertConfig:
    def test_get_returns_defaults_when_not_set(self):
        db = MagicMock()
        with patch("app.alerts.engine.TenantConfigRepository.get_settings", return_value={}):
            cfg = get_alerts_config_for_tenant(db, "T_TEST")
        assert cfg["enabled"] is True
        assert cfg["recipient_email"] == ""
        assert cfg["channel"] == "email"
        assert "failed_jobs_count" in cfg["thresholds"]

    def test_save_and_read_roundtrip(self):
        db = MagicMock()
        saved = {}

        def fake_update(db, tid, settings):
            saved.update(settings)

        with patch("app.alerts.engine.TenantConfigRepository.get_settings", return_value={}), \
             patch("app.alerts.engine.TenantConfigRepository.update_settings", side_effect=fake_update):
            with patch("app.alerts.engine.TenantConfigRepository.get_settings", return_value=saved):
                result = save_alerts_config_for_tenant(
                    db, "T_TEST",
                    enabled=True,
                    recipient_email="ops@example.com",
                    dedup_window_hours=6,
                    thresholds={"failed_jobs_count": 5},
                )

        # The function returns the result of get_alerts_config_for_tenant on the updated settings
        assert result is not None

    def test_thresholds_merged_with_defaults(self):
        db = MagicMock()
        saved = {}

        def fake_update(db, tid, settings):
            saved.update(settings)

        with patch("app.alerts.engine.TenantConfigRepository.get_settings", return_value={}), \
             patch("app.alerts.engine.TenantConfigRepository.update_settings", side_effect=fake_update):
            with patch("app.alerts.engine.TenantConfigRepository.get_settings", return_value=saved):
                save_alerts_config_for_tenant(
                    db, "T_TEST",
                    enabled=True,
                    recipient_email="x@y.com",
                    thresholds={"failed_jobs_count": 10},
                )

        alerts = saved.get("alerts") or {}
        # Custom threshold kept
        assert alerts["thresholds"]["failed_jobs_count"] == 10
        # Default threshold for others still present
        assert "stale_approval_hours" in alerts["thresholds"]


# ---------------------------------------------------------------------------
# HTTP endpoint auth
# ---------------------------------------------------------------------------

class TestAlertEndpointAuth:
    def _client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_get_config_without_auth_returns_401_or_403(self):
        resp = self._client().get("/alerts/config")
        assert resp.status_code in (401, 403)

    def test_put_config_without_auth_returns_401_or_403(self):
        resp = self._client().put("/alerts/config", json={"enabled": True, "recipient_email": "x@y.com"})
        assert resp.status_code in (401, 403)

    def test_run_alerts_without_auth_returns_401_or_403(self):
        resp = self._client().post("/alerts/run")
        assert resp.status_code in (401, 403)

    def test_admin_run_all_requires_admin_key(self):
        resp = self._client().get("/admin/alerts/run-all")
        assert resp.status_code == 401
