"""Local evals for core intelligence quality.

The scenarios are synthetic Swedish installation/service company messages.
They intentionally exercise deterministic code paths only: no LLM, no live
integrations, no OAuth tokens, and no production endpoints.
"""
from __future__ import annotations

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.lead.analyzer import analyze_lead
from app.lead.missing_info import compute_missing_info
from app.lead.next_action import decide_next_action
from app.lead.scorer import score_lead
from app.support.analyzer import analyze_support
from app.support.missing_info import compute_support_missing_info
from app.support.next_action import decide_support_next_action
from app.support.prioritizer import prioritize_support
from app.support.response_draft import build_support_response_draft
from app.workflows.processors.action_dispatch_processor import _build_inquiry_default_actions
from app.workflows.processors.classification_processor import _classify_deterministic
from app.workflows.processors.human_handoff_processor import process_human_handoff_job
from app.workflows.processors.policy_processor import process_policy_job


def _job(
    subject: str,
    message_text: str,
    *,
    detected_job_type: str = "customer_inquiry",
    processor_payloads: list[tuple[str, dict]] | None = None,
) -> Job:
    job = Job(
        tenant_id="TENANT_1001",
        job_type=JobType.CUSTOMER_INQUIRY,
        input_data={
            "subject": subject,
            "message_text": message_text,
            "sender": {"name": "Kund", "email": "kund@example.com"},
        },
    )
    job.processor_history = [
        {
            "processor": "classification_processor",
            "result": {
                "payload": {
                    "detected_job_type": detected_job_type,
                    "confidence": 0.8,
                    "reasons": ["test_fixture"],
                }
            },
        }
    ]
    for processor, payload in processor_payloads or []:
        job.processor_history.append({"processor": processor, "result": {"payload": payload}})
    job.result = {
        "status": "completed",
        "requires_human_review": False,
        "payload": {"detected_job_type": detected_job_type, "confidence": 0.8},
    }
    return job


class TestSwedishClassificationQuality:
    def test_core_classification_examples(self):
        examples = [
            ("Offert laddbox", "Hej, jag vill ha offert på laddbox", "lead"),
            ("Support", "Solcellerna producerar inget sedan igår", "customer_inquiry"),
            ("Faktura", "Här kommer faktura för utfört arbete", "invoice"),
            ("Bokad tid", "Kan ni flytta min bokade tid?", "customer_inquiry"),
            ("Fel bolag", "Ni har skickat detta till fel person och fel bolag", "unknown"),
            ("Spam", "Spam eller säljutskick om SEO och billiga länkar", "spam"),
        ]

        for subject, body, expected in examples:
            assert _classify_deterministic(subject, body) == expected

    def test_sensitive_customer_conflict_classifies_as_inquiry_not_lead(self):
        detected = _classify_deterministic(
            "Missnöjd kund",
            "Jag är missnöjd och vill häva avtalet. Kontakta min advokat.",
        )
        assert detected == "customer_inquiry"

    def test_unclear_empty_message_falls_back_to_unknown(self):
        assert _classify_deterministic(" ", " ") == "unknown"


class TestLeadQualificationQuality:
    def test_ev_charger_lead_missing_core_fields_asks_questions(self):
        input_data = {
            "subject": "Offert laddbox",
            "message_text": "Hej, jag vill ha offert på laddbox till min villa.",
        }
        entities = {"email": "kund@example.com"}

        analysis = analyze_lead(input_data, entities)
        missing = compute_missing_info(analysis.lead_type, input_data, entities)
        lead_score = score_lead(analysis, missing, entities, input_data)
        next_action = decide_next_action(lead_score, missing)

        assert analysis.lead_type == "ev_charger"
        assert "address" in missing.missing_fields
        assert "main_fuse" in missing.missing_fields
        assert next_action == "ask_questions"

    def test_complete_low_risk_lead_can_prepare_next_step_without_free_dispatch(self):
        input_data = {
            "subject": "Offert laddbox",
            "message_text": (
                "Hej, jag vill ha offert på en laddbox till villa på Storgatan 1 i Solna. "
                "Huvudsäkring 20A och installation gärna nästa månad."
            ),
        }
        entities = {"email": "kund@example.com", "address": "Storgatan 1", "city": "Solna"}

        analysis = analyze_lead(input_data, entities)
        missing = compute_missing_info(analysis.lead_type, input_data, entities)
        lead_score = score_lead(analysis, missing, entities, input_data)
        next_action = decide_next_action(lead_score, missing, tenant_auto_actions={"lead": False})

        assert analysis.lead_type == "ev_charger"
        assert missing.completeness_score >= 0.7
        assert next_action in {"create_offer_draft", "approval_required"}


class TestSupportAndInvoiceRiskQuality:
    def test_support_outage_escalates_when_production_stopped(self):
        input_data = {
            "subject": "Solcellerna producerar inget",
            "message_text": "Hela anläggningen är nere och solcellerna producerar inget.",
        }
        entities = {"address": "Storgatan 1"}

        analysis = analyze_support(input_data, entities)
        missing = compute_support_missing_info(analysis.ticket_type, input_data, entities)
        priority = prioritize_support(analysis, missing, entities, input_data)
        next_action = decide_support_next_action(analysis, missing, priority)

        assert analysis.ticket_type == "issue"
        assert analysis.urgency == "high"
        assert analysis.requires_human is True
        assert next_action.action in {"create_task", "escalate"}
        assert next_action.requires_approval is True

    def test_invoice_payment_demand_requires_manual_policy(self):
        job = _job(
            "Inkasso och betalningskrav",
            "Detta är ett inkassokrav. Betala omgående annars går ärendet vidare.",
            detected_job_type="invoice",
            processor_payloads=[
                (
                    "invoice_processor",
                    {
                        "validation_status": "validated",
                        "duplicate_suspected": False,
                        "missing_critical": [],
                        "approval_route": "approval_required",
                        "confidence": 0.9,
                        "validation": {"is_valid": True, "issues": []},
                    },
                )
            ],
        )

        result = process_policy_job(job)
        payload = result.result["payload"]

        assert payload["decision"] == "hold_for_review"
        assert payload["approval_route"] == "manual_review"
        assert payload["recommended_next_step"] == "manual_review"
        assert "risk:debt_collection" in payload["reasons"]


class TestDoNotTouchPolicyQuality:
    def test_sensitive_cases_hold_for_human_review(self):
        scenarios = [
            ("Juridiskt hot", "Vi går till advokat om ni inte löser detta idag.", "legal_threat"),
            ("Reklamation", "Detta är en reklamation på arbetet ni utförde.", "complaint"),
            ("Hävning", "Jag vill häva avtalet och bestrider kostnaden.", "contract_dispute"),
            ("Radera data", "Radera alla mina personuppgifter i era system.", "data_deletion"),
            ("Säkerhetsrisk", "Det luktar bränt och finns risk för brand i elcentralen.", "safety_risk"),
        ]

        for subject, body, category in scenarios:
            job = _job(subject, body)
            result = process_policy_job(job)
            payload = result.result["payload"]

            assert result.result["requires_human_review"] is True
            assert payload["decision"] == "hold_for_review"
            assert payload["target_queue"] == "manual_review"
            assert f"risk:{category}" in payload["reasons"]

    def test_handoff_created_for_policy_hold(self):
        job = _job("Avtalsfråga", "Jag bestrider avtalet och kräver ekonomisk kompensation.")
        held = process_policy_job(job)
        handed_off = process_human_handoff_job(held)

        payload = handed_off.result["payload"]
        assert payload["handoff_created"] is True
        assert payload["handoff_type"] == "manual_review"
        assert payload["suggested_next_step"] == "manual_review"


class TestCustomerReplyQuality:
    def test_sensitive_inquiry_reply_is_approval_gated_and_not_binding(self):
        job = _job(
            "Reklamation",
            "Jag är missnöjd och vill häva avtalet. Jag kräver kompensation.",
        )
        actions = _build_inquiry_default_actions(
            job,
            {
                "followups_enabled": True,
                "internal_notification_email": "support@example.com",
                "auto_actions": {"customer_inquiry": True},
            },
        )

        customer_reply = next(a for a in actions if a["type"] == "send_customer_auto_reply")
        body = customer_reply["body"].lower()

        assert customer_reply["_needs_approval"] is True
        assert "ansvarig handläggare" in body
        assert "kompensation beviljas" not in body
        assert "häver avtalet" not in body

    def test_low_risk_inquiry_still_routes_to_monday(self):
        job = _job("Fråga", "Kan ni flytta min bokade tid till nästa vecka?")
        actions = _build_inquiry_default_actions(
            job,
            {
                "followups_enabled": True,
                "internal_notification_email": "support@example.com",
                "auto_actions": {"customer_inquiry": True},
            },
        )

        assert any(a["type"] == "create_monday_item" for a in actions)
        assert any(a["type"] == "send_internal_handoff" for a in actions)
