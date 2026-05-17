"""
Tests for admin Support Action Console (Slice 2).

Covers:
- pause/resume automation sets demo_mode correctly
- disable/enable scheduler sets run_mode correctly
- force_inbox_sync calls Gmail processing and returns result
- ack_needs_help persists acknowledged item
- clear_acknowledged removes all acknowledged items
- get_tenant_ops_state returns required fields
- tenant isolation: actions reject unknown tenant_id
- admin auth required on HTTP endpoints (401 without key)
- audit events emitted with category="support_action"
- state persistence verified
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call
import pytest

from app.admin.support_console import (
    pause_automation,
    resume_automation,
    disable_scheduler,
    enable_scheduler,
    force_inbox_sync,
    ack_needs_help,
    clear_acknowledged,
    get_tenant_ops_state,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_record(tenant_id: str = "T_TEST", settings: dict | None = None) -> MagicMock:
    r = MagicMock()
    r.tenant_id = tenant_id
    r.settings = settings or {}
    r.name = tenant_id
    return r


def _db_with_tenant(record: MagicMock | None) -> MagicMock:
    db = MagicMock()
    return db


def _patch_repo(record: MagicMock | None):
    """Patch TenantConfigRepository methods."""
    return patch.multiple(
        "app.admin.support_console",
        _tenant_exists=MagicMock(return_value=(record is not None)),
        _get_settings=MagicMock(return_value=dict(record.settings) if record else {}),
        _save_settings=MagicMock(),
        create_audit_event=MagicMock(),
    )


# ---------------------------------------------------------------------------
# pause_automation
# ---------------------------------------------------------------------------

class TestPauseAutomation:
    def test_unknown_tenant_returns_failure(self):
        db = MagicMock()
        with patch("app.admin.support_console._tenant_exists", return_value=False):
            result = pause_automation(db, "T_UNKNOWN")
        assert result["status"] == "failed"
        assert "not found" in result["message"].lower()

    def test_sets_demo_mode_true(self):
        db = MagicMock()
        saved: list[dict] = []

        with patch("app.admin.support_console._tenant_exists", return_value=True), \
             patch("app.admin.support_console._get_settings", return_value={"automation": {}}), \
             patch("app.admin.support_console._save_settings", side_effect=lambda d, t, s: saved.append(s)), \
             patch("app.admin.support_console.create_audit_event"):
            result = pause_automation(db, "T_TEST")

        assert result["status"] == "success"
        assert saved[0]["automation"]["demo_mode"] is True

    def test_audit_event_emitted(self):
        db = MagicMock()
        audit_calls = []
        with patch("app.admin.support_console._tenant_exists", return_value=True), \
             patch("app.admin.support_console._get_settings", return_value={}), \
             patch("app.admin.support_console._save_settings"), \
             patch("app.admin.support_console.create_audit_event", side_effect=lambda **kw: audit_calls.append(kw)):
            pause_automation(db, "T_TEST", actor="support-team")

        assert any(c["category"] == "support_action" and c["action"] == "pause_automation" for c in audit_calls)
        assert any(c.get("details", {}).get("actor") == "support-team" for c in audit_calls)


# ---------------------------------------------------------------------------
# resume_automation
# ---------------------------------------------------------------------------

class TestResumeAutomation:
    def test_unknown_tenant_returns_failure(self):
        db = MagicMock()
        with patch("app.admin.support_console._tenant_exists", return_value=False):
            result = resume_automation(db, "T_UNKNOWN")
        assert result["status"] == "failed"

    def test_sets_demo_mode_false(self):
        db = MagicMock()
        saved: list[dict] = []
        with patch("app.admin.support_console._tenant_exists", return_value=True), \
             patch("app.admin.support_console._get_settings", return_value={"automation": {"demo_mode": True}}), \
             patch("app.admin.support_console._save_settings", side_effect=lambda d, t, s: saved.append(s)), \
             patch("app.admin.support_console.create_audit_event"):
            result = resume_automation(db, "T_TEST")

        assert result["status"] == "success"
        assert saved[0]["automation"]["demo_mode"] is False


# ---------------------------------------------------------------------------
# disable_scheduler / enable_scheduler
# ---------------------------------------------------------------------------

class TestSchedulerControl:
    def test_disable_sets_paused(self):
        db = MagicMock()
        saved: list[dict] = []
        with patch("app.admin.support_console._tenant_exists", return_value=True), \
             patch("app.admin.support_console._get_settings", return_value={}), \
             patch("app.admin.support_console._save_settings", side_effect=lambda d, t, s: saved.append(s)), \
             patch("app.admin.support_console.create_audit_event"):
            result = disable_scheduler(db, "T_TEST")

        assert result["status"] == "success"
        assert saved[0]["scheduler"]["run_mode"] == "paused"

    def test_enable_sets_scheduled(self):
        db = MagicMock()
        saved: list[dict] = []
        with patch("app.admin.support_console._tenant_exists", return_value=True), \
             patch("app.admin.support_console._get_settings", return_value={"scheduler": {"run_mode": "paused"}}), \
             patch("app.admin.support_console._save_settings", side_effect=lambda d, t, s: saved.append(s)), \
             patch("app.admin.support_console.create_audit_event"):
            result = enable_scheduler(db, "T_TEST")

        assert result["status"] == "success"
        assert saved[0]["scheduler"]["run_mode"] == "scheduled"

    def test_unknown_tenant_disable_fails(self):
        db = MagicMock()
        with patch("app.admin.support_console._tenant_exists", return_value=False):
            result = disable_scheduler(db, "T_UNKNOWN")
        assert result["status"] == "failed"

    def test_disable_scheduler_audit_emitted(self):
        db = MagicMock()
        audit_calls = []
        with patch("app.admin.support_console._tenant_exists", return_value=True), \
             patch("app.admin.support_console._get_settings", return_value={}), \
             patch("app.admin.support_console._save_settings"), \
             patch("app.admin.support_console.create_audit_event", side_effect=lambda **kw: audit_calls.append(kw)):
            disable_scheduler(db, "T_TEST")

        assert any(c["action"] == "disable_scheduler" for c in audit_calls)


# ---------------------------------------------------------------------------
# force_inbox_sync
# ---------------------------------------------------------------------------

class TestForceInboxSync:
    def test_unknown_tenant_fails(self):
        db = MagicMock()
        with patch("app.admin.support_console._tenant_exists", return_value=False):
            result = force_inbox_sync(db, "T_UNKNOWN")
        assert result["status"] == "failed"

    def test_successful_sync_returns_summary(self):
        db = MagicMock()
        sync_result = {
            "processed": 3,
            "created_jobs": [{"job_id": "j1"}, {"job_id": "j2"}],
            "deduped": 1,
            "errors": [],
        }
        with patch("app.admin.support_console._tenant_exists", return_value=True), \
             patch("app.admin.support_console.create_audit_event"), \
             patch("app.main._run_gmail_inbox_sync", return_value=sync_result):
            result = force_inbox_sync(db, "T_TEST")

        assert result["status"] == "success"
        assert result["details"]["processed"] == 3
        assert result["details"]["created_jobs"] == 2

    def test_sync_exception_returns_failure(self):
        db = MagicMock()
        with patch("app.admin.support_console._tenant_exists", return_value=True), \
             patch("app.admin.support_console.create_audit_event"), \
             patch("app.main._run_gmail_inbox_sync", side_effect=RuntimeError("no creds")):
            result = force_inbox_sync(db, "T_TEST")

        assert result["status"] == "failed"


# ---------------------------------------------------------------------------
# ack_needs_help / clear_acknowledged
# ---------------------------------------------------------------------------

class TestNeedsHelpAck:
    def test_ack_unknown_tenant_fails(self):
        db = MagicMock()
        with patch("app.admin.support_console._tenant_exists", return_value=False):
            result = ack_needs_help(db, "T_UNKNOWN", "pipeline:job-1")
        assert result["status"] == "failed"

    def test_ack_persists_item_key(self):
        db = MagicMock()
        saved: list[dict] = []
        with patch("app.admin.support_console._tenant_exists", return_value=True), \
             patch("app.admin.support_console._get_settings", return_value={}), \
             patch("app.admin.support_console._save_settings", side_effect=lambda d, t, s: saved.append(s)), \
             patch("app.admin.support_console.create_audit_event"):
            result = ack_needs_help(db, "T_TEST", "pipeline:job-abc", actor="support-1", note="Investigating")

        assert result["status"] == "success"
        acks = saved[0].get("support_acknowledged_items", {})
        assert "pipeline:job-abc" in acks
        assert acks["pipeline:job-abc"]["acknowledged_by"] == "support-1"
        assert acks["pipeline:job-abc"]["note"] == "Investigating"

    def test_ack_multiple_items_accumulate(self):
        db = MagicMock()
        initial = {"support_acknowledged_items": {"existing:item-1": {"acknowledged_by": "prev"}}}
        saved: list[dict] = []
        with patch("app.admin.support_console._tenant_exists", return_value=True), \
             patch("app.admin.support_console._get_settings", return_value=dict(initial)), \
             patch("app.admin.support_console._save_settings", side_effect=lambda d, t, s: saved.append(s)), \
             patch("app.admin.support_console.create_audit_event"):
            ack_needs_help(db, "T_TEST", "pipeline:job-xyz")

        acks = saved[0].get("support_acknowledged_items", {})
        assert "existing:item-1" in acks
        assert "pipeline:job-xyz" in acks

    def test_clear_acknowledged_removes_all(self):
        db = MagicMock()
        initial = {"support_acknowledged_items": {"k1": {}, "k2": {}}, "other_key": "preserved"}
        saved: list[dict] = []
        with patch("app.admin.support_console._tenant_exists", return_value=True), \
             patch("app.admin.support_console._get_settings", return_value=dict(initial)), \
             patch("app.admin.support_console._save_settings", side_effect=lambda d, t, s: saved.append(s)), \
             patch("app.admin.support_console.create_audit_event"):
            result = clear_acknowledged(db, "T_TEST")

        assert result["status"] == "success"
        assert "support_acknowledged_items" not in saved[0]
        # Other settings preserved
        assert saved[0].get("other_key") == "preserved"

    def test_ack_audit_category(self):
        db = MagicMock()
        audit_calls = []
        with patch("app.admin.support_console._tenant_exists", return_value=True), \
             patch("app.admin.support_console._get_settings", return_value={}), \
             patch("app.admin.support_console._save_settings"), \
             patch("app.admin.support_console.create_audit_event", side_effect=lambda **kw: audit_calls.append(kw)):
            ack_needs_help(db, "T_TEST", "k1")

        assert all(c["category"] == "support_action" for c in audit_calls)


# ---------------------------------------------------------------------------
# get_tenant_ops_state
# ---------------------------------------------------------------------------

class TestGetTenantOpsState:
    def _mock_db_for_state(self, record: MagicMock | None = None) -> MagicMock:
        db = MagicMock()
        mock_query = db.query.return_value
        mock_query.filter.return_value = mock_query
        mock_query.count.return_value = 0
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.all.return_value = []
        return db

    def test_unknown_tenant_returns_error(self):
        db = MagicMock()
        with patch("app.admin.support_console.TenantConfigRepository.get", return_value=None):
            result = get_tenant_ops_state(db, "T_UNKNOWN")
        assert "error" in result

    def test_returns_required_fields(self):
        db = self._mock_db_for_state()
        record = _mock_record(settings={
            "automation": {"demo_mode": False},
            "scheduler": {"run_mode": "scheduled"},
        })
        with patch("app.admin.support_console.TenantConfigRepository.get", return_value=record), \
             patch("app.admin.support_console.get_integration_health", return_value={"overall_status": "healthy"}):
            result = get_tenant_ops_state(db, "T_TEST")

        assert result["tenant_id"] == "T_TEST"
        assert "automation_enabled" in result
        assert "scheduler_mode" in result
        assert "integrations_health" in result
        assert "failed_jobs_48h" in result
        assert "stale_approvals_24h" in result
        assert "acknowledged_items" in result
        assert "recent_audit_events" in result

    def test_automation_enabled_inverts_demo_mode(self):
        db = self._mock_db_for_state()
        record = _mock_record(settings={"automation": {"demo_mode": True}})
        with patch("app.admin.support_console.TenantConfigRepository.get", return_value=record), \
             patch("app.admin.support_console.get_integration_health", return_value={}):
            result = get_tenant_ops_state(db, "T_TEST")

        assert result["automation_enabled"] is False

    def test_acknowledged_items_included(self):
        db = self._mock_db_for_state()
        settings = {"support_acknowledged_items": {"k1": {"acknowledged_by": "me"}}}
        record = _mock_record(settings=settings)
        with patch("app.admin.support_console.TenantConfigRepository.get", return_value=record), \
             patch("app.admin.support_console.get_integration_health", return_value={}):
            result = get_tenant_ops_state(db, "T_TEST")

        assert result["acknowledged_items"] == {"k1": {"acknowledged_by": "me"}}


# ---------------------------------------------------------------------------
# HTTP endpoint auth tests
# ---------------------------------------------------------------------------

class TestSupportEndpointAuth:
    def _client(self):
        from fastapi.testclient import TestClient
        from app.main import app
        return TestClient(app, raise_server_exceptions=False)

    def test_state_requires_admin_key(self):
        resp = self._client().get("/admin/support/T_TEST/state")
        assert resp.status_code == 401

    def test_pause_automation_requires_admin_key(self):
        resp = self._client().post("/admin/support/T_TEST/pause-automation", json={})
        assert resp.status_code == 401

    def test_resume_automation_requires_admin_key(self):
        resp = self._client().post("/admin/support/T_TEST/resume-automation", json={})
        assert resp.status_code == 401

    def test_force_inbox_sync_requires_admin_key(self):
        resp = self._client().post("/admin/support/T_TEST/force-inbox-sync", json={})
        assert resp.status_code == 401

    def test_disable_scheduler_requires_admin_key(self):
        resp = self._client().post("/admin/support/T_TEST/disable-scheduler", json={})
        assert resp.status_code == 401

    def test_enable_scheduler_requires_admin_key(self):
        resp = self._client().post("/admin/support/T_TEST/enable-scheduler", json={})
        assert resp.status_code == 401

    def test_ack_needs_help_requires_admin_key(self):
        resp = self._client().post("/admin/support/T_TEST/ack-needs-help", json={"item_key": "k"})
        assert resp.status_code == 401

    def test_clear_acknowledged_requires_admin_key(self):
        resp = self._client().post("/admin/support/T_TEST/clear-acknowledged", json={})
        assert resp.status_code == 401
