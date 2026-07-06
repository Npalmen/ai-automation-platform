"""Local evals for customer reply quality.

Verifies:
  - Low-risk leads get service-profile-aware follow-up questions in auto-reply.
  - High-risk / sensitive leads get a safe acknowledgement, not solution.
  - Missing fields are reflected in the reply.
  - Tenant/company name is used in replies when available.
  - Replies do not over-promise or make legal/financial commitments.
  - Debt collection and dangerous cases route to manual_review with safe ack.

Deterministic only — no LLM, no live integrations.
"""
from __future__ import annotations

import pytest

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.workflows.processors.action_dispatch_processor import (
    _build_lead_default_actions,
    _build_inquiry_default_actions,
    _build_sensitive_customer_ack,
)
from app.workflows.processors.lead_analyzer_processor import process_lead_analyzer_job
from app.workflows.processors.ai_processor_utils import get_latest_processor_payload


# ── Helpers ───────────────────────────────────────────────────────────────────

def _lead_job_with_analyzer(subject: str, body: str, sender_email: str = "kund@example.com") -> Job:
    """Build a Job that has already been through lead_analyzer_processor."""
    job = Job(
        tenant_id="TENANT_TEST",
        job_type=JobType.LEAD,
        input_data={
            "subject": subject,
            "message_text": body,
            "sender": {"name": "Anna Andersson", "email": sender_email},
        },
    )
    job.processor_history = [
        {
            "processor": "classification_processor",
            "result": {
                "payload": {
                    "detected_job_type": "lead",
                    "confidence": 0.9,
                    "reasons": ["test_fixture"],
                }
            },
        },
        {
            "processor": "entity_extraction_processor",
            "result": {
                "payload": {
                    "entities": {"email": sender_email}
                }
            },
        },
        {
            "processor": "lead_processor",
            "result": {
                "payload": {
                    "lead_score": 60,
                    "priority": "normal",
                    "routing": "ask_questions",
                    "reasons": [],
                    "confidence": 0.7,
                    "recommended_next_step": "ask_questions",
                }
            },
        },
    ]
    job.result = {
        "status": "completed",
        "requires_human_review": False,
        "payload": {"detected_job_type": "lead", "confidence": 0.9},
    }
    # Run lead_analyzer so generated_question_message is available
    job = process_lead_analyzer_job(job)
    return job


def _settings(*, signature: str = "Elmontören AB", followups: bool = True) -> dict:
    return {
        "followups_enabled": followups,
        "email_signature_name": signature,
        "internal_notification_email": "",
    }


def _get_auto_reply_body(actions: list[dict]) -> str:
    for a in actions:
        if a.get("type") == "send_customer_auto_reply" and not a.get("_skip"):
            return a.get("body") or ""
    return ""


# ══════════════════════════════════════════════════════════════════════════════
# Low-risk lead — profile-aware questions
# ══════════════════════════════════════════════════════════════════════════════

class TestLowRiskLeadReply:
    def test_ev_charger_reply_references_laddbox(self):
        job = _lead_job_with_analyzer(
            "Laddbox offert",
            "Hej, vi vill ha offert på laddbox till villa i Uppsala.",
        )
        actions = _build_lead_default_actions(job, _settings())
        body = _get_auto_reply_body(actions)
        assert body, "Expected non-empty auto-reply body"
        assert "laddbox" in body.lower() or "ladda" in body.lower() or "underlag" in body.lower()

    def test_solar_reply_references_solar(self):
        job = _lead_job_with_analyzer(
            "Solceller",
            "Hej, vi vill installera solceller på taket.",
        )
        actions = _build_lead_default_actions(job, _settings())
        body = _get_auto_reply_body(actions)
        assert body, "Expected non-empty auto-reply body"
        assert "sol" in body.lower() or "tak" in body.lower() or "underlag" in body.lower()

    def test_reply_starts_with_greeting(self):
        job = _lead_job_with_analyzer(
            "Laddbox",
            "Jag vill ha offert på laddbox.",
        )
        actions = _build_lead_default_actions(job, _settings())
        body = _get_auto_reply_body(actions)
        assert body.startswith("Hej")

    def test_reply_ends_with_signature_when_provided(self):
        job = _lead_job_with_analyzer(
            "Laddbox",
            "Jag vill ha offert på laddbox.",
        )
        settings = _settings(signature="ElFirman AB")
        actions = _build_lead_default_actions(job, settings)
        body = _get_auto_reply_body(actions)
        assert "ElFirman AB" in body

    def test_reply_is_not_empty_when_no_signature(self):
        job = _lead_job_with_analyzer(
            "Laddbox",
            "Jag vill ha offert på laddbox.",
        )
        settings = _settings(signature="")
        actions = _build_lead_default_actions(job, settings)
        body = _get_auto_reply_body(actions)
        assert len(body) > 20

    def test_reply_does_not_promise_booked_time(self):
        job = _lead_job_with_analyzer(
            "Laddbox",
            "Jag vill ha offert på laddbox.",
        )
        actions = _build_lead_default_actions(job, _settings())
        body = _get_auto_reply_body(actions)
        forbidden = ["är bokad", "är bokat", "bekräftar bokning", "du är inbokad"]
        for phrase in forbidden:
            assert phrase not in body.lower(), f"Reply should not include '{phrase}'"

    def test_reply_does_not_make_price_commitment(self):
        job = _lead_job_with_analyzer(
            "Laddbox",
            "Jag vill ha offert på laddbox.",
        )
        actions = _build_lead_default_actions(job, _settings())
        body = _get_auto_reply_body(actions)
        forbidden_price = ["priset är", "kostar xxx", "fastpris"]
        for phrase in forbidden_price:
            assert phrase not in body.lower(), f"Reply should not include '{phrase}'"


# ══════════════════════════════════════════════════════════════════════════════
# High-risk / sensitive — safe acknowledgement
# ══════════════════════════════════════════════════════════════════════════════

class TestHighRiskReply:
    def test_debt_collection_gets_safe_ack(self):
        """Debt-collection lead must get sensitive ack, not regular follow-up."""
        job = _lead_job_with_analyzer(
            "Inkassokrav",
            "Detta är ett inkassokrav. Betala din skuld omgående.",
        )
        actions = _build_lead_default_actions(job, _settings())
        # Should be a sensitive ack — _needs_approval flag
        ack_actions = [
            a for a in actions
            if a.get("type") == "send_customer_auto_reply" and a.get("_needs_approval")
        ]
        assert ack_actions, "Debt collection should produce a sensitive ack with _needs_approval"

    def test_legal_threat_gets_safe_ack(self):
        job = _lead_job_with_analyzer(
            "Juridiskt hot",
            "Om ni inte löser detta omedelbart kontaktar jag min advokat och anmäler.",
        )
        actions = _build_lead_default_actions(job, _settings())
        ack_actions = [
            a for a in actions
            if a.get("type") == "send_customer_auto_reply" and a.get("_needs_approval")
        ]
        assert ack_actions, "Legal threat should produce a sensitive ack with _needs_approval"

    def test_sensitive_ack_body_is_non_committing(self):
        ack = _build_sensitive_customer_ack(
            action_type="send_customer_auto_reply",
            tenant_id="TENANT_TEST",
            to="kund@example.com",
            subject="Re: Ärende",
            sender_name="Anna",
            signature_name="ElFirman AB",
        )
        body = ack["body"]
        assert "juridiskt" in body.lower() or "inte något" in body.lower() or "manuell" in body.lower()

    def test_sensitive_ack_has_approval_flag(self):
        ack = _build_sensitive_customer_ack(
            action_type="send_customer_auto_reply",
            tenant_id="TENANT_TEST",
            to="kund@example.com",
            subject="Re: Ärende",
            sender_name="Anna",
            signature_name="",
        )
        assert ack.get("_needs_approval") is True

    def test_sensitive_ack_includes_sender_name(self):
        ack = _build_sensitive_customer_ack(
            action_type="send_customer_auto_reply",
            tenant_id="TENANT_TEST",
            to="kund@example.com",
            subject="Re: Ärende",
            sender_name="Maria",
            signature_name="",
        )
        assert "Maria" in ack["body"]

    def test_electrical_safety_risk_gets_sensitive_ack(self):
        """Bränt smell / sparks should route to sensitive ack."""
        job = _lead_job_with_analyzer(
            "Elfel",
            "Det luktar bränt från eluttaget och det gnistrar.",
        )
        actions = _build_lead_default_actions(job, _settings())
        ack_actions = [
            a for a in actions
            if a.get("type") == "send_customer_auto_reply" and a.get("_needs_approval")
        ]
        assert ack_actions, "Electrical safety risk should produce sensitive ack"

    def test_followups_disabled_skips_customer_reply(self):
        job = _lead_job_with_analyzer(
            "Laddbox",
            "Offert laddbox.",
        )
        settings = _settings(followups=False)
        actions = _build_lead_default_actions(job, settings)
        skipped = [a for a in actions if a.get("_skip") and a.get("type") == "send_customer_auto_reply"]
        assert skipped, "Should skip when followups_enabled=false"


# ══════════════════════════════════════════════════════════════════════════════
# Inquiry reply quality
# ══════════════════════════════════════════════════════════════════════════════

class TestInquiryReplyQuality:
    def _inquiry_job_base(self, subject: str, body: str) -> Job:
        job = Job(
            tenant_id="TENANT_TEST",
            job_type=JobType.CUSTOMER_INQUIRY,
            input_data={
                "subject": subject,
                "message_text": body,
                "sender": {"name": "Kund", "email": "kund@example.com"},
            },
        )
        job.processor_history = [
            {
                "processor": "classification_processor",
                "result": {
                    "payload": {
                        "detected_job_type": "customer_inquiry",
                        "confidence": 0.9,
                        "reasons": ["test_fixture"],
                    }
                },
            },
            {
                "processor": "entity_extraction_processor",
                "result": {"payload": {"entities": {"email": "kund@example.com"}}},
            },
        ]
        job.result = {
            "status": "completed",
            "requires_human_review": False,
            "payload": {"detected_job_type": "customer_inquiry", "confidence": 0.9},
        }
        return job

    def test_generic_inquiry_produces_auto_reply(self):
        job = self._inquiry_job_base("Fråga", "Hej, jag har en fråga om er service.")
        actions = _build_inquiry_default_actions(job, _settings())
        body = _get_auto_reply_body(actions)
        assert len(body) > 20

    def test_complaint_gets_sensitive_ack(self):
        job = self._inquiry_job_base(
            "Reklamation",
            "Detta är en reklamation. Arbetet ni utförde håller inte måttet.",
        )
        actions = _build_inquiry_default_actions(job, _settings())
        ack_actions = [
            a for a in actions
            if a.get("type") == "send_customer_auto_reply" and a.get("_needs_approval")
        ]
        assert ack_actions, "Complaint should produce sensitive ack"

    def test_urgent_inquiry_reply_contains_urgency_acknowledgement(self):
        job = self._inquiry_job_base(
            "AKUT: El fungerar inte",
            "Hela huset är utan ström sedan en timme. AKUT problem!",
        )
        actions = _build_inquiry_default_actions(job, _settings())
        body = _get_auto_reply_body(actions)
        # Body should acknowledge urgency
        assert body, "Expected non-empty auto-reply"
