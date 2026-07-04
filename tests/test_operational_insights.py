"""Tests for operational insights engine (P2), dashboard KPIs (P1), and SLA reminders (P3)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


TENANT = "T_TEST_INSIGHTS"


def _job_record(
    *,
    job_id: str | None = None,
    tenant_id: str = TENANT,
    job_type: str = "lead",
    status: str = "completed",
    input_data: dict | None = None,
    result: dict | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
):
    now = datetime.now(timezone.utc)
    r = SimpleNamespace(
        job_id=job_id or str(uuid.uuid4()),
        tenant_id=tenant_id,
        job_type=job_type,
        status=status,
        input_data=input_data or {},
        result=result or {},
        created_at=created_at or now,
        updated_at=updated_at or now,
    )
    return r


# ── Insight row schema tests (P2a) ──────────────────────────────────────────

def test_insight_row_schema():
    from app.insights.engine import _insight
    row = _insight(
        "stale_lead", "high", "Test title", "Test detail",
        job_id="j1", pipeline_stage="lead", evidence=["a=1"],
    )
    assert row["type"] == "stale_lead"
    assert row["severity"] == "high"
    assert row["title"] == "Test title"
    assert row["detail"] == "Test detail"
    assert row["job_id"] == "j1"
    assert row["pipeline_stage"] == "lead"
    assert isinstance(row["evidence"], list)


def test_insight_row_schema_defaults():
    from app.insights.engine import _insight
    row = _insight("missing_customer_info", "medium", "T", "D")
    assert row["job_id"] is None
    assert row["pipeline_stage"] is None
    assert row["evidence"] == []


# ── Underlag ready logic tests (P1c) ────────────────────────────────────────

def test_is_underlag_ready_invoice():
    from app.insights.engine import _is_underlag_ready
    job = _job_record(job_type="invoice", status="completed")
    assert _is_underlag_ready(job, {}, set()) is True


def test_is_underlag_ready_lead_without_wo():
    from app.insights.engine import _is_underlag_ready
    job = _job_record(job_type="lead", status="completed")
    assert _is_underlag_ready(job, {}, set()) is False


def test_is_underlag_ready_lead_with_completed_wo():
    from app.insights.engine import _is_underlag_ready
    job = _job_record(job_type="lead", status="completed")
    workspace = {"work_order": {"status": "completed"}}
    assert _is_underlag_ready(job, workspace, set()) is True


def test_is_underlag_ready_already_exported():
    from app.insights.engine import _is_underlag_ready
    job = _job_record(job_type="invoice", status="completed")
    assert _is_underlag_ready(job, {}, {job.job_id}) is False


def test_is_underlag_ready_not_completed():
    from app.insights.engine import _is_underlag_ready
    job = _job_record(job_type="invoice", status="pending")
    assert _is_underlag_ready(job, {}, set()) is False


# ── Insight engine helper tests (P2b, P2c) ──────────────────────────────────

def test_get_processor_payload():
    from app.insights.engine import _get_processor_payload
    history = [
        {"processor": "lead_analyzer_processor", "result": {"payload": {"lead_score": {"score": 80}}}},
        {"processor": "other", "result": {"payload": {"x": 1}}},
    ]
    p = _get_processor_payload(history, "lead_analyzer_processor")
    assert p["lead_score"]["score"] == 80

    empty = _get_processor_payload(history, "nonexistent")
    assert empty == {}


def test_get_missing_fields():
    from app.insights.engine import _get_missing_fields
    lead = {"missing_info": {"missing_fields": ["email", "phone"]}}
    support = {"support_missing_info": {"missing_fields": ["phone", "address"]}}
    fields = _get_missing_fields(lead, support)
    assert "email" in fields
    assert "phone" in fields
    assert "address" in fields
    assert len(fields) == 3  # deduplicated


def test_ensure_aware_naive():
    from app.insights.engine import _ensure_aware
    naive = datetime(2026, 1, 1, 12, 0, 0)
    aware = _ensure_aware(naive)
    assert aware.tzinfo == timezone.utc


def test_ensure_aware_already_aware():
    from app.insights.engine import _ensure_aware
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    result = _ensure_aware(aware)
    assert result == aware


def test_ensure_aware_none():
    from app.insights.engine import _ensure_aware
    assert _ensure_aware(None) is None


# ── Severity ordering (P2a) ────────────────────────────────────────────────

def test_severity_order_keys():
    from app.insights.engine import SEVERITY_ORDER
    assert SEVERITY_ORDER["critical"] < SEVERITY_ORDER["high"]
    assert SEVERITY_ORDER["high"] < SEVERITY_ORDER["medium"]
    assert SEVERITY_ORDER["medium"] < SEVERITY_ORDER["info"]


# ── KPI compute function tests (P1a-d) ──────────────────────────────────────

def test_count_email_approvals_returns_int():
    from app.insights.engine import _count_email_approvals
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = 3
    assert _count_email_approvals(db, TENANT) == 3


def test_count_dispatch_approvals_returns_int():
    from app.insights.engine import _count_dispatch_approvals
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = 0
    assert _count_dispatch_approvals(db, TENANT) == 0


def test_count_email_approvals_none_returns_zero():
    from app.insights.engine import _count_email_approvals
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = None
    assert _count_email_approvals(db, TENANT) == 0


# ── SLA reminder logic tests (P3a-b) ────────────────────────────────────────

def test_sla_pass_demo_mode_skips():
    from app.insights.sla_reminders import run_sla_reminder_pass
    db = MagicMock()
    result = run_sla_reminder_pass(db, TENANT, {"control": {"demo_mode": True}})
    assert result["skipped"] is True
    assert result["reason"] == "demo_mode"


def test_sla_pass_already_run_today_skips():
    from app.insights.sla_reminders import run_sla_reminder_pass
    db = MagicMock()
    # Use UTC date to match the production code (datetime.now(timezone.utc))
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    result = run_sla_reminder_pass(db, TENANT, {
        "scheduler_state": {"last_sla_reminder_at": today_utc + "T08:00:00"},
    })
    assert result["skipped"] is True
    assert result["reason"] == "already_run_today"


def test_sla_pass_lead_disabled_skips():
    from app.insights.sla_reminders import run_sla_reminder_pass
    db = MagicMock()
    result = run_sla_reminder_pass(db, TENANT, {"auto_actions": {"lead": False}})
    assert result["skipped"] is True
    assert result["reason"] == "lead_automation_disabled"


def test_customer_name_from_sender_dict():
    from app.insights.sla_reminders import _customer_name
    assert _customer_name({"sender": {"name": "Kund AB"}}) == "Kund AB"


def test_customer_name_from_flat_key():
    from app.insights.sla_reminders import _customer_name
    assert _customer_name({"sender_name": "Flat Kund"}) == "Flat Kund"


def test_customer_name_missing():
    from app.insights.sla_reminders import _customer_name
    assert _customer_name({}) is None


# ── Digest with insights (P2e) ──────────────────────────────────────────────

def test_digest_body_includes_insights():
    from app.main import _build_digest_body
    insights = [
        {"severity": "high", "title": "Hett lead väntar"},
        {"severity": "medium", "title": "Saknar kundinfo"},
    ]
    subject, body = _build_digest_body("T_TEST", {"leads_today": 3}, {"estimated_hours_saved": 1.5}, insights=insights)
    assert "Viktigt just nu:" in body
    assert "[HIGH] Hett lead väntar" in body
    assert "[MEDIUM] Saknar kundinfo" in body


def test_digest_body_without_insights():
    from app.main import _build_digest_body
    subject, body = _build_digest_body("T_TEST", {"leads_today": 0}, {"estimated_hours_saved": 0})
    assert "Viktigt just nu:" not in body


def test_digest_body_with_empty_insights():
    from app.main import _build_digest_body
    subject, body = _build_digest_body("T_TEST", {"leads_today": 0}, {"estimated_hours_saved": 0}, insights=[])
    assert "Viktigt just nu:" not in body


# ── Insight type constants (P2a) ────────────────────────────────────────────

def test_insight_types_tuple():
    from app.insights.engine import INSIGHT_TYPES
    assert "stale_lead" in INSIGHT_TYPES
    assert "hot_lead_pending" in INSIGHT_TYPES
    assert "underlag_ready" in INSIGHT_TYPES
    assert "fortnox_export_pending" in INSIGHT_TYPES
    assert "email_approval_waiting" in INSIGHT_TYPES
    assert "delivery_incomplete" in INSIGHT_TYPES
    assert "stale_active_case" in INSIGHT_TYPES
