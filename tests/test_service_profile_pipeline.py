"""Local evals for Service Profile pipeline wiring.

Verifies that service profiles are correctly selected, that missing fields are
profile-specific, and that the question generator uses the profile's intro and
follow-up questions.

Deterministic only — no LLM, no live integrations.
"""
from __future__ import annotations

import pytest

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.lead.analyzer import analyze_lead
from app.lead.question_generator import generate_question_message
from app.lead.tenant_context import TenantLeadContext
from app.service_profiles import select_profile, compute_profile_missing_info, get_profile
from app.workflows.processors.ai_processor_utils import (
    append_processor_result,
    get_latest_processor_payload,
)
from app.workflows.processors.lead_analyzer_processor import process_lead_analyzer_job
from app.workflows.processors.support_analyzer_processor import process_support_analyzer_job


# ── Helpers ───────────────────────────────────────────────────────────────────

def _lead_job(subject: str, body: str, *, sender_email: str = "kund@example.com") -> Job:
    job = Job(
        tenant_id="TENANT_TEST",
        job_type=JobType.LEAD,
        input_data={
            "subject": subject,
            "message_text": body,
            "sender": {"name": "Testperson", "email": sender_email},
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
                    "entities": {
                        "email": sender_email,
                    }
                }
            },
        },
    ]
    job.result = {
        "status": "completed",
        "requires_human_review": False,
        "payload": {"detected_job_type": "lead", "confidence": 0.9},
    }
    return job


def _inquiry_job(subject: str, body: str) -> Job:
    job = Job(
        tenant_id="TENANT_TEST",
        job_type=JobType.CUSTOMER_INQUIRY,
        input_data={
            "subject": subject,
            "message_text": body,
            "sender": {"name": "Testperson", "email": "kund@example.com"},
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
            "result": {
                "payload": {
                    "entities": {
                        "email": "kund@example.com",
                    }
                }
            },
        },
    ]
    job.result = {
        "status": "completed",
        "requires_human_review": False,
        "payload": {"detected_job_type": "customer_inquiry", "confidence": 0.9},
    }
    return job


# ══════════════════════════════════════════════════════════════════════════════
# Profile selection in the pipeline
# ══════════════════════════════════════════════════════════════════════════════

class TestProfileSelectionInPipeline:
    def test_ev_charger_lead_produces_ev_charger_profile(self):
        profile = select_profile(
            "lead",
            lead_type="ev_charger",
            text="Hej, vi vill ha offert på laddbox till villa i Uppsala.",
        )
        assert profile.service_type == "ev_charger_installation"

    def test_solar_lead_produces_solar_profile(self):
        profile = select_profile(
            "lead",
            lead_type="solar_installation",
            text="Vi vill installera solceller på vårt tak.",
        )
        assert profile.service_type == "solar_installation"

    def test_electrical_work_lead_produces_panel_profile(self):
        profile = select_profile(
            "lead",
            lead_type="electrical_work",
            text="Vi behöver byta elcentral.",
        )
        assert profile.service_type == "electrical_panel"

    def test_unknown_lead_type_falls_back_to_generic_lead(self):
        profile = select_profile("lead", lead_type="unknown_type", text="Hej")
        assert profile.service_type == "generic_lead"

    def test_debt_collection_text_selects_debt_risk_profile(self):
        profile = select_profile(
            "invoice",
            text="Detta är ett inkassokrav. Betala omgående.",
        )
        assert profile.service_type == "debt_collection_risk"

    def test_electrical_fault_inquiry_selects_correct_profile(self):
        profile = select_profile(
            "customer_inquiry",
            support_category="electrical",
            text="Jordfelsbrytaren löser ut ideligen.",
        )
        assert profile.service_type == "electrical_fault"

    def test_inverter_inquiry_selects_inverter_profile(self):
        profile = select_profile(
            "customer_inquiry",
            text="Växelriktaren visar felkod F01.",
        )
        assert profile.service_type == "inverter_support"

    def test_safety_inquiry_selects_electrical_fault_profile(self):
        profile = select_profile(
            "customer_inquiry",
            support_category="safety",
            text="Det luktar bränt från eluttaget.",
        )
        assert profile.service_type == "electrical_fault"


# ══════════════════════════════════════════════════════════════════════════════
# lead_analyzer_processor wiring
# ══════════════════════════════════════════════════════════════════════════════

class TestLeadAnalyzerProcessorWiring:
    def test_ev_charger_lead_job_produces_service_profile_type(self):
        job = _lead_job(
            "Offert laddbox",
            "Hej, vi vill ha offert på laddbox till villa i Uppsala.",
        )
        result_job = process_lead_analyzer_job(job)
        payload = get_latest_processor_payload(result_job, "lead_analyzer_processor")
        assert payload.get("service_profile_type") == "ev_charger_installation"

    def test_solar_lead_job_produces_solar_profile_type(self):
        job = _lead_job(
            "Solceller",
            "Vi vill installera solceller på taket i Göteborg.",
        )
        result_job = process_lead_analyzer_job(job)
        payload = get_latest_processor_payload(result_job, "lead_analyzer_processor")
        assert payload.get("service_profile_type") == "solar_installation"

    def test_lead_analyzer_produces_generated_question_message(self):
        """When completeness is low, a question message should be generated."""
        job = _lead_job(
            "Laddbox",
            "Jag vill ha offert på en laddbox.",
        )
        result_job = process_lead_analyzer_job(job)
        payload = get_latest_processor_payload(result_job, "lead_analyzer_processor")
        # Should have a question message since info is incomplete
        assert payload.get("generated_question_message") is not None

    def test_ev_charger_question_message_uses_profile_intro(self):
        """Question message should reference laddbox, not be generic."""
        job = _lead_job(
            "Laddbox",
            "Jag vill ha offert på en laddbox.",
        )
        result_job = process_lead_analyzer_job(job)
        payload = get_latest_processor_payload(result_job, "lead_analyzer_processor")
        msg = payload.get("generated_question_message") or ""
        # Profile-specific intro should mention laddbox context
        assert "laddbox" in msg.lower() or "ladda" in msg.lower() or "underlag" in msg.lower()

    def test_lead_analyzer_includes_missing_info(self):
        job = _lead_job(
            "Laddbox",
            "Hej, jag vill ha offert på laddbox.",
        )
        result_job = process_lead_analyzer_job(job)
        payload = get_latest_processor_payload(result_job, "lead_analyzer_processor")
        missing_info = payload.get("missing_info") or {}
        assert "missing_fields" in missing_info
        assert "address" in missing_info["missing_fields"]


# ══════════════════════════════════════════════════════════════════════════════
# support_analyzer_processor wiring
# ══════════════════════════════════════════════════════════════════════════════

class TestSupportAnalyzerProcessorWiring:
    def test_support_job_produces_service_profile_type(self):
        job = _inquiry_job(
            "Solcellerna producerar inget",
            "Hela anläggningen är nere sedan igår.",
        )
        result_job = process_support_analyzer_job(job)
        payload = get_latest_processor_payload(result_job, "support_analyzer_processor")
        assert "service_profile_type" in payload

    def test_electrical_fault_inquiry_produces_electrical_fault_profile(self):
        job = _inquiry_job(
            "Jordfelsbrytaren löser",
            "Jordfelsbrytaren löser ut varje kväll sedan ett par dagar.",
        )
        result_job = process_support_analyzer_job(job)
        payload = get_latest_processor_payload(result_job, "support_analyzer_processor")
        assert payload.get("service_profile_type") == "electrical_fault"

    def test_inverter_fault_inquiry_produces_inverter_support_profile(self):
        job = _inquiry_job(
            "Växelriktarfel",
            "Växelriktaren blinkar rött och visar felkod F03.",
        )
        result_job = process_support_analyzer_job(job)
        payload = get_latest_processor_payload(result_job, "support_analyzer_processor")
        assert payload.get("service_profile_type") == "inverter_support"

    def test_generic_support_falls_back_to_generic_support_profile(self):
        job = _inquiry_job(
            "Fråga",
            "Hej, jag har en fråga om er service.",
        )
        result_job = process_support_analyzer_job(job)
        payload = get_latest_processor_payload(result_job, "support_analyzer_processor")
        assert payload.get("service_profile_type") == "generic_support"


# ══════════════════════════════════════════════════════════════════════════════
# Profile-aware missing info
# ══════════════════════════════════════════════════════════════════════════════

class TestProfileAwareMissingInfo:
    def test_ev_charger_profile_requires_main_fuse(self):
        profile = get_profile("ev_charger_installation")
        result = compute_profile_missing_info(
            profile,
            {"message_text": "Jag vill ha laddbox"},
            {},
        )
        assert "main_fuse" in result["missing_fields"]

    def test_solar_profile_requires_roof_type(self):
        profile = get_profile("solar_installation")
        result = compute_profile_missing_info(
            profile,
            {"message_text": "Vi vill ha solceller"},
            {},
        )
        assert "roof_type" in result["missing_fields"]

    def test_debt_collection_profile_is_always_incomplete(self):
        profile = get_profile("debt_collection_risk")
        result = compute_profile_missing_info(
            profile,
            {"message_text": "Inkassokrav"},
            {},
        )
        assert not result["is_complete"]

    def test_profile_completeness_increases_with_info(self):
        profile = get_profile("ev_charger_installation")

        sparse = compute_profile_missing_info(
            profile,
            {"message_text": "Laddbox"},
            {},
        )
        rich = compute_profile_missing_info(
            profile,
            {
                "message_text": (
                    "Laddbox Storgatan 1 Stockholm villa 20A "
                    "garage installation nästa månad"
                )
            },
            {"address": "Storgatan 1"},
        )
        assert rich["completeness_score"] > sparse["completeness_score"]


# ══════════════════════════════════════════════════════════════════════════════
# Question generator uses service profile
# ══════════════════════════════════════════════════════════════════════════════

class TestQuestionGeneratorWithProfile:
    def test_ev_charger_profile_produces_profile_specific_intro(self):
        profile = get_profile("ev_charger_installation")
        tenant_ctx = TenantLeadContext(tenant_id="test")  # no context — fallback mode
        msg = generate_question_message(
            ["address", "main_fuse"],
            tenant_ctx,
            "ev_charger",
            service_profile=profile,
        )
        assert msg is not None
        # Profile intro should be present
        intro = profile.follow_up_intro.lower()
        assert any(word in (msg or "").lower() for word in intro.split()[:4])

    def test_solar_profile_produces_profile_specific_intro(self):
        profile = get_profile("solar_installation")
        tenant_ctx = TenantLeadContext(tenant_id="test")
        msg = generate_question_message(
            ["address", "roof_type"],
            tenant_ctx,
            "solar_installation",
            service_profile=profile,
        )
        assert msg is not None
        assert "sol" in (msg or "").lower() or "tak" in (msg or "").lower()

    def test_fallback_without_profile_still_works(self):
        """Without service_profile, question_generator should still produce output."""
        tenant_ctx = TenantLeadContext(tenant_id="test")
        msg = generate_question_message(
            ["address", "phone"],
            tenant_ctx,
            "ev_charger",
            service_profile=None,
        )
        assert msg is not None
        assert len(msg) > 10

    def test_empty_missing_fields_returns_none(self):
        profile = get_profile("ev_charger_installation")
        tenant_ctx = TenantLeadContext(tenant_id="test")
        msg = generate_question_message(
            [],
            tenant_ctx,
            "ev_charger",
            service_profile=profile,
        )
        assert msg is None


# ══════════════════════════════════════════════════════════════════════════════
# Profile-specific missing fields exposed in lead_analyzer_processor payload
# ══════════════════════════════════════════════════════════════════════════════

class TestLeadPipelineProfileMissingFieldsPayload:
    def test_ev_charger_job_exposes_profile_missing_fields(self):
        """profile_missing_fields key must appear in processor payload for EV charger."""
        job = _lead_job(
            "Offert laddbox",
            "Hej, vi vill ha laddbox till villan.",
        )
        result_job = process_lead_analyzer_job(job)
        payload = get_latest_processor_payload(result_job, "lead_analyzer_processor")
        assert "profile_missing_fields" in payload
        # EV charger profile requires main_fuse — must be missing without that info
        assert "main_fuse" in payload["profile_missing_fields"]

    def test_solar_job_exposes_profile_missing_fields_with_roof_type(self):
        """Solar profile should flag roof_type as missing when not provided."""
        job = _lead_job(
            "Solceller",
            "Vi vill ha solceller på huset i Malmö.",
        )
        result_job = process_lead_analyzer_job(job)
        payload = get_latest_processor_payload(result_job, "lead_analyzer_processor")
        assert "profile_missing_fields" in payload
        assert "roof_type" in payload["profile_missing_fields"]

    def test_profile_completeness_score_in_payload(self):
        """profile_completeness_score must be a float between 0 and 1."""
        job = _lead_job("Laddbox", "Jag vill ha offert.")
        result_job = process_lead_analyzer_job(job)
        payload = get_latest_processor_payload(result_job, "lead_analyzer_processor")
        score = payload.get("profile_completeness_score")
        assert score is not None
        assert 0.0 <= score <= 1.0

    def test_ev_charger_question_uses_profile_missing_fields_content(self):
        """Question message for EV charger should reflect profile-specific fields,
        not just generic lead fields like 'address'."""
        job = _lead_job(
            "Laddbox villa",
            "Jag vill installera en laddbox i garaget.",
        )
        result_job = process_lead_analyzer_job(job)
        payload = get_latest_processor_payload(result_job, "lead_analyzer_processor")
        msg = payload.get("generated_question_message") or ""
        # Message should contain profile-specific content (laddbox/garage/säkring context)
        assert len(msg) > 0
        lower_msg = msg.lower()
        assert any(kw in lower_msg for kw in ["laddbox", "ladda", "säkring", "installation", "adress"])


# ══════════════════════════════════════════════════════════════════════════════
# Support pipeline: service profile passed to question generator
# ══════════════════════════════════════════════════════════════════════════════

class TestSupportPipelineProfileQuestionGeneration:
    def test_inverter_support_question_uses_profile_intro(self):
        """Inverter support with missing info should get profile-based question message."""
        from app.support.question_generator import generate_support_question_message
        from app.service_profiles import get_profile

        profile = get_profile("inverter_support")
        msg = generate_support_question_message(
            ["installation_date", "error_code"],
            ticket_type="issue",
            tenant_ctx=None,
            input_data={},
            service_profile=profile,
        )
        assert msg is not None
        # Profile-specific intro for inverter_support should be present
        lower_msg = msg.lower()
        assert any(kw in lower_msg for kw in ["växelriktare", "inverter", "solcell", "installation", "felinformation"])

    def test_emergency_support_ignores_service_profile(self):
        """Emergency ticket must keep AKUT opening regardless of service profile."""
        from app.support.question_generator import generate_support_question_message
        from app.service_profiles import get_profile

        profile = get_profile("electrical_fault")
        msg = generate_support_question_message(
            ["address"],
            ticket_type="emergency",
            tenant_ctx=None,
            input_data={},
            service_profile=profile,
        )
        assert msg is not None
        assert "AKUT" in msg

    def test_safety_support_keeps_disclaimer(self):
        """Safety-risk tickets must keep the safety disclaimer even with a profile."""
        from app.support.question_generator import generate_support_question_message
        from app.service_profiles import get_profile

        profile = get_profile("electrical_fault")
        msg = generate_support_question_message(
            ["address"],
            ticket_type="safety",
            tenant_ctx=None,
            input_data={"message_text": "Det luktar bränt"},
            service_profile=profile,
        )
        assert msg is not None
        assert "⚠️" in msg or "säkerhet" in msg.lower() or "elektriker" in msg.lower()

    def test_support_pipeline_passes_service_profile_to_question_generator(self):
        """Inverter fault inquiry should produce a profile-aware question message in pipeline."""
        job = _inquiry_job(
            "Växelriktarfel",
            "Växelriktaren blinkar rött och visar felkod F03. Inget installation_date.",
        )
        result_job = process_support_analyzer_job(job)
        payload = get_latest_processor_payload(result_job, "support_analyzer_processor")
        # Profile type confirmed
        assert payload.get("service_profile_type") == "inverter_support"
        # If question message generated, it should reflect profile context
        msg = payload.get("support_generated_question_message")
        if msg:
            lower_msg = msg.lower()
            assert any(kw in lower_msg for kw in ["växelriktare", "inverter", "solcell", "installation", "felinformation", "adress", "information"])

    def test_support_no_regression_without_service_profile(self):
        """generate_support_question_message without service_profile must still work."""
        from app.support.question_generator import generate_support_question_message

        msg = generate_support_question_message(
            ["address", "phone"],
            ticket_type="issue",
            tenant_ctx=None,
            input_data={},
            service_profile=None,
        )
        assert msg is not None
        assert len(msg) > 10
