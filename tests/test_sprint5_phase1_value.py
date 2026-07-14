"""Sprint 5 — Phase 1 value layer: focused unit tests.

Covers:
- OfferDraft enrichment (contact fields, missing_fields, human_approval_required)
- _infer_lead_status fix (ask_questions → waiting_for_customer)
- Invoice routing classification (debt_collection, reminder, clean)
- Daily report rendering (counts, rendered_text)
- Approval command parser (GODKÄNN, STOPPA, ÄNDRA, unknown)
- Derived job status helper (waiting_for_customer, quote_draft_prepared)
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.lead.analyzer import analyze_lead
from app.lead.missing_info import compute_missing_info
from app.lead.models import LeadAnalysis, MissingInfoResult
from app.lead.offer_draft import build_offer_draft
from app.invoice.routing import classify_invoice_routing
from app.workflows.approval_command_parser import parse_approval_command
from app.workflows.derived_status import derive_job_status
from app.domain.workflows.models import Job
from app.domain.workflows.statuses import JobStatus
from app.domain.workflows.enums import JobType


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_complete_ev_charger_analysis() -> tuple[LeadAnalysis, MissingInfoResult]:
    analysis = LeadAnalysis(
        lead_type="ev_charger",
        intent="ready_to_buy",
        urgency="low",
        customer_type="private",
        confidence=0.9,
    )
    missing = MissingInfoResult(
        required_fields=["address", "main_fuse"],
        present_fields=["address", "main_fuse"],
        missing_fields=[],
        optional_fields=[],
        completeness_score=1.0,
    )
    return analysis, missing


def _make_incomplete_analysis() -> tuple[LeadAnalysis, MissingInfoResult]:
    analysis = LeadAnalysis(
        lead_type="ev_charger",
        intent="researching",
        urgency="low",
        customer_type="unknown",
        confidence=0.5,
    )
    missing = MissingInfoResult(
        required_fields=["address", "main_fuse", "charger_count"],
        present_fields=[],
        missing_fields=["address", "main_fuse", "charger_count"],
        optional_fields=[],
        completeness_score=0.0,
    )
    return analysis, missing


def _make_job_with_history(
    status: JobStatus = JobStatus.COMPLETED,
    processor_history: list | None = None,
) -> Job:
    job = Job(
        job_id="test-job-1",
        tenant_id="TENANT_TEST",
        job_type=JobType.LEAD,
        status=status,
        input_data={},
        result=None,
        processor_history=processor_history or [],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    return job


# ── OfferDraft enrichment ─────────────────────────────────────────────────────

def test_offer_draft_includes_contact_and_approval_flag():
    analysis, missing = _make_complete_ev_charger_analysis()
    entities = {
        "customer_name": "Erik Lindström",
        "email": "erik@example.com",
        "phone": "070-123 45 67",
        "address": "Storgatan 1, Järfälla",
    }
    draft = build_offer_draft(analysis, missing, entities)

    assert draft is not None
    assert draft.customer_name == "Erik Lindström"
    assert draft.customer_email == "erik@example.com"
    assert draft.customer_phone == "070-123 45 67"
    assert draft.address == "Storgatan 1, Järfälla"
    assert draft.human_approval_required is True
    assert isinstance(draft.missing_fields, list)

    d = draft.to_dict()
    assert d["customer_name"] == "Erik Lindström"
    assert d["human_approval_required"] is True
    assert "disclaimer" in d


def test_offer_draft_none_when_incomplete():
    analysis, missing = _make_incomplete_analysis()
    draft = build_offer_draft(analysis, missing, {})
    assert draft is None


def test_offer_draft_missing_fields_populated():
    analysis = LeadAnalysis(
        lead_type="ev_charger",
        intent="ready_to_buy",
        urgency="low",
        customer_type="private",
        confidence=0.85,
    )
    missing = MissingInfoResult(
        required_fields=["address", "main_fuse", "charger_count"],
        present_fields=["address", "main_fuse"],
        missing_fields=["charger_count"],
        optional_fields=[],
        completeness_score=0.667,
    )
    # Just below threshold — should return None
    draft = build_offer_draft(analysis, missing, {})
    assert draft is None


# ── _infer_lead_status fix ────────────────────────────────────────────────────

def test_infer_lead_status_ask_questions_returns_waiting_for_customer():
    from app.workflows.processors.lead_analyzer_processor import _infer_lead_status
    result = _infer_lead_status("ask_questions", {})
    assert result == "waiting_for_customer"


def test_infer_lead_status_create_offer_draft_returns_quote_draft_prepared():
    from app.workflows.processors.lead_analyzer_processor import _infer_lead_status
    result = _infer_lead_status("create_offer_draft", {})
    assert result == "quote_draft_prepared"


# ── Invoice routing ───────────────────────────────────────────────────────────

def _clean_payload() -> dict:
    return {
        "validation_status": "approved",
        "approval_route": "approval_required",
        "missing_critical": [],
        "duplicate_suspected": False,
        "validation": {"is_valid": True, "issues": []},
    }


def test_invoice_routing_debt_collection():
    payload = _clean_payload()
    result = classify_invoice_routing(
        invoice_payload=payload,
        subject="INKASSO — Obetalad faktura",
        body="Vi kontaktar er angående inkassokrav. Beloppet är förfallet.",
    )
    assert result["invoice_routing"] == "debt_collection_review"
    assert len(result["risk_signals"]) > 0


def test_invoice_routing_kronofogden():
    payload = _clean_payload()
    result = classify_invoice_routing(
        invoice_payload=payload,
        subject="Betalningsföreläggande från Kronofogden",
        body="Kronofogdemyndigheten har utfärdat ett betalningsföreläggande.",
    )
    assert result["invoice_routing"] == "debt_collection_review"


def test_invoice_routing_payment_reminder():
    payload = _clean_payload()
    result = classify_invoice_routing(
        invoice_payload=payload,
        subject="Betalningspåminnelse faktura 2024-001",
        body="Vi påminner er om en obetald faktura med påminnelseavgift.",
    )
    assert result["invoice_routing"] == "payment_reminder_review"
    assert len(result["risk_signals"]) > 0


def test_invoice_routing_clean_forward_to_accounting():
    payload = _clean_payload()
    result = classify_invoice_routing(
        invoice_payload=payload,
        subject="Faktura 2024-001 från Leverantör AB",
        body="Bifogat finner ni faktura avseende levererade tjänster.",
    )
    assert result["invoice_routing"] == "forward_to_accounting"
    assert result["risk_signals"] == []


def test_invoice_routing_validation_failed_manual_review():
    payload = {
        "validation_status": "manual_review",
        "approval_route": "manual_review",
        "missing_critical": ["invoice_number"],
        "duplicate_suspected": False,
        "validation": {"is_valid": False, "issues": ["missing_invoice_number"]},
    }
    result = classify_invoice_routing(
        invoice_payload=payload,
        subject="Faktura",
        body="Se bifogad faktura.",
    )
    assert result["invoice_routing"] == "manual_review_required"


# ── Approval command parser ───────────────────────────────────────────────────

def test_parse_approval_command_godkann():
    result = parse_approval_command("GODKÄNN")
    assert result["parsed"] is True
    assert result["command"] == "approve"
    assert result["confidence"] == "high"


def test_parse_approval_command_approve_english():
    result = parse_approval_command("APPROVE")
    assert result["parsed"] is True
    assert result["command"] == "approve"


def test_parse_approval_command_stoppa():
    result = parse_approval_command("STOPPA")
    assert result["parsed"] is True
    assert result["command"] == "reject"


def test_parse_approval_command_reject_english():
    result = parse_approval_command("REJECT")
    assert result["parsed"] is True
    assert result["command"] == "reject"


def test_parse_approval_command_andra():
    result = parse_approval_command("ÄNDRA: Hej Maria, vi återkommer imorgon.")
    assert result["parsed"] is True
    assert result["command"] == "change"
    assert result["change_text"] == "Hej Maria, vi återkommer imorgon."


def test_parse_approval_command_change_english():
    result = parse_approval_command("CHANGE: Updated reply text here.")
    assert result["parsed"] is True
    assert result["command"] == "change"
    assert "Updated reply text" in result["change_text"]


def test_parse_approval_command_unknown():
    result = parse_approval_command("Skicka mer information tack.")
    assert result["parsed"] is False
    assert result["command"] is None


def test_parse_approval_command_empty():
    result = parse_approval_command("")
    assert result["parsed"] is False


def test_parse_approval_command_skips_quoted_lines():
    body = "> On 15 Jul, someone wrote:\n> GODKÄNN\nSTOPPA"
    result = parse_approval_command(body)
    assert result["parsed"] is True
    assert result["command"] == "reject"


def test_parse_approval_command_stops_at_signature():
    body = "--\nGODKÄNN"
    result = parse_approval_command(body)
    assert result["parsed"] is False


# ── Derived status helper ─────────────────────────────────────────────────────

def _processor_entry(name: str, payload: dict) -> dict:
    return {
        "processor": name,
        "result": {
            "status": "completed",
            "summary": "ok",
            "requires_human_review": False,
            "payload": payload,
        },
    }


def test_derive_job_status_waiting_for_customer():
    history = [
        _processor_entry("lead_analyzer_processor", {
            "next_action": "ask_questions",
            "lead_status": "waiting_for_customer",
            "offer_draft": None,
            "generated_question_message": "Vilken säkring har du?",
        }),
    ]
    job = _make_job_with_history(status=JobStatus.AWAITING_APPROVAL, processor_history=history)
    result = derive_job_status(job)
    assert result["derived_status"] == "waiting_for_customer"
    assert result["offer_draft_present"] is False


def test_derive_job_status_quote_draft_prepared():
    history = [
        _processor_entry("lead_analyzer_processor", {
            "next_action": "create_offer_draft",
            "lead_status": "quote_draft_prepared",
            "offer_draft": {
                "summary": "Preliminärt underlag",
                "human_approval_required": True,
            },
        }),
    ]
    job = _make_job_with_history(status=JobStatus.AWAITING_APPROVAL, processor_history=history)
    result = derive_job_status(job)
    assert result["derived_status"] == "quote_draft_prepared"
    assert result["offer_draft_present"] is True


def test_derive_job_status_risk_review_required():
    job = _make_job_with_history(status=JobStatus.MANUAL_REVIEW)
    result = derive_job_status(job)
    assert result["derived_status"] == "risk_review_required"


def test_derive_job_status_invoice_routing_needed():
    history = [
        _processor_entry("invoice_processor", {
            "invoice_routing": "debt_collection_review",
            "risk_signals": ["inkasso"],
            "routing_reason": "Debt collection detected.",
        }),
    ]
    job = _make_job_with_history(
        status=JobStatus.AWAITING_APPROVAL,
        processor_history=history,
    )
    result = derive_job_status(job)
    assert result["derived_status"] == "invoice_routing_needed"
    assert result["invoice_routing"] == "debt_collection_review"


# ── Daily report rendering (unit test via mocked DB) ─────────────────────────

def test_daily_report_counts_and_rendered_text():
    """Test report generation with mocked job repository."""
    from app.reporting.daily_report import generate_daily_report

    # Build two jobs: one quote_draft_prepared, one waiting_for_customer
    quote_job = _make_job_with_history(
        status=JobStatus.AWAITING_APPROVAL,
        processor_history=[
            _processor_entry("lead_analyzer_processor", {
                "next_action": "create_offer_draft",
                "lead_status": "quote_draft_prepared",
                "offer_draft": {"summary": "test", "human_approval_required": True},
                "service_profile_type": "ev_charger",
            }),
            _processor_entry("entity_extraction_processor", {
                "entities": {"customer_name": "Erik Lindström"},
                "confidence": 0.9,
            }),
        ],
    )
    quote_job.job_type = JobType.LEAD

    waiting_job = _make_job_with_history(
        status=JobStatus.AWAITING_APPROVAL,
        processor_history=[
            _processor_entry("lead_analyzer_processor", {
                "next_action": "ask_questions",
                "lead_status": "waiting_for_customer",
                "offer_draft": None,
            }),
        ],
    )
    waiting_job.job_type = JobType.LEAD

    mock_db = MagicMock()

    with patch("app.reporting.daily_report.JobRepository.list_jobs", return_value=[quote_job, waiting_job]):
        with patch("app.reporting.daily_report.ApprovalRequestRepository.count_pending_for_tenant", return_value=2):
            report = generate_daily_report(mock_db, tenant_id="TENANT_TEST", since_hours=24)

    assert report["tenant_id"] == "TENANT_TEST"
    assert report["period_hours"] == 24
    assert "generated_at" in report
    assert report["counts"]["leads_ready_for_quote"] >= 1
    assert report["counts"]["leads_waiting_for_customer"] >= 1
    assert report["counts"]["pending_approvals"] == 2
    assert "God morgon" in report["rendered_text"]
    assert "Krowolf" in report["rendered_text"]
    assert isinstance(report["top_priorities"], list)
