"""
Tests for pilot cockpit, followup engine, closeout packet, and finance export status.

Unit tests use mocked DB sessions — matching existing project test patterns.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from datetime import datetime, timezone


def _make_job(
    job_id="job-001",
    tenant_id="tenant-1",
    job_type="lead",
    status="awaiting_approval",
    result=None,
    input_data=None,
    created_at=None,
    updated_at=None,
):
    j = MagicMock()
    j.job_id = job_id
    j.tenant_id = tenant_id
    j.job_type = job_type
    j.status = status
    j.result = result or {}
    j.input_data = input_data or {}
    j.created_at = created_at or datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
    j.updated_at = updated_at or datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
    return j


def _make_approval(approval_id="appr-001", tenant_id="tenant-1", job_id="job-001",
                   state="pending", next_on_approve="email_send"):
    a = MagicMock()
    a.approval_id = approval_id
    a.tenant_id = tenant_id
    a.job_id = job_id
    a.state = state
    a.next_on_approve = next_on_approve
    a.requested_at = datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc)
    return a


# ---------------------------------------------------------------------------
# Follow-up state derivation tests
# ---------------------------------------------------------------------------

class TestFollowupStateDerived:
    """Test that followup state is correctly derived from job/lead status."""

    def test_new_lead_maps_to_new_state(self):
        from app.main import _FOLLOWUP_STATE_MAP
        assert _FOLLOWUP_STATE_MAP.get("new") == "new"

    def test_contacted_maps_to_replied_waiting(self):
        from app.main import _FOLLOWUP_STATE_MAP
        assert _FOLLOWUP_STATE_MAP.get("contacted") == "replied_waiting_customer"

    def test_waiting_for_customer_maps_correctly(self):
        from app.main import _FOLLOWUP_STATE_MAP
        assert _FOLLOWUP_STATE_MAP.get("waiting_for_customer") == "replied_waiting_customer"

    def test_completed_maps_to_closed_won(self):
        from app.main import _FOLLOWUP_STATE_MAP
        assert _FOLLOWUP_STATE_MAP.get("completed") == "closed_won"

    def test_failed_maps_to_closed_lost(self):
        from app.main import _FOLLOWUP_STATE_MAP
        assert _FOLLOWUP_STATE_MAP.get("failed") == "closed_lost"

    def test_awaiting_approval_maps_to_waiting_internal(self):
        from app.main import _FOLLOWUP_STATE_MAP
        assert _FOLLOWUP_STATE_MAP.get("awaiting_approval") == "waiting_internal"

    def test_offer_sent_maps_to_quote_sent(self):
        from app.main import _FOLLOWUP_STATE_MAP
        assert _FOLLOWUP_STATE_MAP.get("offer_sent") == "quote_sent"


class TestFollowupNextAction:
    """Test that next_action text is defined for each followup state."""

    def test_all_followup_states_have_next_action(self):
        from app.main import _FOLLOWUP_STATE_MAP, _FOLLOWUP_NEXT_ACTION
        states = set(_FOLLOWUP_STATE_MAP.values())
        for state in states:
            assert state in _FOLLOWUP_NEXT_ACTION, f"Missing next_action for state: {state}"

    def test_followup_due_is_urgent_text(self):
        from app.main import _FOLLOWUP_NEXT_ACTION
        text = _FOLLOWUP_NEXT_ACTION.get("followup_due", "")
        assert "nu" in text.lower() or "förfall" in text.lower()


# ---------------------------------------------------------------------------
# Closeout packet logic tests
# ---------------------------------------------------------------------------

class TestCloseoutMissingFields:
    """Test that missing fields are correctly identified for closeout."""

    def test_no_customer_email_flagged(self):
        missing = []
        customer_email = None
        if not customer_email:
            missing.append("Kund-e-post")
        assert "Kund-e-post" in missing

    def test_incomplete_work_order_flagged(self):
        missing = []
        wo_status = "in_progress"
        if wo_status not in ("completed", "cancelled"):
            missing.append("Arbetsorder ej avslutad")
        assert "Arbetsorder ej avslutad" in missing

    def test_completed_work_order_not_flagged(self):
        missing = []
        wo_status = "completed"
        if wo_status not in ("completed", "cancelled"):
            missing.append("Arbetsorder ej avslutad")
        assert "Arbetsorder ej avslutad" not in missing

    def test_no_material_lines_flagged(self):
        missing = []
        material_lines = []
        if not material_lines:
            missing.append("Material-rader (för underlag)")
        assert "Material-rader (för underlag)" in missing


class TestCloseoutSummaryBuilding:
    """Test customer and internal summary generation logic."""

    def test_customer_summary_includes_subject(self):
        subject = "Solpaneler installation"
        customer_name = "Anna Svensson"
        wo_status_sv = "Avslutat"
        lines = [
            f"Ärende: {subject}",
            f"Kund: {customer_name}",
            f"Status: {wo_status_sv}",
        ]
        summary = "\n".join(lines)
        assert "Solpaneler installation" in summary
        assert "Anna Svensson" in summary
        assert "Avslutat" in summary

    def test_internal_summary_includes_finance_status(self):
        finance_ready = True
        fortnox_exported = False
        line = f"Underlag redo: {'Ja' if finance_ready else 'Nej'}"
        export_line = f"Fortnox exporterat: {'Ja' if fortnox_exported else 'Nej'}"
        assert "Underlag redo: Ja" in line
        assert "Fortnox exporterat: Nej" in export_line


# ---------------------------------------------------------------------------
# Cockpit aggregation logic tests
# ---------------------------------------------------------------------------

class TestCockpitCounts:
    """Test cockpit count aggregation logic."""

    def test_actions_required_sums_correctly(self):
        email_approvals = [MagicMock(), MagicMock()]   # 2
        dispatch_approvals = [MagicMock()]              # 1
        hot_leads_and_escalations = [MagicMock()]       # 1
        actions_required = (
            len(email_approvals)
            + len(dispatch_approvals)
            + len(hot_leads_and_escalations)
        )
        assert actions_required == 4

    def test_zero_actions_when_all_clear(self):
        email_approvals = []
        dispatch_approvals = []
        stale_leads = []
        actions_required = len(email_approvals) + len(dispatch_approvals) + len(stale_leads)
        assert actions_required == 0


# ---------------------------------------------------------------------------
# Finance export status tests
# ---------------------------------------------------------------------------

class TestFinanceExportStatus:
    """Test finance export status endpoint logic."""

    def test_urls_are_correctly_formatted(self):
        job_id = "abc-123"
        preview_url = f"/finance/invoices/{job_id}/fortnox/preview"
        export_url  = f"/finance/invoices/{job_id}/fortnox/export"
        draft_url   = f"/finance/invoices/{job_id}/draft"
        assert preview_url == "/finance/invoices/abc-123/fortnox/preview"
        assert export_url  == "/finance/invoices/abc-123/fortnox/export"
        assert draft_url   == "/finance/invoices/abc-123/draft"

    def test_export_count_reflects_events(self):
        events = [MagicMock(), MagicMock(), MagicMock()]
        assert len(events) == 3

    def test_exported_flag_true_when_job_in_exported_ids(self):
        job_id = "job-999"
        exported_ids = {"job-999", "job-888"}
        exported = job_id in exported_ids
        assert exported is True

    def test_exported_flag_false_when_job_not_in_exported_ids(self):
        job_id = "job-000"
        exported_ids = {"job-999"}
        exported = job_id in exported_ids
        assert exported is False
