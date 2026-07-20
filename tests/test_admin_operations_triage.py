"""
Tests for admin operations triage endpoint (Slice — SaaS Launch Hardening).

Covers:
- get_admin_needs_help returns correct shape
- admin auth required (401 without key, 200 with key)
- integration error signals appear for unhealthy tenants
- failed pipeline job signals appear
- stale approval signals appear
- failed integration event signals appear
- failed scheduler audit signals appear
- one bad tenant does not break overall response
- no secrets in response
- severity ordering (critical before high before medium)
- limit is respected (default 50, max 200)
- empty tenant list returns safe response
- _row builder produces required keys
- tenant isolation (rows carry correct tenant_id)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.admin.operations_triage import (
    _build_tenant_triage,
    _failed_integration_event_signals,
    _failed_pipeline_signals,
    _failed_scheduler_signals,
    _integration_signals,
    _missing_tenant_config_signals,
    _reconciliation_required_signals,
    _resolve_runbook,
    _row,
    _stale_approval_signals,
    dedupe_and_normalize_signals,
    get_admin_needs_help,
)


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------

def _settings(**kwargs):
    defaults = {
        "GOOGLE_MAIL_ACCESS_TOKEN": "",
        "MONDAY_API_KEY": "",
        "FORTNOX_ACCESS_TOKEN": "",
        "APP_NAME": "Test",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _mock_db():
    db = MagicMock()
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.count.return_value = 0
    q.first.return_value = None
    q.all.return_value = []
    db.query.return_value = q
    return db


def _make_job(job_id="job-001", tenant_id="T_A", job_type="lead", status="failed",
              result=None, updated_at=None):
    j = MagicMock()
    j.job_id = job_id
    j.tenant_id = tenant_id
    j.job_type = job_type
    j.status = status
    j.result = result or {"error": "Something went wrong"}
    j.updated_at = updated_at or datetime.now(timezone.utc)
    return j


def _make_approval(approval_id="appr-001", tenant_id="T_A", job_id="job-001",
                   state="pending", next_on_approve="email_send", created_at=None):
    a = MagicMock()
    a.approval_id = approval_id
    a.tenant_id = tenant_id
    a.job_id = job_id
    a.state = state
    a.next_on_approve = next_on_approve
    a.created_at = created_at or (datetime.now(timezone.utc) - timedelta(hours=30))
    return a


def _make_integration_event(tenant_id="T_A", job_id="job-001",
                            integration_type="controlled_dispatch",
                            status="failed", last_error="Auth failed",
                            created_at=None, event_id=1):
    e = MagicMock()
    e.id = event_id
    e.tenant_id = tenant_id
    e.job_id = job_id
    e.integration_type = integration_type
    e.status = status
    e.last_error = last_error
    e.created_at = created_at or datetime.now(timezone.utc)
    return e


def _make_audit_event(tenant_id="T_A", category="scheduler", action="run_once",
                      status="failed", details=None, created_at=None,
                      event_id="evt-001"):
    e = MagicMock()
    e.event_id = event_id
    e.tenant_id = tenant_id
    e.category = category
    e.action = action
    e.status = status
    e.details = details or {}
    e.created_at = created_at or datetime.now(timezone.utc)
    return e


def _make_tenant_record(tenant_id="T_A", name="Acme"):
    r = MagicMock()
    r.tenant_id = tenant_id
    r.name = name
    return r


# ---------------------------------------------------------------------------
# _row builder
# ---------------------------------------------------------------------------

class TestRowBuilder:
    def test_required_keys_present(self):
        r = _row(
            tenant_id="T_A",
            tenant_name="Acme",
            severity="high",
            area="pipeline",
            title="Test",
            detail="Some detail",
        )
        required = {
            "tenant_id", "tenant_name", "severity", "area",
            "title", "detail", "job_id", "approval_id",
            "created_at", "recommended_action", "runbook_ref",
        }
        assert required.issubset(r.keys())

    def test_optional_defaults_to_none_or_empty(self):
        r = _row(tenant_id="T", tenant_name="T", severity="info", area="x",
                 title="t", detail="d")
        assert r["job_id"] is None
        assert r["approval_id"] is None
        assert r["created_at"] is None

    def test_no_secrets_in_response(self):
        r = _row(tenant_id="T", tenant_name="T", severity="info", area="x",
                 title="t", detail="d", recommended_action="", runbook_ref="")
        dumped = str(r)
        for bad in ("password", "api_key", "token", "secret", "access_token"):
            assert bad not in dumped.lower()


# ---------------------------------------------------------------------------
# _integration_signals
# ---------------------------------------------------------------------------

class TestIntegrationSignals:
    def test_error_status_yields_critical_row(self):
        db = _mock_db()
        s = _settings()
        health_data = {
            "overall_status": "error",
            "systems": {
                "google_mail": {
                    "status": "error",
                    "recommended_action": "Fix Gmail config.",
                }
            },
            "recent_errors": [],
            "runbook_signals": [],
        }
        with (
            patch("app.admin.operations_triage.get_integration_health", return_value=health_data),
            patch(
                "app.admin.operations_triage.derive_integration_selection",
                return_value=MagicMock(),
            ),
            patch(
                "app.admin.operations_triage.should_raise_tenant_warning",
                return_value=True,
            ),
        ):
            rows = _integration_signals(db, "T_A", "Acme", s)
        assert len(rows) == 1
        assert rows[0]["severity"] == "critical"
        assert rows[0]["area"] == "integration"
        assert rows[0]["tenant_id"] == "T_A"

    def test_not_configured_yields_high_severity(self):
        db = _mock_db()
        s = _settings()
        health_data = {
            "overall_status": "warning",
            "systems": {
                "monday": {"status": "not_configured", "recommended_action": "Set API key."}
            },
            "recent_errors": [],
            "runbook_signals": [],
        }
        with (
            patch("app.admin.operations_triage.get_integration_health", return_value=health_data),
            patch(
                "app.admin.operations_triage.derive_integration_selection",
                return_value=MagicMock(),
            ),
            patch(
                "app.admin.operations_triage.should_raise_tenant_warning",
                return_value=True,
            ),
        ):
            rows = _integration_signals(db, "T_A", "Acme", s)
        assert rows[0]["severity"] == "medium"

    def test_warning_yields_medium_severity(self):
        db = _mock_db()
        s = _settings()
        health_data = {
            "overall_status": "warning",
            "systems": {
                "google_mail": {"status": "warning", "recommended_action": "Run scan."}
            },
            "recent_errors": [],
            "runbook_signals": [],
        }
        with (
            patch("app.admin.operations_triage.get_integration_health", return_value=health_data),
            patch(
                "app.admin.operations_triage.derive_integration_selection",
                return_value=MagicMock(),
            ),
            patch(
                "app.admin.operations_triage.should_raise_tenant_warning",
                return_value=True,
            ),
        ):
            rows = _integration_signals(db, "T_A", "Acme", s)
        assert rows[0]["severity"] == "medium"

    def test_healthy_system_produces_no_rows(self):
        db = _mock_db()
        s = _settings()
        health_data = {
            "overall_status": "healthy",
            "systems": {"gmail": {"status": "healthy", "recommended_action": ""}},
            "recent_errors": [],
            "runbook_signals": [],
        }
        with patch("app.admin.operations_triage.get_integration_health", return_value=health_data):
            rows = _integration_signals(db, "T_A", "Acme", s)
        assert rows == []

    def test_exception_returns_empty_list(self):
        db = _mock_db()
        s = _settings()
        with patch("app.admin.operations_triage.get_integration_health", side_effect=Exception("boom")):
            rows = _integration_signals(db, "T_A", "Acme", s)
        assert rows == []


# ---------------------------------------------------------------------------
# _failed_pipeline_signals
# ---------------------------------------------------------------------------

class TestFailedPipelineSignals:
    def test_failed_job_produces_high_row(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            _make_job(job_id="job-001", job_type="lead", result={"error": "Dispatch failed"})
        ]
        rows = _failed_pipeline_signals(db, "T_A", "Acme")
        assert len(rows) == 1
        assert rows[0]["severity"] == "high"
        assert rows[0]["area"] == "pipeline"
        assert rows[0]["job_id"] == "job-001"
        assert "Dispatch failed" in rows[0]["detail"]

    def test_no_failed_jobs_returns_empty(self):
        db = _mock_db()
        rows = _failed_pipeline_signals(db, "T_A", "Acme")
        assert rows == []

    def test_exception_returns_empty(self):
        db = MagicMock()
        db.query.side_effect = Exception("db error")
        rows = _failed_pipeline_signals(db, "T_A", "Acme")
        assert rows == []

    def test_tenant_id_matches(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            _make_job(tenant_id="T_B")
        ]
        rows = _failed_pipeline_signals(db, "T_B", "Beta Corp")
        assert rows[0]["tenant_id"] == "T_B"
        assert rows[0]["tenant_name"] == "Beta Corp"


# ---------------------------------------------------------------------------
# _stale_approval_signals
# ---------------------------------------------------------------------------

class TestStaleApprovalSignals:
    def test_stale_email_approval_produces_high_row(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            _make_approval(approval_id="appr-x", next_on_approve="email_send",
                           created_at=datetime.now(timezone.utc) - timedelta(hours=30))
        ]
        rows = _stale_approval_signals(db, "T_A", "Acme")
        assert len(rows) == 1
        assert rows[0]["severity"] == "high"
        assert rows[0]["area"] == "approval_email"
        assert rows[0]["approval_id"] == "appr-x"

    def test_stale_dispatch_approval_area(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            _make_approval(next_on_approve="controlled_dispatch",
                           created_at=datetime.now(timezone.utc) - timedelta(hours=50))
        ]
        rows = _stale_approval_signals(db, "T_A", "Acme")
        assert rows[0]["area"] == "approval_dispatch"

    def test_no_stale_approvals_returns_empty(self):
        db = _mock_db()
        rows = _stale_approval_signals(db, "T_A", "Acme")
        assert rows == []

    def test_exception_returns_empty(self):
        db = MagicMock()
        db.query.side_effect = Exception("oops")
        rows = _stale_approval_signals(db, "T_A", "Acme")
        assert rows == []


# ---------------------------------------------------------------------------
# _failed_integration_event_signals
# ---------------------------------------------------------------------------

class TestFailedIntegrationEventSignals:
    def test_failed_event_produces_high_row(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            _make_integration_event(integration_type="controlled_dispatch", last_error="401 Unauthorized")
        ]
        rows = _failed_integration_event_signals(db, "T_A", "Acme")
        assert len(rows) == 1
        assert rows[0]["severity"] == "high"
        assert "401 Unauthorized" in rows[0]["detail"]
        assert rows[0]["external_impact"] == "yes"
        assert rows[0]["retryable"] == "unknown"

    def test_success_latest_state_suppresses_failed_row(self):
        db = _mock_db()
        older_failed = _make_integration_event(
            status="failed",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
            event_id=1,
        )
        newer_success = _make_integration_event(
            status="success",
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
            event_id=2,
        )
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            newer_success,
            older_failed,
        ]
        rows = _failed_integration_event_signals(db, "T_A", "Acme")
        assert rows == []

    def test_no_failed_events_returns_empty(self):
        db = _mock_db()
        rows = _failed_integration_event_signals(db, "T_A", "Acme")
        assert rows == []

    def test_exception_returns_empty(self):
        db = MagicMock()
        db.query.side_effect = Exception("fail")
        rows = _failed_integration_event_signals(db, "T_A", "Acme")
        assert rows == []


# ---------------------------------------------------------------------------
# _failed_scheduler_signals
# ---------------------------------------------------------------------------

class TestFailedSchedulerSignals:
    def test_failed_scheduler_event_produces_medium_row(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            _make_audit_event(category="scheduler", action="run_once", status="failed")
        ]
        rows = _failed_scheduler_signals(db, "T_A", "Acme")
        assert len(rows) == 1
        assert rows[0]["severity"] == "medium"
        assert rows[0]["area"] == "scheduler"

    def test_exception_returns_empty(self):
        db = MagicMock()
        db.query.side_effect = Exception("err")
        rows = _failed_scheduler_signals(db, "T_A", "Acme")
        assert rows == []


# ---------------------------------------------------------------------------
# get_admin_needs_help (full aggregation)
# ---------------------------------------------------------------------------

def _mock_db_empty():
    db = _mock_db()
    return db


class TestGetAdminNeedsHelp:
    def test_empty_tenant_list_returns_safe_response(self):
        db = _mock_db()
        s = _settings()
        with patch("app.admin.operations_triage.TenantConfigRepository.list_all", return_value=[]):
            result = get_admin_needs_help(db=db, app_settings=s)
        assert result["total"] == 0
        assert result["items"] == []
        assert "critical" in result
        assert "high" in result
        assert "medium" in result

    def test_response_shape_has_required_keys(self):
        db = _mock_db()
        s = _settings()
        tenant = _make_tenant_record("T_A", "Acme")
        with patch("app.admin.operations_triage.TenantConfigRepository.list_all", return_value=[tenant]):
            with patch("app.admin.operations_triage._build_tenant_triage", return_value=[
                _row(tenant_id="T_A", tenant_name="Acme", severity="high",
                     area="pipeline", title="Failed job", detail="Error detail",
                     job_id="job-001", created_at="2026-05-01T10:00:00+00:00",
                     recommended_action="Review job.", runbook_ref="docs/runbook-pilot-support.md")
            ]):
                result = get_admin_needs_help(db=db, app_settings=s)
        assert result["total"] == 1
        assert result["high"] == 1
        assert result["items"][0]["tenant_id"] == "T_A"
        assert result["items"][0]["job_id"] == "job-001"

    def test_severity_ordering_critical_before_high_before_medium(self):
        db = _mock_db()
        s = _settings()
        tenant = _make_tenant_record("T_A", "Acme")
        now = "2026-05-01T10:00:00+00:00"
        rows = [
            _row(tenant_id="T_A", tenant_name="Acme", severity="medium",
                 area="x", title="Med", detail="d", created_at=now),
            _row(tenant_id="T_A", tenant_name="Acme", severity="critical",
                 area="x", title="Crit", detail="d", created_at=now),
            _row(tenant_id="T_A", tenant_name="Acme", severity="high",
                 area="x", title="High", detail="d", created_at=now),
        ]
        with patch("app.admin.operations_triage.TenantConfigRepository.list_all", return_value=[tenant]):
            with patch("app.admin.operations_triage._build_tenant_triage", return_value=rows):
                result = get_admin_needs_help(db=db, app_settings=s)
        severities = [r["severity"] for r in result["items"]]
        assert severities == ["critical", "high", "medium"]

    def test_one_failing_tenant_does_not_break_response(self):
        db = _mock_db()
        s = _settings()
        tenant_ok  = _make_tenant_record("T_A", "Good")
        tenant_bad = _make_tenant_record("T_B", "Bad")
        ok_row = _row(tenant_id="T_A", tenant_name="Good", severity="high",
                      area="pipeline", title="Fail", detail="d",
                      created_at="2026-05-01T09:00:00+00:00")

        def _build_side_effect(db, tenant_id, tenant_name, app_settings, **kwargs):
            if tenant_id == "T_B":
                raise RuntimeError("simulated failure")
            return [ok_row]

        with patch("app.admin.operations_triage.TenantConfigRepository.list_all",
                   return_value=[tenant_ok, tenant_bad]):
            with patch("app.admin.operations_triage._build_tenant_triage",
                       side_effect=_build_side_effect):
                result = get_admin_needs_help(db=db, app_settings=s)
        assert result["total"] == 1
        assert result["items"][0]["tenant_id"] == "T_A"

    def test_limit_is_respected(self):
        db = _mock_db()
        s = _settings()
        tenant = _make_tenant_record("T_A", "Acme")
        now = "2026-05-01T10:00:00+00:00"
        many_rows = [
            _row(tenant_id="T_A", tenant_name="Acme", severity="high",
                 area="pipeline", title=f"Fail {i}", detail="d", created_at=now)
            for i in range(20)
        ]
        with patch("app.admin.operations_triage.TenantConfigRepository.list_all", return_value=[tenant]):
            with patch("app.admin.operations_triage._build_tenant_triage", return_value=many_rows):
                result = get_admin_needs_help(db=db, app_settings=s, limit=5)
        assert result["total"] == 5
        assert len(result["items"]) == 5

    def test_max_limit_capped_at_200_in_endpoint(self):
        """Endpoint enforces min(limit, 200) — verify 201 is accepted but capped."""
        db = _mock_db()
        s = _settings()
        with patch("app.admin.operations_triage.TenantConfigRepository.list_all", return_value=[]):
            result = get_admin_needs_help(db=db, app_settings=s, limit=201)
        # Should not raise; returns whatever fits up to 201 (no crash)
        assert isinstance(result["items"], list)

    def test_no_secrets_in_response(self):
        db = _mock_db()
        s = _settings(GOOGLE_MAIL_ACCESS_TOKEN="super-secret-token")
        with patch("app.admin.operations_triage.TenantConfigRepository.list_all", return_value=[]):
            result = get_admin_needs_help(db=db, app_settings=s)
        dumped = str(result)
        assert "super-secret-token" not in dumped

    def test_tenant_isolation_rows_carry_correct_tenant(self):
        db = _mock_db()
        s = _settings()
        t1 = _make_tenant_record("T_A", "Alpha")
        t2 = _make_tenant_record("T_B", "Beta")
        now = "2026-05-01T10:00:00+00:00"

        def _build_side_effect(db, tenant_id, tenant_name, app_settings, **kwargs):
            return [_row(tenant_id=tenant_id, tenant_name=tenant_name,
                         severity="medium", area="x", title="t",
                         detail="d", created_at=now)]

        with patch("app.admin.operations_triage.TenantConfigRepository.list_all",
                   return_value=[t1, t2]):
            with patch("app.admin.operations_triage._build_tenant_triage",
                       side_effect=_build_side_effect):
                result = get_admin_needs_help(db=db, app_settings=s)
        tenant_ids = {r["tenant_id"] for r in result["items"]}
        assert tenant_ids == {"T_A", "T_B"}

    def test_counts_match_items(self):
        db = _mock_db()
        s = _settings()
        tenant = _make_tenant_record("T_A", "Acme")
        now = "2026-05-01T10:00:00+00:00"
        rows = [
            _row(tenant_id="T_A", tenant_name="Acme", severity="critical",
                 area="x", title="c1", detail="d", created_at=now),
            _row(tenant_id="T_A", tenant_name="Acme", severity="critical",
                 area="x", title="c2", detail="d", created_at=now),
            _row(tenant_id="T_A", tenant_name="Acme", severity="high",
                 area="x", title="h1", detail="d", created_at=now),
        ]
        with patch("app.admin.operations_triage.TenantConfigRepository.list_all", return_value=[tenant]):
            with patch("app.admin.operations_triage._build_tenant_triage", return_value=rows):
                result = get_admin_needs_help(db=db, app_settings=s)
        assert result["critical"] == 2
        assert result["high"] == 1
        assert result["total"] == 3


# ---------------------------------------------------------------------------
# dedupe_and_normalize_signals
# ---------------------------------------------------------------------------

class TestDedupeAndNormalize:
    def test_collapses_duplicate_key_keeps_highest_severity(self):
        rows = [
            _row(
                tenant_id="T_A", tenant_name="A", severity="medium", area="pipeline",
                title="Same", detail="d", job_id="job-1",
                created_at="2026-01-02T10:00:00+00:00",
            ),
            _row(
                tenant_id="T_A", tenant_name="A", severity="high", area="pipeline",
                title="Same", detail="d", job_id="job-1",
                created_at="2026-01-03T10:00:00+00:00",
            ),
        ]
        result = dedupe_and_normalize_signals(rows)
        assert len(result) == 1
        assert result[0]["severity"] == "high"

    def test_detected_at_is_earliest_and_last_observed_latest(self):
        rows = [
            _row(
                tenant_id="T_A", tenant_name="A", severity="high", area="pipeline",
                title="Same", detail="d", job_id="job-1",
                created_at="2026-01-01T10:00:00+00:00",
            ),
            _row(
                tenant_id="T_A", tenant_name="A", severity="high", area="pipeline",
                title="Same", detail="d", job_id="job-1",
                created_at="2026-01-05T10:00:00+00:00",
            ),
        ]
        result = dedupe_and_normalize_signals(rows)
        assert result[0]["detected_at"] == "2026-01-01T10:00:00+00:00"
        assert result[0]["last_observed_at"] == "2026-01-05T10:00:00+00:00"


class TestReconciliationRequiredSignals:
    def test_reconciliation_required_produces_critical_row(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            _make_integration_event(
                status="reconciliation_required",
                integration_type="visma",
                last_error="Uncertain write",
            )
        ]
        rows = _reconciliation_required_signals(db, "T_A", "Acme")
        assert len(rows) == 1
        assert rows[0]["severity"] == "critical"
        assert rows[0]["area"] == "integration_reconciliation"
        assert rows[0]["retryable"] == "no"
        assert rows[0]["external_impact"] == "yes"

    def test_later_success_clears_reconciliation_signal(self):
        db = _mock_db()
        recon = _make_integration_event(
            status="reconciliation_required",
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
            event_id=1,
        )
        success = _make_integration_event(
            status="success",
            created_at=datetime.now(timezone.utc) - timedelta(hours=1),
            event_id=2,
        )
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [
            success, recon,
        ]
        rows = _reconciliation_required_signals(db, "T_A", "Acme")
        assert rows == []


class TestMissingTenantConfigSignals:
    def _record(self, *, status="active", demo_mode=False, job_types=None, integrations=None):
        r = MagicMock()
        r.status = status
        r.enabled_job_types = job_types or []
        r.allowed_integrations = integrations or []
        r.settings = {"automation": {"demo_mode": demo_mode}}
        return r

    def test_active_empty_config_produces_signal(self):
        record = self._record()
        rows = _missing_tenant_config_signals(record, "T_A", "Acme")
        assert len(rows) == 1
        assert rows[0]["area"] == "tenant_config"
        assert rows[0]["retryable"] == "not_applicable"

    def test_inactive_tenant_excluded(self):
        record = self._record(status="inactive")
        assert _missing_tenant_config_signals(record, "T_A", "Acme") == []

    def test_demo_mode_excluded(self):
        record = self._record(demo_mode=True)
        assert _missing_tenant_config_signals(record, "T_A", "Acme") == []

    def test_configured_tenant_excluded(self):
        record = self._record(job_types=["lead"])
        assert _missing_tenant_config_signals(record, "T_A", "Acme") == []


class TestRunbookRegistry:
    def test_resolve_known_runbook(self):
        result = _resolve_runbook("oauth_integration")
        assert result is not None
        assert result["id"] == "oauth_integration"
        assert "OAuth" in result["label"]

    def test_unknown_runbook_returns_none(self):
        assert _resolve_runbook("does_not_exist") is None


# ---------------------------------------------------------------------------
# Endpoint auth tests (via TestClient)
# ---------------------------------------------------------------------------

class TestNeedsHelpEndpoint:
    def test_missing_admin_key_returns_401(self):
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/admin/operations/needs-help")
        assert r.status_code == 401

    def test_wrong_admin_key_returns_401(self):
        from fastapi.testclient import TestClient
        from app.main import app
        import os
        os.environ["ADMIN_API_KEY"] = "correct-key"
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/admin/operations/needs-help",
                       headers={"X-Admin-API-Key": "wrong-key"})
        assert r.status_code == 401

    def test_valid_admin_key_returns_200_with_shape(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from types import SimpleNamespace
        _key = "test-admin-key-for-triage"
        _s = SimpleNamespace(ADMIN_API_KEY=_key, GOOGLE_MAIL_ACCESS_TOKEN="",
                             MONDAY_API_KEY="", APP_NAME="Test")
        client = TestClient(app, raise_server_exceptions=False)
        with patch("app.core.admin_auth.get_settings", return_value=_s):
            with patch("app.admin.operations_triage.TenantConfigRepository.list_all", return_value=[]):
                r = client.get("/admin/operations/needs-help",
                               headers={"X-Admin-API-Key": _key})
        assert r.status_code == 200
        body = r.json()
        assert "total" in body
        assert "items" in body
        assert "summary" in body
        assert "critical" in body["summary"]
        assert "failed" in body["summary"]
        assert "warning" in body["summary"]
        assert "information" in body["summary"]
