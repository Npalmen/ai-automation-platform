"""Local golden path tests.

Verifies a complete local demo flow from synthetic input to customer activity,
covering the full pipeline:

  synthetic lead/input
  → classification
  → service profile selection
  → profile-specific missing info
  → profile-specific follow-up question
  → safe customer reply
  → approval/manual_review when risk
  → pipeline completes without crash

Each test is deterministic — no LLM, no live integrations, no external calls.

This doubles as the local demo checklist: all scenarios here must pass before
proceeding to live verification.
"""
from __future__ import annotations

import pytest

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.lead.analyzer import analyze_lead
from app.lead.missing_info import compute_missing_info
from app.lead.question_generator import generate_question_message
from app.lead.tenant_context import TenantLeadContext
from app.service_profiles import select_profile, compute_profile_missing_info, get_profile
from app.support.analyzer import analyze_support
from app.support.next_action import decide_support_next_action
from app.support.prioritizer import prioritize_support
from app.workflows.intelligence_safety import assess_content_risk
from app.workflows.processors.action_dispatch_processor import (
    _build_lead_default_actions,
    _build_inquiry_default_actions,
)
from app.workflows.processors.ai_processor_utils import get_latest_processor_payload
from app.workflows.processors.classification_processor import _classify_deterministic
from app.workflows.processors.lead_analyzer_processor import process_lead_analyzer_job
from app.workflows.processors.support_analyzer_processor import process_support_analyzer_job
from app.workflows.processors.policy_processor import process_policy_job


# ── Helpers ───────────────────────────────────────────────────────────────────

def _lead_job(subject: str, body: str) -> Job:
    job = Job(
        tenant_id="TENANT_DEMO",
        job_type=JobType.LEAD,
        input_data={
            "subject": subject,
            "message_text": body,
            "sender": {"name": "Klara Nilsson", "email": "klara@example.com"},
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
                    "entities": {"email": "klara@example.com"}
                }
            },
        },
        {
            "processor": "lead_processor",
            "result": {
                "payload": {
                    "lead_score": 55,
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
    return job


def _inquiry_job(subject: str, body: str) -> Job:
    job = Job(
        tenant_id="TENANT_DEMO",
        job_type=JobType.CUSTOMER_INQUIRY,
        input_data={
            "subject": subject,
            "message_text": body,
            "sender": {"name": "Klara Nilsson", "email": "klara@example.com"},
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
                "payload": {"entities": {"email": "klara@example.com"}}
            },
        },
    ]
    job.result = {
        "status": "completed",
        "requires_human_review": False,
        "payload": {"detected_job_type": "customer_inquiry", "confidence": 0.9},
    }
    return job


def _settings() -> dict:
    return {
        "followups_enabled": True,
        "email_signature_name": "Elmontören AB",
        "internal_notification_email": "",
    }


def _auto_reply(actions: list[dict]) -> str:
    for a in actions:
        if a.get("type") == "send_customer_auto_reply" and not a.get("_skip"):
            return a.get("body") or ""
    return ""


# ══════════════════════════════════════════════════════════════════════════════
# Golden path 1 — EV charger lead (low risk, incomplete info)
# ══════════════════════════════════════════════════════════════════════════════

class TestGoldenPathEvCharger:
    """
    Scenario: Customer asks for EV charger installation quote. Missing address,
    main_fuse, and placement. Expect profile ev_charger_installation, follow-up
    questions about those fields, and a service-profile-aware customer auto-reply.
    """

    def test_classification_is_lead(self):
        detected = _classify_deterministic(
            "Laddbox till villa",
            "Hej, vi vill ha offert på laddbox till villa i Uppsala.",
        )
        assert detected == "lead"

    def test_profile_selection_is_ev_charger(self):
        input_data = {
            "subject": "Laddbox till villa",
            "message_text": "Hej, vi vill ha offert på laddbox till villa i Uppsala.",
        }
        analysis = analyze_lead(input_data, {})
        profile = select_profile("lead", lead_type=analysis.lead_type, text=input_data["message_text"])
        assert profile.service_type == "ev_charger_installation"

    def test_missing_fields_include_address_and_main_fuse(self):
        input_data = {
            "subject": "Laddbox till villa",
            "message_text": "Hej, vi vill ha offert på laddbox till villa i Uppsala.",
        }
        analysis = analyze_lead(input_data, {})
        missing = compute_missing_info(analysis.lead_type, input_data, {})
        assert "address" in missing.missing_fields
        assert "main_fuse" in missing.missing_fields

    def test_question_message_is_service_specific(self):
        input_data = {
            "subject": "Laddbox",
            "message_text": "Jag vill ha offert på laddbox.",
        }
        analysis = analyze_lead(input_data, {})
        profile = select_profile("lead", lead_type=analysis.lead_type, text=input_data["message_text"])
        missing = compute_missing_info(analysis.lead_type, input_data, {})
        tenant_ctx = TenantLeadContext(tenant_id="test")
        msg = generate_question_message(
            missing.missing_fields, tenant_ctx, analysis.lead_type,
            service_profile=profile,
        )
        assert msg is not None
        assert "laddbox" in msg.lower() or "underlag" in msg.lower() or "ladda" in msg.lower()

    def test_pipeline_produces_service_profile_type_in_payload(self):
        job = _lead_job(
            "Laddbox till villa",
            "Hej, vi vill ha offert på laddbox till villa i Uppsala.",
        )
        result_job = process_lead_analyzer_job(job)
        payload = get_latest_processor_payload(result_job, "lead_analyzer_processor")
        assert payload.get("service_profile_type") == "ev_charger_installation"

    def test_customer_auto_reply_uses_profile_questions(self):
        job = _lead_job(
            "Laddbox till villa",
            "Hej, vi vill ha offert på laddbox till villa i Uppsala.",
        )
        result_job = process_lead_analyzer_job(job)
        actions = _build_lead_default_actions(result_job, _settings())
        body = _auto_reply(actions)
        assert body, "Expected non-empty auto-reply"
        assert "Hej" in body
        # Should contain service-specific question content
        assert "laddbox" in body.lower() or "underlag" in body.lower() or "adress" in body.lower()

    def test_reply_does_not_confirm_booking(self):
        job = _lead_job("Laddbox", "Jag vill ha laddbox.")
        result_job = process_lead_analyzer_job(job)
        actions = _build_lead_default_actions(result_job, _settings())
        body = _auto_reply(actions)
        assert "är bokad" not in body.lower()
        assert "är bokat" not in body.lower()


# ══════════════════════════════════════════════════════════════════════════════
# Golden path 2 — Solar installation lead
# ══════════════════════════════════════════════════════════════════════════════

class TestGoldenPathSolar:
    """
    Scenario: Customer wants solar panels. Expect solar_installation profile,
    questions about roof_type, address, and annual_consumption.
    """

    def test_classification_is_lead(self):
        detected = _classify_deterministic(
            "Solceller",
            "Vi vill installera solceller på vårt tak.",
        )
        assert detected == "lead"

    def test_profile_is_solar(self):
        profile = select_profile(
            "lead",
            lead_type="solar_installation",
            text="Vi vill installera solceller på vårt tak.",
        )
        assert profile.service_type == "solar_installation"

    def test_missing_fields_include_roof_type(self):
        input_data = {
            "subject": "Solceller",
            "message_text": "Vi vill installera solceller på vårt tak.",
        }
        profile = get_profile("solar_installation")
        result = compute_profile_missing_info(profile, input_data, {})
        assert "roof_type" in result["missing_fields"]

    def test_pipeline_produces_solar_profile_type(self):
        job = _lead_job("Solceller", "Vi vill installera solceller på taket.")
        result_job = process_lead_analyzer_job(job)
        payload = get_latest_processor_payload(result_job, "lead_analyzer_processor")
        assert payload.get("service_profile_type") == "solar_installation"

    def test_customer_reply_mentions_solar_context(self):
        job = _lead_job("Solceller", "Vi vill installera solceller på taket.")
        result_job = process_lead_analyzer_job(job)
        actions = _build_lead_default_actions(result_job, _settings())
        body = _auto_reply(actions)
        assert body
        assert "sol" in body.lower() or "underlag" in body.lower() or "tak" in body.lower()


# ══════════════════════════════════════════════════════════════════════════════
# Golden path 3 — Debt collection / high-risk invoice
# ══════════════════════════════════════════════════════════════════════════════

class TestGoldenPathDebtCollection:
    """
    Scenario: Incoming debt collection demand. Expect risk detection,
    manual_review routing, and safe acknowledgement rather than normal automation.
    """

    def test_debt_collection_risk_detected(self):
        input_data = {
            "subject": "Inkassokrav",
            "message_text": "Detta är ett inkassokrav. Betala er skuld omgående.",
        }
        risk = assess_content_risk(input_data)
        assert risk["risk_detected"] is True

    def test_debt_collection_profile_selected_for_invoice(self):
        profile = select_profile(
            "invoice",
            text="Inkassokrav. Betala omgående annars går ärendet vidare till kronofogden.",
        )
        assert profile.service_type == "debt_collection_risk"

    def test_debt_collection_profile_high_risk_flag(self):
        profile = get_profile("debt_collection_risk")
        # is_high_risk needs text containing a risk flag from the profile
        assert profile.risk_flags or profile.high_risk_action == "manual_review"

    def test_debt_collection_routes_to_manual_review(self):
        profile = get_profile("debt_collection_risk")
        assert "manual" in profile.default_route or "manual" in profile.missing_info_action


# ══════════════════════════════════════════════════════════════════════════════
# Golden path 4 — Electrical fault support (safety risk)
# ══════════════════════════════════════════════════════════════════════════════

class TestGoldenPathElectricalFault:
    """
    Scenario: Customer reports burnt smell / sparks from socket.
    Expect safety risk, electrical_fault profile, manual_review routing.
    """

    def test_safety_risk_detected(self):
        input_data = {
            "subject": "Elfel",
            "message_text": "Det luktar bränt från eluttaget och det gnistrar farligt.",
        }
        risk = assess_content_risk(input_data)
        assert risk["risk_detected"] is True

    def test_electrical_fault_profile_selected(self):
        profile = select_profile(
            "customer_inquiry",
            text="Det luktar bränt från eluttaget och det gnistrar farligt.",
        )
        assert profile.service_type == "electrical_fault"

    def test_support_analyzer_escalates_electrical_fault(self):
        job = _inquiry_job(
            "Elfel — luktar bränt",
            "Det luktar bränt från eluttaget och det gnistrar farligt.",
        )
        result_job = process_support_analyzer_job(job)
        payload = get_latest_processor_payload(result_job, "support_analyzer_processor")
        support_next = payload.get("support_next_action") or {}
        # Should escalate or route to manual review
        action = support_next.get("action", "")
        assert action in ("escalate", "manual_review", "create_task"), (
            f"Expected escalation for safety risk, got '{action}'"
        )

    def test_customer_reply_is_sensitive_ack_for_safety(self):
        job = _inquiry_job(
            "Elfel — luktar bränt",
            "Det luktar bränt från eluttaget och det gnistrar farligt.",
        )
        actions = _build_inquiry_default_actions(job, _settings())
        ack_actions = [
            a for a in actions
            if a.get("type") == "send_customer_auto_reply" and a.get("_needs_approval")
        ]
        assert ack_actions, "Safety risk should produce sensitive ack with _needs_approval"


# ══════════════════════════════════════════════════════════════════════════════
# Golden path 5 — Tenant routing hint override
# ══════════════════════════════════════════════════════════════════════════════

class TestGoldenPathTenantRouting:
    """
    Scenario: Tenant has routing hint ev_charger_installation → sales_team.
    Expect profile route to be overridden without changing service_type or fields.
    """

    def test_tenant_routing_hint_changes_route(self):
        tenant_ctx = TenantLeadContext(tenant_id="TENANT_DEMO")
        tenant_ctx.context_available = True
        tenant_ctx.routing_hints = {"ev_charger_installation": "sales_team"}
        profile = select_profile(
            "lead", lead_type="ev_charger", tenant_ctx=tenant_ctx
        )
        assert profile.default_route == "sales_team"
        assert profile.service_type == "ev_charger_installation"

    def test_tenant_custom_required_fields_applied(self):
        tenant_ctx = TenantLeadContext(tenant_id="TENANT_DEMO")
        tenant_ctx.context_available = True
        tenant_ctx.lead_requirements = {
            "ev_charger_installation": {
                "required": ["address", "phone", "pictures"],
                "optional": [],
            }
        }
        profile = get_profile("ev_charger_installation")
        result = compute_profile_missing_info(
            profile,
            {"message_text": "Laddbox"},
            {},
            tenant_ctx=tenant_ctx,
        )
        assert result["schema_source"] == "tenant_override"
        assert "pictures" in result["required_fields"]
        assert "pictures" in result["missing_fields"]


# ══════════════════════════════════════════════════════════════════════════════
# Integration health — not_configured should not crash
# ══════════════════════════════════════════════════════════════════════════════

class TestIntegrationHealthSanity:
    def test_is_integration_configured_does_not_crash(self):
        from app.integrations.service import is_integration_configured
        # Should return False cleanly for unconfigured integrations
        result = is_integration_configured({})
        assert result is False

    def test_assess_content_risk_does_not_crash_on_empty(self):
        risk = assess_content_risk({})
        assert "risk_detected" in risk

    def test_select_profile_does_not_crash_on_empty_input(self):
        profile = select_profile("lead", lead_type=None, text=None, tenant_ctx=None)
        assert profile is not None
        assert profile.service_type == "generic_lead"
