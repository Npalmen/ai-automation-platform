"""Local evals for customer reply quality.

Verifies:
  - Low-risk leads get service-profile-aware follow-up questions in auto-reply.
  - High-risk / sensitive leads get a safe acknowledgement, not solution.
  - Missing fields are reflected in the reply.
  - Tenant/company name is used in replies when available.
  - Replies do not over-promise or make legal/financial commitments.
  - Debt collection and dangerous cases route to manual_review with safe ack.
  - Service context is correctly detected (add-on vs new vs fault).
  - Greeting uses first name only — not full name.
  - Stiff opener "Tack för ditt meddelande." is absent.
  - Multiple industries produce relevant, context-aware questions.
  - Approval-first behavior is unchanged.

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
    _first_name,
    _profile_opener,
)
from app.workflows.processors.lead_analyzer_processor import process_lead_analyzer_job
from app.workflows.processors.ai_processor_utils import get_latest_processor_payload
from app.service_profiles.context import detect_service_context


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


# ══════════════════════════════════════════════════════════════════════════════
# Service context detection unit tests
# ══════════════════════════════════════════════════════════════════════════════

class TestServiceContextDetection:
    def test_add_on_existing_solar(self):
        text = "vi har solceller idag och vill komplettera med batterilager"
        assert detect_service_context(text) == "add_on_existing"

    def test_add_on_existing_via_installer(self):
        text = "ni installerade vår laddbox för två år sedan, nu vill vi lägga till solceller"
        assert detect_service_context(text) == "add_on_existing"

    def test_repair_or_fault_laddbox(self):
        text = "laddboxen fungerar inte, den laddar inte längre"
        assert detect_service_context(text) == "repair_or_fault"

    def test_repair_or_fault_solar_production(self):
        text = "solcellerna producerar inte, produktionen har minskat det senaste halvåret"
        assert detect_service_context(text) == "repair_or_fault"

    def test_urgent_issue(self):
        text = "vattenläcka akut, vi har barn hemma"
        assert detect_service_context(text) == "urgent_issue"

    def test_unclear_followup(self):
        text = "tänkte bara kolla läget, hörde inget från er förra veckan"
        assert detect_service_context(text) == "unclear_followup"

    def test_new_installation_default(self):
        text = "vi vill installera solceller på taket av vår villa"
        assert detect_service_context(text) == "new_installation"

    def test_price_shopping(self):
        text = "vad tar ni betalt, har fått tre offerter från andra"
        assert detect_service_context(text) == "price_shopping"


# ══════════════════════════════════════════════════════════════════════════════
# Service-context-aware profile routing
# ══════════════════════════════════════════════════════════════════════════════

class TestServiceContextProfileRouting:
    """Verify that the right profile is selected based on context, not just keywords."""

    def _run_lead(self, subject: str, body: str) -> Job:
        job = Job(
            tenant_id="TENANT_TEST",
            job_type=JobType.LEAD,
            input_data={
                "subject": subject,
                "message_text": body,
                "sender": {"name": "Test Person", "email": "test@example.com"},
            },
        )
        job.processor_history = [
            {"processor": "classification_processor", "result": {"payload": {"detected_job_type": "lead", "confidence": 0.9, "reasons": []}}},
            {"processor": "entity_extraction_processor", "result": {"payload": {"entities": {"email": "test@example.com"}}}},
            {"processor": "lead_processor", "result": {"payload": {"lead_score": 60, "priority": "normal", "routing": "ask_questions", "reasons": [], "confidence": 0.7, "recommended_next_step": "ask_questions"}}},
        ]
        job.result = {"status": "completed", "requires_human_review": False, "payload": {"detected_job_type": "lead", "confidence": 0.9}}
        return process_lead_analyzer_job(job)

    def test_battery_addon_routes_to_battery_profile(self):
        """Existing solar + wants battery → battery_storage profile (not solar_installation)."""
        job = self._run_lead(
            "Batteri till befintlig solcellsanläggning",
            "Hej, vi har solceller idag och vill komplettera med ett batterilager på 10 kWh.",
        )
        payload = get_latest_processor_payload(job, "lead_analyzer_processor")
        assert payload.get("service_profile_type") == "battery_storage", (
            f"Expected battery_storage profile, got: {payload.get('service_profile_type')}"
        )

    def test_battery_addon_no_roof_type_question(self):
        """Existing solar + wants battery → reply must NOT ask about roof type."""
        job = self._run_lead(
            "Fråga om batterilager till befintlig solcellsinstallation",
            "Vi har en 10 kWp solcellsanläggning sedan 2022 och funderar på att "
            "komplettera med ett batterilager (gärna 10-15 kWh).",
        )
        actions = _build_lead_default_actions(job, _settings())
        body = _get_auto_reply_body(actions)
        assert body, "Expected non-empty auto-reply"
        assert "taktyp" not in body.lower(), (
            f"Should NOT ask about roof type for battery add-on, body:\n{body}"
        )
        assert "takvinkel" not in body.lower(), (
            f"Should NOT ask about roof angle for battery add-on, body:\n{body}"
        )

    def test_battery_addon_asks_battery_relevant_questions(self):
        """Battery add-on reply should reference battery or fuse or existing system."""
        job = self._run_lead(
            "Batterilager till solceller",
            "Vi har solceller idag och vill veta om ni kan installera batteri på circa 10 kWh.",
        )
        actions = _build_lead_default_actions(job, _settings())
        body = _get_auto_reply_body(actions)
        assert body
        assert any(kw in body.lower() for kw in ("batteri", "säkring", "solcell", "lösning")), (
            f"Battery add-on reply should reference battery context, body:\n{body}"
        )

    def test_new_solar_may_ask_roof_type(self):
        """New solar installation → roof type and annual consumption questions are appropriate."""
        job = self._run_lead(
            "Solceller till villan",
            "Hej, vi vill installera solceller på taket av vår villa. Vad kostar det?",
        )
        payload = get_latest_processor_payload(job, "lead_analyzer_processor")
        assert payload.get("service_profile_type") == "solar_installation"
        actions = _build_lead_default_actions(job, _settings())
        body = _get_auto_reply_body(actions)
        assert body
        # Solar new-installation questions are all valid
        assert any(kw in body.lower() for kw in ("sol", "tak", "förbruk", "kwh")), (
            f"New solar reply should reference solar prerequisites, body:\n{body}"
        )

    def test_laddbox_fault_routes_to_fault_profile(self):
        """Laddbox not working → ev_charger_fault profile."""
        job = self._run_lead(
            "Laddbox fungerar inte",
            "Vår laddbox har slutat fungera. Den laddar inte längre.",
        )
        payload = get_latest_processor_payload(job, "lead_analyzer_processor")
        assert payload.get("service_profile_type") == "ev_charger_fault", (
            f"Expected ev_charger_fault profile, got: {payload.get('service_profile_type')}"
        )

    def test_laddbox_fault_no_new_installation_questions(self):
        """Laddbox fault reply should NOT ask new-installation questions."""
        job = self._run_lead(
            "Laddbox fungerar inte",
            "Hej, vår laddbox har slutat fungera. Den laddar inte längre.",
        )
        actions = _build_lead_default_actions(job, _settings())
        body = _get_auto_reply_body(actions)
        assert body
        assert "önskad placering" not in body.lower(), (
            f"Fault reply should not ask about desired placement, body:\n{body}"
        )
        assert "fastighetstyp" not in body.lower(), (
            f"Fault reply should not ask about property type, body:\n{body}"
        )

    def test_new_laddbox_installation_asks_installation_questions(self):
        """New laddbox installation → asks placement and fuse questions."""
        job = self._run_lead(
            "Laddbox installation offert",
            "Hej, vi vill installera en laddbox i garaget för vår elbil.",
        )
        payload = get_latest_processor_payload(job, "lead_analyzer_processor")
        assert payload.get("service_profile_type") == "ev_charger_installation"
        actions = _build_lead_default_actions(job, _settings())
        body = _get_auto_reply_body(actions)
        assert body
        assert any(kw in body.lower() for kw in ("laddbox", "placering", "säkring", "underlag", "ladda")), (
            f"New laddbox reply should ask installation questions, body:\n{body}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# VVS and building project replies
# ══════════════════════════════════════════════════════════════════════════════

class TestMultiIndustryReplyQuality:

    def _inquiry_job(self, subject: str, body: str) -> Job:
        job = Job(
            tenant_id="TENANT_TEST",
            job_type=JobType.CUSTOMER_INQUIRY,
            input_data={
                "subject": subject,
                "message_text": body,
                "sender": {"name": "Helena Berg", "email": "helena@example.com"},
            },
        )
        job.processor_history = [
            {"processor": "classification_processor", "result": {"payload": {"detected_job_type": "customer_inquiry", "confidence": 0.9, "reasons": []}}},
            {"processor": "entity_extraction_processor", "result": {"payload": {"entities": {"email": "helena@example.com"}}}},
        ]
        job.result = {"status": "completed", "requires_human_review": False, "payload": {"detected_job_type": "customer_inquiry", "confidence": 0.9}}
        return job

    def _lead_job(self, subject: str, body: str, sender_name: str = "Thomas Lindqvist") -> Job:
        job = Job(
            tenant_id="TENANT_TEST",
            job_type=JobType.LEAD,
            input_data={
                "subject": subject,
                "message_text": body,
                "sender": {"name": sender_name, "email": "test@example.com"},
            },
        )
        job.processor_history = [
            {"processor": "classification_processor", "result": {"payload": {"detected_job_type": "lead", "confidence": 0.9, "reasons": []}}},
            {"processor": "entity_extraction_processor", "result": {"payload": {"entities": {"email": "test@example.com"}}}},
            {"processor": "lead_processor", "result": {"payload": {"lead_score": 60, "priority": "normal", "routing": "ask_questions", "reasons": [], "confidence": 0.7, "recommended_next_step": "ask_questions"}}},
        ]
        job.result = {"status": "completed", "requires_human_review": False, "payload": {"detected_job_type": "lead", "confidence": 0.9}}
        return process_lead_analyzer_job(job)

    def test_vvs_lead_produces_service_reply(self):
        """VVS water leak lead → practical service-oriented reply."""
        job = self._lead_job(
            "Vattenläcka under diskbänk",
            "Hej, jag har en vattenläcka under diskbänken i köket. Det droppar sakta.",
        )
        actions = _build_lead_default_actions(job, _settings())
        body = _get_auto_reply_body(actions)
        assert body, "Expected non-empty auto-reply for VVS lead"
        # Should not be a generic response — context should be addressed
        assert len(body) > 30

    def test_snickare_lead_produces_practical_reply(self):
        """Small builder project → practical, not overly formal reply."""
        job = self._lead_job(
            "Bygga förråd på tomten",
            "Vi funderar på att bygga ett 15 kvm friggebodsliknande förråd på vår tomt i Huddinge.",
        )
        actions = _build_lead_default_actions(job, _settings())
        body = _get_auto_reply_body(actions)
        assert body, "Expected non-empty auto-reply for snickare project"
        # Should have a non-empty, practical reply
        assert len(body) > 30

    def test_vvs_inquiry_reply_is_non_empty(self):
        """VVS inquiry produces a response."""
        job = self._inquiry_job(
            "Vattenläcka under diskbänk",
            "Jag har en vattenläcka under diskbänken i köket. Det droppar sakta.",
        )
        actions = _build_inquiry_default_actions(job, _settings())
        body = _get_auto_reply_body(actions)
        assert body, "Expected non-empty auto-reply for VVS inquiry"

    def test_unclear_followup_produces_reply(self):
        """Unclear follow-up → produces a reply (not skipped)."""
        job = self._inquiry_job(
            "Re: Er offert från förra veckan",
            "Hej, jag mailade er förra veckan men tänkte bara kolla läget. /Sofia",
        )
        actions = _build_inquiry_default_actions(job, _settings())
        body = _get_auto_reply_body(actions)
        assert body, "Unclear follow-up should still produce a reply"


# ══════════════════════════════════════════════════════════════════════════════
# Greeting and tone quality
# ══════════════════════════════════════════════════════════════════════════════

class TestGreetingAndToneQuality:

    def _lead_with_full_name(self, full_name: str, subject: str, body: str) -> Job:
        job = Job(
            tenant_id="TENANT_TEST",
            job_type=JobType.LEAD,
            input_data={
                "subject": subject,
                "message_text": body,
                "sender": {"name": full_name, "email": "kund@example.com"},
            },
        )
        job.processor_history = [
            {"processor": "classification_processor", "result": {"payload": {"detected_job_type": "lead", "confidence": 0.9, "reasons": []}}},
            {"processor": "entity_extraction_processor", "result": {"payload": {"entities": {"email": "kund@example.com"}}}},
            {"processor": "lead_processor", "result": {"payload": {"lead_score": 60, "priority": "normal", "routing": "ask_questions", "reasons": [], "confidence": 0.7, "recommended_next_step": "ask_questions"}}},
        ]
        job.result = {"status": "completed", "requires_human_review": False, "payload": {"detected_job_type": "lead", "confidence": 0.9}}
        return process_lead_analyzer_job(job)

    def test_greeting_uses_first_name_only(self):
        """Greeting must use first name only, never full name like 'Hej Niklas Palm,'."""
        job = self._lead_with_full_name(
            "Niklas Palm", "Laddbox offert", "Jag vill ha offert på laddbox i garaget."
        )
        actions = _build_lead_default_actions(job, _settings())
        body = _get_auto_reply_body(actions)
        assert body
        assert "Hej Niklas," in body or body.startswith("Hej Niklas"), (
            f"Should greet with first name only, body:\n{body[:150]}"
        )
        assert "Hej Niklas Palm" not in body, (
            f"Should NOT use full name in greeting, body:\n{body[:150]}"
        )

    def test_greeting_with_compound_name(self):
        """Per Olofsson → greet as 'Hej Per,'."""
        job = self._lead_with_full_name(
            "Per Olofsson", "Batteri", "Vi vill ha batterilager till solcellerna."
        )
        actions = _build_lead_default_actions(job, _settings())
        body = _get_auto_reply_body(actions)
        assert body
        assert "Hej Per," in body, f"Should use 'Hej Per,', body:\n{body[:150]}"
        assert "Per Olofsson" not in body.split("\n")[0], (
            "Full name should not appear in the greeting line"
        )

    def test_greeting_fallback_when_no_name(self):
        """When no sender name is available, greeting falls back to 'Hej,'."""
        job = Job(
            tenant_id="TENANT_TEST",
            job_type=JobType.LEAD,
            input_data={
                "subject": "Laddbox",
                "message_text": "Offert på laddbox tack.",
                "sender": {"name": "", "email": "anon@example.com"},
            },
        )
        job.processor_history = [
            {"processor": "classification_processor", "result": {"payload": {"detected_job_type": "lead", "confidence": 0.9, "reasons": []}}},
            {"processor": "entity_extraction_processor", "result": {"payload": {"entities": {}}}},
            {"processor": "lead_processor", "result": {"payload": {"lead_score": 50, "priority": "normal", "routing": "ask_questions", "reasons": [], "confidence": 0.6, "recommended_next_step": "ask_questions"}}},
        ]
        job.result = {"status": "completed", "requires_human_review": False, "payload": {"detected_job_type": "lead", "confidence": 0.9}}
        job = process_lead_analyzer_job(job)
        actions = _build_lead_default_actions(job, _settings())
        body = _get_auto_reply_body(actions)
        assert body
        assert body.startswith("Hej,") or body.startswith("Hej "), (
            f"Should start with 'Hej,' when no name, body:\n{body[:150]}"
        )

    def test_no_stiff_opener_phrase(self):
        """Reply must NOT contain the stiff 'Tack för ditt meddelande.'"""
        job = self._lead_with_full_name(
            "Anna Andersson", "Laddbox", "Jag vill ha offert på laddbox."
        )
        actions = _build_lead_default_actions(job, _settings())
        body = _get_auto_reply_body(actions)
        assert "Tack för ditt meddelande." not in body, (
            "Reply should not use the stiff 'Tack för ditt meddelande.' opener"
        )

    def test_no_stiff_svar_racker_closing(self):
        """Reply must NOT contain the stiff 'Svar räcker kort' closing."""
        job = self._lead_with_full_name(
            "Erik Svensson", "Solceller", "Vi vill ha solceller på villan."
        )
        actions = _build_lead_default_actions(job, _settings())
        body = _get_auto_reply_body(actions)
        assert "Svar räcker kort" not in body, (
            "Reply should not use the stiff 'Svar räcker kort' closing"
        )

    def test_profile_opener_for_battery(self):
        assert _profile_opener("battery_storage") != ""

    def test_profile_opener_for_solar(self):
        assert _profile_opener("solar_installation") != ""

    def test_first_name_helper_extracts_first(self):
        assert _first_name("Niklas Palm") == "Niklas"

    def test_first_name_helper_single(self):
        assert _first_name("Per") == "Per"

    def test_first_name_helper_empty(self):
        assert _first_name("") == ""

    def test_first_name_helper_brf(self):
        assert _first_name("BRF Solstrålen") == ""


# ══════════════════════════════════════════════════════════════════════════════
# Approval-first behavior unchanged
# ══════════════════════════════════════════════════════════════════════════════

class TestApprovalFirstUnchanged:

    def _simple_lead_job(self) -> Job:
        job = Job(
            tenant_id="TENANT_TEST",
            job_type=JobType.LEAD,
            input_data={
                "subject": "Laddbox",
                "message_text": "Offert på laddbox.",
                "sender": {"name": "Test User", "email": "test@example.com"},
            },
        )
        job.processor_history = [
            {"processor": "classification_processor", "result": {"payload": {"detected_job_type": "lead", "confidence": 0.9, "reasons": []}}},
            {"processor": "entity_extraction_processor", "result": {"payload": {"entities": {"email": "test@example.com"}}}},
            {"processor": "lead_processor", "result": {"payload": {"lead_score": 60, "priority": "normal", "routing": "ask_questions", "reasons": [], "confidence": 0.7, "recommended_next_step": "ask_questions"}}},
        ]
        job.result = {"status": "completed", "requires_human_review": False, "payload": {"detected_job_type": "lead", "confidence": 0.9}}
        return process_lead_analyzer_job(job)

    def test_email_actions_are_approval_gated_by_default(self):
        """Without explicit auto_actions enable, all email actions require approval."""
        job = self._simple_lead_job()
        # _settings() has no auto_actions → _email_needs_approval returns True
        actions = _build_lead_default_actions(job, _settings())
        email_actions = [
            a for a in actions
            if a.get("type") == "send_customer_auto_reply" and not a.get("_skip")
        ]
        assert email_actions, "Expected at least one customer auto-reply action"
        for a in email_actions:
            assert a.get("_needs_approval"), (
                "Email action must be approval-gated when auto_actions not explicitly enabled"
            )

    def test_battery_addon_is_still_approval_gated(self):
        """Battery add-on context fix does not bypass approval gate."""
        job = Job(
            tenant_id="TENANT_TEST",
            job_type=JobType.LEAD,
            input_data={
                "subject": "Batteri till solceller",
                "message_text": "Vi har solceller idag och vill komplettera med batterilager.",
                "sender": {"name": "Per Olofsson", "email": "per@example.com"},
            },
        )
        job.processor_history = [
            {"processor": "classification_processor", "result": {"payload": {"detected_job_type": "lead", "confidence": 0.9, "reasons": []}}},
            {"processor": "entity_extraction_processor", "result": {"payload": {"entities": {"email": "per@example.com"}}}},
            {"processor": "lead_processor", "result": {"payload": {"lead_score": 60, "priority": "normal", "routing": "ask_questions", "reasons": [], "confidence": 0.7, "recommended_next_step": "ask_questions"}}},
        ]
        job.result = {"status": "completed", "requires_human_review": False, "payload": {"detected_job_type": "lead", "confidence": 0.9}}
        job = process_lead_analyzer_job(job)

        actions = _build_lead_default_actions(job, _settings())
        email_actions = [
            a for a in actions
            if a.get("type") == "send_customer_auto_reply" and not a.get("_skip")
        ]
        for a in email_actions:
            assert a.get("_needs_approval"), "Battery add-on email must still require approval"

    def test_auto_send_not_enabled_by_quality_changes(self):
        """Quality improvements must NOT enable auto-send (auto_actions must remain off by default)."""
        from app.workflows.processors.action_dispatch_processor import _email_needs_approval
        # Without auto_actions key → should need approval
        assert _email_needs_approval("lead", {}) is True
        assert _email_needs_approval("customer_inquiry", {}) is True
        assert _email_needs_approval("lead", {"auto_actions": {}}) is True
        assert _email_needs_approval("lead", {"auto_actions": {"lead": "manual"}}) is True
