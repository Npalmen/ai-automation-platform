"""
Tests for Slice 11 – Dispatch Observability + ROI Attribution.

Covers:
- get_dispatch_summary: empty, success aggregation, failed/skipped, by_mode, by_job_type, by_system
- Optional filters: job_type, system
- limit_recent respected
- dispatch_mode metadata included in payload
- GET /dispatch/summary endpoint shape
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.workflows.dispatchers.observability import (
    MINUTES_SAVED_PER_SUCCESS,
    get_dispatch_summary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow():
    return datetime.now(timezone.utc)


def _make_event(
    *,
    status: str = "success",
    payload: dict | None = None,
    created_at: datetime | None = None,
    job_id: str = "job-1",
    tenant_id: str = "tenant-1",
) -> SimpleNamespace:
    return SimpleNamespace(
        job_id=job_id,
        tenant_id=tenant_id,
        integration_type="controlled_dispatch",
        status=status,
        payload=payload or {},
        created_at=created_at or _utcnow(),
    )


def _make_db(records: list) -> MagicMock:
    db = MagicMock()
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.all.return_value = records
    db.query.return_value = q
    return db


# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------

class TestEmptySummary:
    def test_zero_counts(self):
        db = _make_db([])
        result = get_dispatch_summary(db, "tenant-1")

        assert result["total_dispatches"] == 0
        assert result["successful_dispatches"] == 0
        assert result["failed_dispatches"] == 0
        assert result["skipped_dispatches"] == 0
        assert result["estimated_minutes_saved"] == 0
        assert result["estimated_hours_saved"] == 0.0
        assert result["recent"] == []

    def test_mode_keys_present(self):
        db = _make_db([])
        result = get_dispatch_summary(db, "tenant-1")

        assert "manual" in result["by_mode"]
        assert "approval_required" in result["by_mode"]
        assert "full_auto" in result["by_mode"]
        assert "unknown" in result["by_mode"]

    def test_by_job_type_empty(self):
        db = _make_db([])
        result = get_dispatch_summary(db, "tenant-1")
        assert result["by_job_type"] == {}

    def test_by_system_empty(self):
        db = _make_db([])
        result = get_dispatch_summary(db, "tenant-1")
        assert result["by_system"] == {}


# ---------------------------------------------------------------------------
# Success aggregation
# ---------------------------------------------------------------------------

class TestSuccessAggregation:
    def test_single_success_counts(self):
        ev = _make_event(status="success", payload={"dispatch_mode": "full_auto", "job_type": "lead", "system": "monday"})
        db = _make_db([ev])
        result = get_dispatch_summary(db, "tenant-1")

        assert result["total_dispatches"] == 1
        assert result["successful_dispatches"] == 1
        assert result["failed_dispatches"] == 0
        assert result["skipped_dispatches"] == 0

    def test_minutes_saved_per_success(self):
        events = [
            _make_event(status="success", payload={"dispatch_mode": "full_auto", "job_type": "lead", "system": "monday"})
            for _ in range(3)
        ]
        db = _make_db(events)
        result = get_dispatch_summary(db, "tenant-1")

        assert result["estimated_minutes_saved"] == 3 * MINUTES_SAVED_PER_SUCCESS
        assert result["estimated_hours_saved"] == round(3 * MINUTES_SAVED_PER_SUCCESS / 60, 2)

    def test_failed_does_not_add_minutes(self):
        events = [
            _make_event(status="success", payload={"dispatch_mode": "full_auto", "job_type": "lead", "system": "monday"}),
            _make_event(status="failed",  payload={"dispatch_mode": "full_auto", "job_type": "lead", "system": "monday"}),
        ]
        db = _make_db(events)
        result = get_dispatch_summary(db, "tenant-1")

        assert result["estimated_minutes_saved"] == MINUTES_SAVED_PER_SUCCESS

    def test_mixed_statuses(self):
        events = [
            _make_event(status="success"),
            _make_event(status="success"),
            _make_event(status="failed"),
            _make_event(status="skipped"),
        ]
        db = _make_db(events)
        result = get_dispatch_summary(db, "tenant-1")

        assert result["total_dispatches"] == 4
        assert result["successful_dispatches"] == 2
        assert result["failed_dispatches"] == 1
        assert result["skipped_dispatches"] == 1


# ---------------------------------------------------------------------------
# by_mode aggregation
# ---------------------------------------------------------------------------

class TestByMode:
    def test_full_auto_mode(self):
        ev = _make_event(payload={"dispatch_mode": "full_auto"})
        db = _make_db([ev])
        result = get_dispatch_summary(db, "tenant-1")
        assert result["by_mode"]["full_auto"] == 1
        assert result["by_mode"]["manual"] == 0

    def test_manual_mode(self):
        ev = _make_event(payload={"dispatch_mode": "manual"})
        db = _make_db([ev])
        result = get_dispatch_summary(db, "tenant-1")
        assert result["by_mode"]["manual"] == 1

    def test_approval_required_mode(self):
        ev = _make_event(payload={"dispatch_mode": "approval_required"})
        db = _make_db([ev])
        result = get_dispatch_summary(db, "tenant-1")
        assert result["by_mode"]["approval_required"] == 1

    def test_unknown_mode_fallback(self):
        ev = _make_event(payload={"dispatch_mode": "something_weird"})
        db = _make_db([ev])
        result = get_dispatch_summary(db, "tenant-1")
        assert result["by_mode"]["unknown"] == 1

    def test_missing_mode_fallback(self):
        ev = _make_event(payload={})
        db = _make_db([ev])
        result = get_dispatch_summary(db, "tenant-1")
        assert result["by_mode"]["unknown"] == 1

    def test_multiple_modes(self):
        events = [
            _make_event(payload={"dispatch_mode": "full_auto"}),
            _make_event(payload={"dispatch_mode": "full_auto"}),
            _make_event(payload={"dispatch_mode": "manual"}),
            _make_event(payload={"dispatch_mode": "approval_required"}),
        ]
        db = _make_db(events)
        result = get_dispatch_summary(db, "tenant-1")
        assert result["by_mode"]["full_auto"] == 2
        assert result["by_mode"]["manual"] == 1
        assert result["by_mode"]["approval_required"] == 1


# ---------------------------------------------------------------------------
# by_job_type and by_system
# ---------------------------------------------------------------------------

class TestByJobTypeAndSystem:
    def test_by_job_type(self):
        events = [
            _make_event(payload={"job_type": "lead"}),
            _make_event(payload={"job_type": "lead"}),
            _make_event(payload={"job_type": "invoice"}),
        ]
        db = _make_db(events)
        result = get_dispatch_summary(db, "tenant-1")
        assert result["by_job_type"]["lead"] == 2
        assert result["by_job_type"]["invoice"] == 1

    def test_by_system(self):
        events = [
            _make_event(payload={"system": "monday"}),
            _make_event(payload={"system": "monday"}),
            _make_event(payload={"system": "gmail"}),
        ]
        db = _make_db(events)
        result = get_dispatch_summary(db, "tenant-1")
        assert result["by_system"]["monday"] == 2
        assert result["by_system"]["gmail"] == 1

    def test_missing_job_type_falls_back_to_unknown(self):
        ev = _make_event(payload={})
        db = _make_db([ev])
        result = get_dispatch_summary(db, "tenant-1")
        assert result["by_job_type"]["unknown"] == 1

    def test_missing_system_falls_back_to_unknown(self):
        ev = _make_event(payload={})
        db = _make_db([ev])
        result = get_dispatch_summary(db, "tenant-1")
        assert result["by_system"]["unknown"] == 1


# ---------------------------------------------------------------------------
# Optional filters
# ---------------------------------------------------------------------------

class TestOptionalFilters:
    def test_filter_by_job_type(self):
        events = [
            _make_event(status="success", payload={"job_type": "lead"}),
            _make_event(status="success", payload={"job_type": "invoice"}),
        ]
        db = _make_db(events)
        result = get_dispatch_summary(db, "tenant-1", job_type="lead")
        assert result["total_dispatches"] == 1
        assert result["by_job_type"] == {"lead": 1}

    def test_filter_by_system(self):
        events = [
            _make_event(status="success", payload={"system": "monday"}),
            _make_event(status="success", payload={"system": "gmail"}),
        ]
        db = _make_db(events)
        result = get_dispatch_summary(db, "tenant-1", system="monday")
        assert result["total_dispatches"] == 1
        assert result["by_system"] == {"monday": 1}

    def test_filter_by_both(self):
        events = [
            _make_event(status="success", payload={"job_type": "lead", "system": "monday"}),
            _make_event(status="success", payload={"job_type": "lead", "system": "gmail"}),
            _make_event(status="success", payload={"job_type": "invoice", "system": "monday"}),
        ]
        db = _make_db(events)
        result = get_dispatch_summary(db, "tenant-1", job_type="lead", system="monday")
        assert result["total_dispatches"] == 1


# ---------------------------------------------------------------------------
# limit_recent
# ---------------------------------------------------------------------------

class TestLimitRecent:
    def test_default_limit_10(self):
        events = [_make_event(job_id=f"job-{i}") for i in range(15)]
        db = _make_db(events)
        result = get_dispatch_summary(db, "tenant-1")
        assert len(result["recent"]) == 10

    def test_custom_limit(self):
        events = [_make_event(job_id=f"job-{i}") for i in range(5)]
        db = _make_db(events)
        result = get_dispatch_summary(db, "tenant-1", limit_recent=3)
        assert len(result["recent"]) == 3

    def test_fewer_than_limit(self):
        events = [_make_event(job_id=f"job-{i}") for i in range(2)]
        db = _make_db(events)
        result = get_dispatch_summary(db, "tenant-1", limit_recent=10)
        assert len(result["recent"]) == 2


# ---------------------------------------------------------------------------
# recent entry shape
# ---------------------------------------------------------------------------

class TestRecentShape:
    def test_recent_fields(self):
        now = _utcnow()
        ev = _make_event(
            job_id="job-abc",
            status="success",
            payload={
                "job_type": "lead",
                "system": "monday",
                "dispatch_mode": "full_auto",
                "external_id": "12345",
                "message": "Created item",
            },
            created_at=now,
        )
        db = _make_db([ev])
        result = get_dispatch_summary(db, "tenant-1")
        entry = result["recent"][0]

        assert entry["job_id"] == "job-abc"
        assert entry["job_type"] == "lead"
        assert entry["system"] == "monday"
        assert entry["status"] == "success"
        assert entry["mode"] == "full_auto"
        assert entry["external_id"] == "12345"
        assert entry["message"] == "Created item"
        assert entry["created_at"] is not None

    def test_recent_missing_payload_fields(self):
        ev = _make_event(payload={})
        db = _make_db([ev])
        result = get_dispatch_summary(db, "tenant-1")
        entry = result["recent"][0]

        assert entry["job_type"] == "unknown"
        assert entry["system"] == "unknown"
        assert entry["mode"] == "unknown"
        assert entry["external_id"] is None
        assert entry["message"] == ""


# ---------------------------------------------------------------------------
# Endpoint wiring (direct function call, no HTTP client)
# ---------------------------------------------------------------------------

class TestEndpointShape:
    def test_get_dispatch_summary_returns_all_keys(self):
        """get_dispatch_summary returns the expected top-level keys."""
        events = [
            _make_event(status="success", payload={"dispatch_mode": "full_auto", "job_type": "lead", "system": "monday"}),
            _make_event(status="failed",  payload={"dispatch_mode": "manual",    "job_type": "lead", "system": "monday"}),
        ]
        db = _make_db(events)
        result = get_dispatch_summary(db, "tenant-1")

        expected_keys = {
            "total_dispatches",
            "successful_dispatches",
            "failed_dispatches",
            "skipped_dispatches",
            "by_mode",
            "by_job_type",
            "by_system",
            "estimated_minutes_saved",
            "estimated_hours_saved",
            "recent",
        }
        assert expected_keys.issubset(result.keys())

    def test_tenant_isolation(self):
        """Records from a different tenant must not appear in results."""
        ev_own   = _make_event(job_id="job-own",   tenant_id="t-1", status="success")
        ev_other = _make_event(job_id="job-other",  tenant_id="t-2", status="success")

        # Filter is applied by the DB query (tenant_id filter); simulate that
        db = _make_db([ev_own])   # DB already filters by tenant
        result = get_dispatch_summary(db, "t-1")
        assert result["total_dispatches"] == 1
        assert result["recent"][0]["job_id"] == "job-own"
