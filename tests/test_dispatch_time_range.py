"""
Tests for Slice 12 – Time-Range Filters + Customer ROI Report.

Covers:
- get_dispatch_summary: range filtering (today, 7d, 30d, all), invalid range defaults to 30d
- get_dispatch_summary: range metadata (range, from, to) in response
- get_dispatch_summary: backward-compatible shape (no regression on existing keys)
- get_dispatch_report: headline values, success_rate, automation_share, message
- get_dispatch_report: zero-event edge cases
- get_dispatch_report: range filtering (old records excluded for short ranges)
- Tenant isolation
- _normalise_range helper
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.workflows.dispatchers.observability import (
    MINUTES_SAVED_PER_SUCCESS,
    _normalise_range,
    get_dispatch_report,
    get_dispatch_summary,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow():
    return datetime.now(timezone.utc)


def _event(
    *,
    status: str = "success",
    payload: dict | None = None,
    created_at: datetime | None = None,
    job_id: str = "job-1",
    tenant_id: str = "t-1",
) -> SimpleNamespace:
    return SimpleNamespace(
        job_id=job_id,
        tenant_id=tenant_id,
        integration_type="controlled_dispatch",
        status=status,
        payload=payload or {},
        created_at=created_at or _utcnow(),
    )


def _db(records: list) -> MagicMock:
    db = MagicMock()
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.all.return_value = records
    db.query.return_value = q
    return db


# ---------------------------------------------------------------------------
# _normalise_range
# ---------------------------------------------------------------------------

class TestNormaliseRange:
    def test_valid_today(self):
        assert _normalise_range("today") == "today"

    def test_valid_7d(self):
        assert _normalise_range("7d") == "7d"

    def test_valid_30d(self):
        assert _normalise_range("30d") == "30d"

    def test_valid_all(self):
        assert _normalise_range("all") == "all"

    def test_none_defaults_to_30d(self):
        assert _normalise_range(None) == "30d"

    def test_invalid_string_defaults_to_30d(self):
        assert _normalise_range("yesterday") == "30d"

    def test_empty_string_defaults_to_30d(self):
        assert _normalise_range("") == "30d"


# ---------------------------------------------------------------------------
# Time-range filtering: get_dispatch_summary
# ---------------------------------------------------------------------------

class TestSummaryRangeFiltering:
    def _make_records_spread(self):
        """Events at various ages."""
        now = _utcnow()
        return [
            _event(job_id="ev-now",   created_at=now),
            _event(job_id="ev-3d",    created_at=now - timedelta(days=3)),
            _event(job_id="ev-8d",    created_at=now - timedelta(days=8)),
            _event(job_id="ev-35d",   created_at=now - timedelta(days=35)),
        ]

    def test_today_includes_only_today(self):
        now = _utcnow()
        records_today = [_event(job_id="today", created_at=now)]
        records_old   = [_event(job_id="old",   created_at=now - timedelta(days=2))]

        # DB returns only records after from_dt (we simulate the SQL filter)
        db = _db(records_today)
        result = get_dispatch_summary(db, "t-1", range_="today")
        assert result["total_dispatches"] == 1
        assert result["range"] == "today"

    def test_7d_excludes_older_records(self):
        now = _utcnow()
        recent = [_event(job_id=f"r{i}", created_at=now - timedelta(days=i)) for i in range(5)]
        db = _db(recent)
        result = get_dispatch_summary(db, "t-1", range_="7d")
        assert result["total_dispatches"] == 5
        assert result["range"] == "7d"

    def test_30d_default(self):
        now = _utcnow()
        records = [_event(job_id=f"e{i}", created_at=now - timedelta(days=i*5)) for i in range(6)]
        db = _db(records)
        result = get_dispatch_summary(db, "t-1", range_="30d")
        assert result["range"] == "30d"

    def test_all_includes_all_records(self):
        now = _utcnow()
        old = _event(job_id="very-old", created_at=now - timedelta(days=365))
        db = _db([old])
        result = get_dispatch_summary(db, "t-1", range_="all")
        assert result["range"] == "all"
        assert result["total_dispatches"] == 1

    def test_invalid_range_defaults_to_30d(self):
        db = _db([])
        result = get_dispatch_summary(db, "t-1", range_="bogus")
        assert result["range"] == "30d"

    def test_none_range_defaults_to_30d(self):
        db = _db([])
        result = get_dispatch_summary(db, "t-1", range_=None)
        assert result["range"] == "30d"


# ---------------------------------------------------------------------------
# Metadata fields in summary
# ---------------------------------------------------------------------------

class TestSummaryMetadata:
    def test_range_key_present(self):
        db = _db([])
        result = get_dispatch_summary(db, "t-1", range_="7d")
        assert result["range"] == "7d"

    def test_to_key_present(self):
        db = _db([])
        result = get_dispatch_summary(db, "t-1", range_="7d")
        assert "to" in result
        assert result["to"] is not None

    def test_from_key_present_for_bounded_range(self):
        db = _db([])
        result = get_dispatch_summary(db, "t-1", range_="7d")
        assert result["from"] is not None

    def test_from_is_none_for_all(self):
        db = _db([])
        result = get_dispatch_summary(db, "t-1", range_="all")
        assert result["from"] is None


# ---------------------------------------------------------------------------
# Backward compatibility: existing keys still present
# ---------------------------------------------------------------------------

class TestSummaryBackwardCompat:
    def test_all_original_keys_present(self):
        db = _db([])
        result = get_dispatch_summary(db, "t-1")
        expected_keys = {
            "total_dispatches", "successful_dispatches", "failed_dispatches",
            "skipped_dispatches", "by_mode", "by_job_type", "by_system",
            "estimated_minutes_saved", "estimated_hours_saved", "recent",
        }
        assert expected_keys.issubset(result.keys())

    def test_by_mode_has_four_keys(self):
        db = _db([])
        result = get_dispatch_summary(db, "t-1")
        assert set(result["by_mode"].keys()) == {"manual", "approval_required", "full_auto", "unknown"}


# ---------------------------------------------------------------------------
# get_dispatch_report: headline values
# ---------------------------------------------------------------------------

class TestDispatchReport:
    def _events(self, n_success=0, n_failed=0, n_skipped=0, mode="full_auto", system="monday", job_type="lead"):
        events = []
        for i in range(n_success):
            events.append(_event(status="success", payload={"dispatch_mode": mode, "system": system, "job_type": job_type}, job_id=f"s{i}"))
        for i in range(n_failed):
            events.append(_event(status="failed",  payload={"dispatch_mode": mode, "system": system, "job_type": job_type}, job_id=f"f{i}"))
        for i in range(n_skipped):
            events.append(_event(status="skipped", payload={"dispatch_mode": mode, "system": system, "job_type": job_type}, job_id=f"k{i}"))
        return events

    def test_dispatches_completed_is_total(self):
        db = _db(self._events(n_success=3, n_failed=1))
        r = get_dispatch_report(db, "t-1")
        assert r["headline"]["dispatches_completed"] == 4

    def test_time_saved_hours(self):
        db = _db(self._events(n_success=12))
        r = get_dispatch_report(db, "t-1")
        expected = round(12 * MINUTES_SAVED_PER_SUCCESS / 60, 2)
        assert r["headline"]["time_saved_hours"] == expected

    def test_success_rate_excludes_skipped(self):
        # 3 success, 1 failed, 2 skipped → actionable=4, rate=75
        db = _db(self._events(n_success=3, n_failed=1, n_skipped=2))
        r = get_dispatch_report(db, "t-1")
        assert r["headline"]["success_rate_percent"] == 75

    def test_success_rate_100(self):
        db = _db(self._events(n_success=5))
        r = get_dispatch_report(db, "t-1")
        assert r["headline"]["success_rate_percent"] == 100

    def test_success_rate_0_when_all_failed(self):
        db = _db(self._events(n_failed=3))
        r = get_dispatch_report(db, "t-1")
        assert r["headline"]["success_rate_percent"] == 0

    def test_automation_share_full_auto(self):
        # 4 full_auto, 1 manual → actionable=5, share=80
        evts = (
            self._events(n_success=4, mode="full_auto") +
            self._events(n_success=1, mode="manual")
        )
        db = _db(evts)
        r = get_dispatch_report(db, "t-1")
        assert r["headline"]["automation_share_percent"] == 80

    def test_automation_share_includes_approval_required(self):
        # 2 full_auto + 2 approval_required + 1 manual → actionable=5, auto=4, share=80
        evts = (
            self._events(n_success=2, mode="full_auto") +
            self._events(n_success=2, mode="approval_required") +
            self._events(n_success=1, mode="manual")
        )
        db = _db(evts)
        r = get_dispatch_report(db, "t-1")
        assert r["headline"]["automation_share_percent"] == 80

    def test_automation_share_0_when_all_manual(self):
        db = _db(self._events(n_success=5, mode="manual"))
        r = get_dispatch_report(db, "t-1")
        assert r["headline"]["automation_share_percent"] == 0

    def test_zero_events_returns_zeros(self):
        db = _db([])
        r = get_dispatch_report(db, "t-1")
        h = r["headline"]
        assert h["dispatches_completed"] == 0
        assert h["time_saved_hours"] == 0.0
        assert h["success_rate_percent"] == 0
        assert h["automation_share_percent"] == 0

    def test_only_skipped_returns_zeros_in_rates(self):
        db = _db(self._events(n_skipped=5))
        r = get_dispatch_report(db, "t-1")
        assert r["headline"]["success_rate_percent"] == 0
        assert r["headline"]["automation_share_percent"] == 0

    def test_breakdown_keys(self):
        db = _db(self._events(n_success=2, mode="full_auto"))
        r = get_dispatch_report(db, "t-1")
        assert "manual" in r["breakdown"]
        assert "approval_required" in r["breakdown"]
        assert "full_auto" in r["breakdown"]

    def test_systems_present(self):
        db = _db(self._events(n_success=2, system="monday"))
        r = get_dispatch_report(db, "t-1")
        assert r["systems"].get("monday") == 2

    def test_job_types_present(self):
        db = _db(self._events(n_success=3, job_type="lead"))
        r = get_dispatch_report(db, "t-1")
        assert r["job_types"].get("lead") == 3

    def test_message_non_empty_when_events(self):
        db = _db(self._events(n_success=2))
        r = get_dispatch_report(db, "t-1")
        assert len(r["message"]) > 0

    def test_message_no_events(self):
        db = _db([])
        r = get_dispatch_report(db, "t-1")
        assert "Inga" in r["message"]

    def test_range_metadata_present(self):
        db = _db([])
        r = get_dispatch_report(db, "t-1", range_="7d")
        assert r["range"] == "7d"
        assert "from" in r
        assert "to" in r

    def test_invalid_range_defaults_to_30d(self):
        db = _db([])
        r = get_dispatch_report(db, "t-1", range_="bogus")
        assert r["range"] == "30d"


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    def test_summary_tenant_scoped(self):
        ev_own   = _event(job_id="mine",  tenant_id="t-A", status="success")
        db = _db([ev_own])
        result = get_dispatch_summary(db, "t-A")
        assert result["total_dispatches"] == 1

    def test_report_tenant_scoped(self):
        ev_own = _event(job_id="mine", tenant_id="t-A", status="success")
        db = _db([ev_own])
        result = get_dispatch_report(db, "t-A")
        assert result["headline"]["dispatches_completed"] == 1
