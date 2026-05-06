"""
Tests for Phase 7 ready-to-market usage analytics.

Covers read-only admin metrics for active tenants, automation rate, time saved,
and blocked flows. The service should not call external APIs or expose secrets.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.analytics.usage import (
    _normalise_range,
    _range_bounds,
    get_usage_analytics,
)
from app.domain.integrations.models import IntegrationEvent
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.job_models import JobRecord


class _FakeQuery:
    def __init__(self, records):
        self.records = records

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return self.records


class _FakeDb:
    def __init__(self, mapping):
        self.mapping = mapping

    def query(self, model):
        return _FakeQuery(self.mapping.get(model, []))


def _tenant(tenant_id="T_1", name="Kund AB", status="active"):
    return SimpleNamespace(tenant_id=tenant_id, name=name, status=status)


def _job(tenant_id, job_id, job_type, status, created_at):
    return SimpleNamespace(
        tenant_id=tenant_id,
        job_id=job_id,
        job_type=job_type,
        status=status,
        created_at=created_at,
    )


def _approval(tenant_id, job_id, state, created_at):
    return SimpleNamespace(
        tenant_id=tenant_id,
        job_id=job_id,
        state=state,
        created_at=created_at,
    )


def _event(tenant_id, job_id, status, mode, created_at):
    return SimpleNamespace(
        tenant_id=tenant_id,
        job_id=job_id,
        integration_type="controlled_dispatch",
        status=status,
        payload={"dispatch_mode": mode},
        created_at=created_at,
    )


def _other_event(tenant_id, created_at):
    return SimpleNamespace(
        tenant_id=tenant_id,
        job_id="other",
        integration_type="google_mail",
        status="success",
        payload={},
        created_at=created_at,
    )


def _run_with(records, tenants):
    db = _FakeDb(records)
    with patch("app.analytics.usage.TenantConfigRepository.list_all", return_value=tenants):
        return get_usage_analytics(db, range_="30d")


class TestRangeHandling:
    def test_unknown_range_defaults_to_30d(self):
        assert _normalise_range("bad") == "30d"

    def test_all_range_has_no_from_bound(self):
        from_dt, to_dt = _range_bounds("all")
        assert from_dt is None
        assert to_dt is not None


class TestUsageAnalytics:
    def test_empty_tenant_list_returns_zero_summary(self):
        result = _run_with({}, [])
        assert result["summary"]["tenant_count"] == 0
        assert result["summary"]["active_tenants_in_range"] == 0
        assert result["tenants"] == []

    def test_active_tenants_jobs_and_blocked_flows(self):
        now = datetime.now(timezone.utc)
        tenants = [_tenant("T_1"), _tenant("T_2")]
        records = {
            JobRecord: [
                _job("T_1", "j1", "lead", "completed", now),
                _job("T_1", "j2", "lead", "awaiting_approval", now),
                _job("T_2", "j3", "invoice", "manual_review", now),
            ],
            ApprovalRequestRecord: [
                _approval("T_1", "j2", "pending", now),
            ],
            IntegrationEvent: [],
        }
        result = _run_with(records, tenants)
        assert result["summary"]["active_tenants_in_range"] == 2
        assert result["summary"]["jobs_created"] == 3
        assert result["summary"]["jobs_completed"] == 1
        assert result["summary"]["blocked_flows"] == 2
        assert result["summary"]["pending_approvals"] == 1

    def test_dispatch_metrics_include_automation_rate_and_time_saved(self):
        now = datetime.now(timezone.utc)
        tenants = [_tenant("T_1")]
        records = {
            JobRecord: [],
            ApprovalRequestRecord: [],
            IntegrationEvent: [
                _event("T_1", "j1", "success", "full_auto", now),
                _event("T_1", "j2", "success", "approval_required", now),
                _event("T_1", "j3", "failed", "manual", now),
            ],
        }
        result = _run_with(records, tenants)
        summary = result["summary"]
        assert summary["dispatches_total"] == 3
        assert summary["dispatches_successful"] == 2
        assert summary["dispatches_failed"] == 1
        assert summary["automation_rate_percent"] == 67
        assert summary["time_saved_hours"] == 0.17

    def test_non_dispatch_events_still_count_as_activity_but_not_dispatches(self):
        now = datetime.now(timezone.utc)
        tenants = [_tenant("T_1")]
        records = {
            JobRecord: [],
            ApprovalRequestRecord: [],
            IntegrationEvent: [_other_event("T_1", now)],
        }
        result = _run_with(records, tenants)
        assert result["summary"]["active_tenants_in_range"] == 1
        assert result["summary"]["dispatches_total"] == 0

    def test_old_records_outside_range_are_excluded(self):
        old = datetime.now(timezone.utc) - timedelta(days=40)
        tenants = [_tenant("T_1")]
        records = {
            JobRecord: [_job("T_1", "j1", "lead", "completed", old)],
            ApprovalRequestRecord: [],
            IntegrationEvent: [],
        }
        result = _run_with(records, tenants)
        assert result["summary"]["jobs_created"] == 0
        assert result["summary"]["active_tenants_in_range"] == 0

    def test_top_blocked_tenants_sorted_descending(self):
        now = datetime.now(timezone.utc)
        tenants = [_tenant("T_1"), _tenant("T_2")]
        records = {
            JobRecord: [
                _job("T_1", "j1", "lead", "failed", now),
                _job("T_2", "j2", "lead", "failed", now),
                _job("T_2", "j3", "lead", "manual_review", now),
            ],
            ApprovalRequestRecord: [],
            IntegrationEvent: [],
        }
        result = _run_with(records, tenants)
        assert result["top_blocked_tenants"][0]["tenant_id"] == "T_2"
        assert result["top_blocked_tenants"][0]["blocked_flows"] == 2

    def test_no_secret_values_in_response(self):
        now = datetime.now(timezone.utc)
        tenants = [_tenant("T_SECRET", name="Kund AB")]
        records = {
            JobRecord: [_job("T_SECRET", "j1", "lead", "completed", now)],
            ApprovalRequestRecord: [],
            IntegrationEvent: [],
        }
        result = _run_with(records, tenants)
        rendered = str(result)
        assert "secret-token" not in rendered
        assert "api-key" not in rendered
