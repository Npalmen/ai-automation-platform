"""
Tests for GET /admin/operations/overview (Kapitel 2 — Global operativ översikt).
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError

from app.admin.operations_overview import (
    OperationsOverviewUnavailable,
    _build_priority_items,
    _compute_platform_status,
    _gmail_status_from_triage_rows,
    _integration_event_breakdown,
    _priority_id,
    get_operations_overview,
)
from app.admin.operations_overview_schemas import OperationsOverviewResponse
from app.admin.operations_triage import _map_priority_item, _row, get_admin_needs_help


def _settings(**kwargs):
    defaults = {
        "ADMIN_API_KEY": "test-admin-key",
        "GOOGLE_MAIL_ACCESS_TOKEN": "",
        "MONDAY_API_KEY": "",
        "FORTNOX_ACCESS_TOKEN": "",
        "APP_NAME": "Test",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**kwargs)


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


def _tenant(tenant_id="T_A", name="Acme", status="active", settings=None):
    r = MagicMock()
    r.tenant_id = tenant_id
    r.name = name
    r.status = status
    r.settings = settings or {}
    return r


class TestSchedulerSignal:
    def test_nested_scheduler_run_mode_paused(self):
        from app.admin.operations_overview import _derive_scheduler_signal

        result = _derive_scheduler_signal(
            [_tenant(settings={"scheduler": {"run_mode": "paused"}})]
        )
        assert result["status"] == "paused"

    def test_legacy_flat_run_mode_paused(self):
        from app.admin.operations_overview import _derive_scheduler_signal

        result = _derive_scheduler_signal([_tenant(settings={"run_mode": "paused"})])
        assert result["status"] == "paused"


def _integration_event(
    integration_type="visma",
    status="success",
    tenant_id="T_A",
    created_at=None,
):
    e = MagicMock()
    e.integration_type = integration_type
    e.status = status
    e.tenant_id = tenant_id
    e.created_at = created_at or datetime.now(timezone.utc)
    return e


def _overview_patches(db, tenants=None, triage_rows=None, events=None):
    tenants = tenants if tenants is not None else []
    triage_rows = triage_rows if triage_rows is not None else []
    events = events if events is not None else []

    def query_side_effect(model):
        q = MagicMock()
        q.filter.return_value = q
        q.count.return_value = 0
        if model.__name__ == "IntegrationEvent":
            q.all.return_value = events
        else:
            q.all.return_value = []
        return q

    db.query.side_effect = query_side_effect

    return (
        patch(
            "app.admin.operations_overview.TenantConfigRepository.list_all",
            return_value=tenants,
        ),
        patch(
            "app.admin.operations_overview.collect_all_triage_rows",
            return_value=triage_rows,
        ),
    )


class TestComputePlatformStatus:
    def _counters(self, **kwargs):
        base = {
            "stuck_jobs": {"value": 0},
            "failed_jobs": {"value": 0},
            "integration_errors": {"value": 0},
            "open_manual_reviews": {"value": 0},
        }
        base.update(kwargs)
        return base

    def test_critical_when_database_failed(self):
        result = _compute_platform_status(
            self._counters(),
            {},
            {"database": {"status": "failed"}},
        )
        assert result["level"] == "critical"

    def test_failed_when_stuck_jobs(self):
        result = _compute_platform_status(
            self._counters(stuck_jobs={"value": 2}),
            {"gmail": {"status": "healthy", "affected_tenants": 0}},
            {"database": {"status": "healthy"}},
        )
        assert result["level"] == "failed"

    def test_failed_when_integration_failed_multi_tenant(self):
        result = _compute_platform_status(
            self._counters(),
            {"visma": {"status": "failed", "affected_tenants": 2}},
            {"database": {"status": "healthy"}},
        )
        assert result["level"] == "failed"

    def test_warning_when_failed_jobs(self):
        result = _compute_platform_status(
            self._counters(failed_jobs={"value": 1}),
            {"gmail": {"status": "healthy", "affected_tenants": 0}},
            {"database": {"status": "healthy"}},
        )
        assert result["level"] == "warning"

    def test_warning_when_unknown_integration_not_healthy(self):
        result = _compute_platform_status(
            self._counters(),
            {
                "gmail": {"status": "healthy", "affected_tenants": 0},
                "visma": {"status": "unknown", "affected_tenants": 0},
            },
            {"database": {"status": "healthy"}},
        )
        assert result["level"] == "warning"

    def test_healthy_when_no_signals(self):
        result = _compute_platform_status(
            self._counters(),
            {
                "gmail": {"status": "healthy", "affected_tenants": 0},
                "visma": {"status": "healthy", "affected_tenants": 0},
            },
            {"database": {"status": "healthy"}},
        )
        assert result["level"] == "healthy"


class TestPriorityIds:
    def test_job_id_prefix(self):
        row = _row(
            tenant_id="T_A", tenant_name="A", severity="high", area="pipeline",
            title="t", detail="d", job_id="job-123",
        )
        assert _priority_id(row) == "job:job-123"

    def test_approval_id_prefix(self):
        row = _row(
            tenant_id="T_A", tenant_name="A", severity="high", area="approval",
            title="t", detail="d", approval_id="appr-456",
        )
        assert _priority_id(row) == "approval:appr-456"

    def test_hash_prefix_stable(self):
        row = _row(
            tenant_id="T_A", tenant_name="A", severity="medium", area="scheduler",
            title="Scheduler failure", detail="d", created_at="2026-01-01T00:00:00+00:00",
        )
        assert _priority_id(row).startswith("hash:")
        assert _priority_id(row) == _priority_id(row)

    def test_hash_changes_with_title(self):
        r1 = _row(
            tenant_id="T_A", tenant_name="A", severity="medium", area="scheduler",
            title="A", detail="d", created_at="2026-01-01T00:00:00+00:00",
        )
        r2 = _row(
            tenant_id="T_A", tenant_name="A", severity="medium", area="scheduler",
            title="B", detail="d", created_at="2026-01-01T00:00:00+00:00",
        )
        assert _priority_id(r1) != _priority_id(r2)

    def test_source_id_precedence(self):
        row = _row(
            tenant_id="T_A", tenant_name="A", severity="high", area="pipeline",
            title="t", detail="d", job_id="job-123",
            source_id="integration_event:99",
        )
        assert _priority_id(row) == "integration_event:99"


class TestMapPriorityItem:
    def test_link_points_to_customer(self):
        row = _row(
            tenant_id="T_A", tenant_name="Acme", severity="high", area="pipeline",
            title="t", detail="d", job_id="job-1",
            retryable="not_applicable", external_impact="no",
        )
        item = _map_priority_item(row)
        assert item["link"] == "/customers/T_A"
        assert item["safe_retry_available"] == "unknown"
        assert item["external_action_may_have_occurred"] == "no"


class TestPrioritySorting:
    def test_severity_first(self):
        rows = [
            _row(tenant_id="T", tenant_name="T", severity="info", area="pipeline",
                 title="i", detail="d", created_at="2026-01-03T00:00:00+00:00"),
            _row(tenant_id="T", tenant_name="T", severity="critical", area="pipeline",
                 title="c", detail="d", created_at="2026-01-01T00:00:00+00:00"),
        ]
        items = _build_priority_items(rows, limit=10)
        assert items[0]["severity"] == "critical"

    def test_external_before_internal_same_severity(self):
        rows = [
            _row(tenant_id="T", tenant_name="T", severity="high", area="pipeline",
                 title="internal", detail="d", created_at="2026-01-01T00:00:00+00:00"),
            _row(tenant_id="T", tenant_name="T", severity="high", area="integration_event",
                 title="external", detail="d", created_at="2026-01-02T00:00:00+00:00"),
        ]
        items = _build_priority_items(rows, limit=10)
        assert items[0]["category"] == "integration_event"

    def test_oldest_first_within_level(self):
        rows = [
            _row(tenant_id="T", tenant_name="T", severity="high", area="pipeline",
                 title="newer", detail="d", created_at="2026-01-03T00:00:00+00:00"),
            _row(tenant_id="T", tenant_name="T", severity="high", area="pipeline",
                 title="older", detail="d", created_at="2026-01-01T00:00:00+00:00"),
        ]
        items = _build_priority_items(rows, limit=10)
        assert items[0]["title"] == "older"

    def test_deterministic_across_calls(self):
        rows = [
            _row(tenant_id="T_A", tenant_name="A", severity="high", area="pipeline",
                 title="x", detail="d", job_id="j1", created_at="2026-01-01T00:00:00+00:00"),
            _row(tenant_id="T_B", tenant_name="B", severity="medium", area="integration",
                 title="gmail", detail="d", created_at="2026-01-02T00:00:00+00:00"),
        ]
        first = _build_priority_items(rows, limit=10)
        second = _build_priority_items(rows, limit=10)
        assert [i["id"] for i in first] == [i["id"] for i in second]


class TestIntegrationStatus:
    def test_gmail_unknown_when_no_tenants(self):
        result = _gmail_status_from_triage_rows([], tenant_count=0)
        assert result["status"] == "unknown"

    def test_gmail_healthy_when_no_rows_and_tenants_exist(self):
        result = _gmail_status_from_triage_rows([], tenant_count=3)
        assert result["status"] == "healthy"

    def test_gmail_failed_on_critical_row(self):
        rows = [
            _row(
                tenant_id="T", tenant_name="T", severity="critical", area="integration",
                title="Gmail integration is error", detail="d",
            ),
        ]
        result = _gmail_status_from_triage_rows(rows, tenant_count=1)
        assert result["status"] == "failed"

    def test_visma_unknown_without_events(self):
        db = _mock_db()
        breakdown = _integration_event_breakdown(
            db, datetime.now(timezone.utc) - timedelta(hours=24),
        )
        assert breakdown["visma"]["total_events"] == 0

    def test_visma_healthy_with_success_only(self):
        db = _mock_db()
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        events = [_integration_event("visma", "success", "T_A")]
        db.query.return_value.filter.return_value.all.return_value = events
        breakdown = _integration_event_breakdown(db, since)
        assert breakdown["visma"]["total_events"] == 1
        assert breakdown["visma"]["issues"] == 0


class TestGetOperationsOverview:
    def test_returns_full_shape(self):
        db = _mock_db()
        tenants = [_tenant("T_A", status="active"), _tenant("T_B", status="inactive")]
        p1, p2 = _overview_patches(db, tenants=tenants)
        with p1, p2:
            result = get_operations_overview(db=db, app_settings=_settings())
        OperationsOverviewResponse.model_validate(result)
        assert result["period"]["hours"] == 24
        assert result["counters"]["active_tenants"]["value"] == 1
        assert result["counters"]["active_tenants"]["window_hours"] is None
        assert result["counters"]["jobs_last_24h"]["window_hours"] == 24
        assert result["counters"]["failed_jobs"]["window_hours"] == 48
        assert result["system"]["api"]["status"] == "healthy"
        assert "API-processen" in result["system"]["api"]["description"]
        assert result["system"]["backup"]["status"] == "unknown"

    def test_raises_on_query_failure(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.count.side_effect = OperationalError(
            "stmt", {}, Exception("db down"),
        )
        with patch(
            "app.admin.operations_overview.TenantConfigRepository.list_all",
            return_value=[_tenant()],
        ):
            with pytest.raises(OperationsOverviewUnavailable):
                get_operations_overview(db=db, app_settings=_settings())

    def test_multi_tenant_priority_tenant_ids(self):
        db = _mock_db()
        triage = [
            _row(tenant_id="T_A", tenant_name="A", severity="high", area="pipeline",
                 title="a", detail="d", job_id="j-a"),
            _row(tenant_id="T_B", tenant_name="B", severity="medium", area="pipeline",
                 title="b", detail="d", job_id="j-b"),
            _row(tenant_id="T_C", tenant_name="C", severity="info", area="pipeline",
                 title="c", detail="d", job_id="j-c"),
        ]
        p1, p2 = _overview_patches(
            db,
            tenants=[_tenant("T_A"), _tenant("T_B"), _tenant("T_C")],
            triage_rows=triage,
        )
        with p1, p2:
            result = get_operations_overview(db=db, app_settings=_settings())
        tenant_ids = {p["tenant_id"] for p in result["priorities"]}
        assert tenant_ids == {"T_A", "T_B", "T_C"}

    def test_no_secrets_in_response(self):
        db = _mock_db()
        secret = "super-secret-token"
        s = _settings(GOOGLE_MAIL_ACCESS_TOKEN=secret)
        p1, p2 = _overview_patches(db, tenants=[_tenant()], triage_rows=[])
        with p1, p2:
            result = get_operations_overview(db=db, app_settings=s)
        blob = OperationsOverviewResponse.model_validate(result).model_dump_json()
        assert secret not in blob
        assert "password" not in blob.lower()
        assert "api_key" not in blob.lower()


class TestPerformanceSmoke:
    def test_fifty_tenants_under_two_seconds(self):
        db = _mock_db()
        tenants = [_tenant(f"T_{i}") for i in range(50)]
        p1, p2 = _overview_patches(db, tenants=tenants, triage_rows=[])
        start = time.perf_counter()
        with p1, p2:
            get_operations_overview(db=db, app_settings=_settings())
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0


class TestOverviewEndpoint:
    def test_missing_admin_key_returns_401(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/admin/operations/overview")
        assert r.status_code == 401

    def test_tenant_key_returns_401(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)
        r = client.get(
            "/admin/operations/overview",
            headers={"X-API-Key": "tenant-only-key"},
        )
        assert r.status_code == 401

    def test_valid_admin_key_returns_200(self):
        from fastapi.testclient import TestClient
        from app.main import app

        key = "overview-admin-key"
        s = _settings(ADMIN_API_KEY=key)
        with TestClient(app, raise_server_exceptions=False) as client:
            with patch("app.core.admin_auth.get_settings", return_value=s):
                with patch(
                    "app.admin.operations_overview.TenantConfigRepository.list_all",
                    return_value=[],
                ):
                    with patch(
                        "app.admin.operations_overview.collect_all_triage_rows",
                        return_value=[],
                    ):
                        r = client.get(
                            "/admin/operations/overview",
                            headers={"X-Admin-API-Key": key},
                        )
        assert r.status_code == 200
        body = r.json()
        OperationsOverviewResponse.model_validate(body)
        assert body["period"]["hours"] == 24
        assert "application" not in body.get("system", {})

    def test_query_failure_returns_503(self):
        from fastapi.testclient import TestClient
        from app.main import app

        key = "overview-admin-key"
        s = _settings(ADMIN_API_KEY=key)
        client = TestClient(app, raise_server_exceptions=False)
        with patch("app.core.admin_auth.get_settings", return_value=s):
            with patch(
                "app.admin.operations_overview.get_operations_overview",
                side_effect=OperationsOverviewUnavailable(),
            ):
                r = client.get(
                    "/admin/operations/overview",
                    headers={"X-Admin-API-Key": key},
                )
        assert r.status_code == 503


class TestCollectAllTriageRowsRefactor:
    def test_get_admin_needs_help_still_works(self):
        db = _mock_db()
        rows = [
            _row(
                tenant_id="T_A", tenant_name="A", severity="critical", area="x",
                title="c", detail="d",
                created_at=datetime.now(timezone.utc).isoformat(),
            ),
        ]
        with patch("app.admin.operations_triage.collect_all_triage_rows", return_value=rows):
            result = get_admin_needs_help(db=db, app_settings=_settings(), limit=50)
        assert result["total"] == 1
        assert result["critical"] == 1
