"""Tests for the Follow-up Question Engine.

Covers:
- evaluate_information_completeness for lead, customer_inquiry, invoice
- follow-up send_email injection in lead and inquiry builders
- no follow-up email when complete or no sender_email
- invoice missing-info surfacing in internal task (no external email)
- explicit input_data.actions bypass (no injection)
- lead/inquiry/invoice builders still produce their normal actions
"""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from app.workflows.processors.action_dispatch_processor import (
    _build_inquiry_default_actions,
    _build_invoice_default_actions,
    _build_lead_default_actions,
    _resolve_actions,
)
from app.workflows.processors.ai_processor_utils import evaluate_information_completeness


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_job(job_type_str: str, input_data: dict) -> MagicMock:
    job = MagicMock()
    job.job_id = str(uuid4())
    job.tenant_id = "tenant-test"
    job.processor_history = []

    from app.domain.workflows.models import JobType
    job.job_type = JobType(job_type_str)
    job.input_data = input_data
    return job


def _lead_job(input_data: dict) -> MagicMock:
    return _make_job("lead", input_data)


def _inquiry_job(input_data: dict) -> MagicMock:
    return _make_job("customer_inquiry", input_data)


def _invoice_job(input_data: dict) -> MagicMock:
    return _make_job("invoice", input_data)


# ── evaluate_information_completeness: lead ───────────────────────────────────

class TestLeadCompleteness:
    def test_complete_lead_is_ready(self):
        result = evaluate_information_completeness("lead", {
            "sender": {"email": "user@example.com", "phone": "0701234567"},
            "message_text": "Jag är intresserad av era tjänster och vill veta mer.",
        })
        assert result["is_complete"] is True
        assert result["recommended_status"] == "ready_for_action"
        assert result["missing_fields"] == []

    def test_lead_missing_email(self):
        result = evaluate_information_completeness("lead", {
            "message_text": "Intresserad av er produkt.",
        })
        assert "email" in result["missing_fields"]
        assert result["is_complete"] is False
        assert result["recommended_status"] == "needs_customer_info"

    def test_lead_missing_request_details(self):
        result = evaluate_information_completeness("lead", {
            "sender": {"email": "user@example.com"},
            "message_text": "",
            "subject": "",
        })
        assert "request_details" in result["missing_fields"]
        assert result["is_complete"] is False

    def test_lead_missing_phone_not_blocking(self):
        result = evaluate_information_completeness("lead", {
            "sender": {"email": "user@example.com"},
            "message_text": "Intresserad av era tjänster och vill boka ett möte.",
        })
        assert result["is_complete"] is True
        assert "phone" in result["missing_fields"]

    def test_lead_follow_up_questions_present_when_incomplete(self):
        result = evaluate_information_completeness("lead", {
            "message_text": "",
            "subject": "",
        })
        assert len(result["follow_up_questions"]) > 0


# ── evaluate_information_completeness: customer_inquiry ──────────────────────

class TestInquiryCompleteness:
    def test_complete_inquiry_is_ready(self):
        result = evaluate_information_completeness("customer_inquiry", {
            "sender": {"email": "user@example.com"},
            "message_text": "Produkten slutar fungera när jag trycker på knappen.",
        })
        assert result["is_complete"] is True
        assert result["recommended_status"] == "ready_for_action"

    def test_inquiry_vague_message_is_incomplete(self):
        result = evaluate_information_completeness("customer_inquiry", {
            "sender": {"email": "user@example.com"},
            "message_text": "Problem",
        })
        assert "problem_description" in result["missing_fields"]
        assert result["is_complete"] is False
        assert result["recommended_status"] == "needs_customer_info"

    def test_inquiry_no_email_is_incomplete(self):
        result = evaluate_information_completeness("customer_inquiry", {
            "message_text": "Produkten slutar fungera när jag trycker på knappen.",
        })
        assert "email" in result["missing_fields"]
        assert result["is_complete"] is False


# ── evaluate_information_completeness: invoice ────────────────────────────────

class TestInvoiceCompleteness:
    def test_complete_invoice_is_ready(self):
        result = evaluate_information_completeness("invoice", {
            "sender": {"name": "Leverantör AB", "email": "bill@supplier.com"},
            "subject": "Faktura #12345",
            "message_text": "Se bifogad faktura. Belopp: 5 000 kr. Förfallodatum: 2026-05-01.",
        })
        assert result["is_complete"] is True
        assert result["recommended_status"] == "ready_for_action"

    def test_invoice_missing_amount_number_date_is_incomplete(self):
        result = evaluate_information_completeness("invoice", {
            "sender": {"name": "Leverantör AB"},
            "subject": "Faktura",
            "message_text": "Se bifogad faktura.",
        })
        assert "invoice_details" in result["missing_fields"]
        assert result["is_complete"] is False
        assert result["recommended_status"] == "needs_internal_review"

    def test_invoice_no_customer_facing_questions(self):
        result = evaluate_information_completeness("invoice", {
            "sender": {"name": "Leverantör AB"},
            "subject": "Faktura",
            "message_text": "Faktura bifogad.",
        })
        assert result["follow_up_questions"] == []


# ── lead builder: follow-up injection ────────────────────────────────────────

class TestLeadFollowUp:
    def test_incomplete_lead_with_email_adds_followup_email(self):
        job = _lead_job({
            "sender": {"email": "kund@example.com"},
            "message_text": "",
            "subject": "",
        })
        actions = _build_lead_default_actions(job)
        types = [a["type"] for a in actions]
        assert "send_email" in types
        follow_up = next(a for a in actions if a["type"] == "send_email")
        assert follow_up["to"] == "kund@example.com"

    def test_incomplete_lead_without_email_no_followup(self):
        job = _lead_job({
            "message_text": "",
            "subject": "",
        })
        actions = _build_lead_default_actions(job)
        types = [a["type"] for a in actions]
        assert "send_email" not in types

    def test_complete_lead_no_followup_email(self):
        job = _lead_job({
            "sender": {"email": "kund@example.com", "phone": "0701234567"},
            "message_text": "Jag är intresserad av era tjänster och vill veta mer.",
        })
        actions = _build_lead_default_actions(job)
        types = [a["type"] for a in actions]
        assert "send_email" not in types

    def test_lead_builder_creates_monday_item(self):
        job = _lead_job({
            "sender": {"email": "kund@example.com"},
            "message_text": "Intresserad av er produkt och prissättning.",
        })
        actions = _build_lead_default_actions(job)
        assert any(a["type"] == "create_monday_item" for a in actions)

    def test_lead_missing_fields_in_column_values(self):
        job = _lead_job({
            "message_text": "",
            "subject": "",
        })
        actions = _build_lead_default_actions(job)
        monday = next(a for a in actions if a["type"] == "create_monday_item")
        assert "missing_fields" in monday["column_values"]
        assert "completeness_status" in monday["column_values"]


# ── inquiry builder: follow-up injection ─────────────────────────────────────

class TestInquiryFollowUp:
    def test_incomplete_inquiry_with_email_adds_followup(self):
        job = _inquiry_job({
            "sender": {"email": "kund@example.com"},
            "subject": "Problem",
            "message_text": "Hjälp",
        })
        actions = _build_inquiry_default_actions(job)
        types = [a["type"] for a in actions]
        assert "send_email" in types
        follow_ups = [a for a in actions if a["type"] == "send_email" and a["to"] == "kund@example.com"]
        assert len(follow_ups) == 1

    def test_complete_inquiry_no_followup_to_customer(self):
        job = _inquiry_job({
            "sender": {"email": "kund@example.com"},
            "subject": "Problem med produkten",
            "message_text": "Produkten slutar fungera varje gång jag trycker på knappen.",
        })
        actions = _build_inquiry_default_actions(job)
        customer_emails = [a for a in actions if a["type"] == "send_email" and a["to"] == "kund@example.com"]
        assert len(customer_emails) == 0

    def test_inquiry_still_sends_to_support(self):
        job = _inquiry_job({
            "sender": {"email": "kund@example.com"},
            "subject": "Problem",
            "message_text": "Produkten slutar fungera när jag trycker på knappen.",
        })
        actions = _build_inquiry_default_actions(job)
        support_handoffs = [a for a in actions if a["type"] == "send_internal_handoff" and "support" in a.get("to", "")]
        assert len(support_handoffs) == 1


# ── invoice builder: no external email ───────────────────────────────────────

class TestInvoiceFollowUp:
    def test_incomplete_invoice_no_customer_email(self):
        job = _invoice_job({
            "sender": {"name": "Leverantör AB", "email": "bill@supplier.com"},
            "subject": "Faktura",
            "message_text": "Se bifogad faktura.",
        })
        actions = _build_invoice_default_actions(job)
        types = [a["type"] for a in actions]
        assert "send_email" not in types

    def test_incomplete_invoice_internal_task_includes_missing_info(self):
        job = _invoice_job({
            "sender": {"name": "Leverantör AB"},
            "subject": "Faktura",
            "message_text": "Se bifogad faktura.",
        })
        actions = _build_invoice_default_actions(job)
        internal = next(a for a in actions if a["type"] == "create_internal_task")
        assert "SAKNAD INFORMATION" in internal["description"]
        assert "completeness" in internal["metadata"]

    def test_invoice_builder_produces_monday_and_task(self):
        job = _invoice_job({
            "sender": {"name": "Leverantör AB"},
            "subject": "Faktura #99",
            "message_text": "Belopp: 10 000 kr.",
        })
        actions = _build_invoice_default_actions(job)
        types = [a["type"] for a in actions]
        assert "create_monday_item" in types
        assert "create_internal_task" in types


# ── explicit actions bypass ───────────────────────────────────────────────────

class TestExplicitActionsOverride:
    def test_explicit_input_actions_not_augmented(self):
        explicit = [{"type": "send_email", "to": "boss@company.com", "subject": "X", "body": "Y"}]
        job = _lead_job({
            "actions": explicit,
            "sender": {"email": ""},
            "message_text": "",
            "subject": "",
        })
        actions = _resolve_actions(job)
        assert actions == explicit
        assert len(actions) == 1
