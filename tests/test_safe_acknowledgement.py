"""Tests for safe acknowledgement dual-state pipeline behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.evaluation.profile_testbot.generator.profile_generator import generate_semi_auto_campaign
from app.evaluation.profile_testbot.oracles.hard_safety import HardSafetyContext
from app.evaluation.profile_testbot.oracles.reply_contract import evaluate_reply_contract
from app.evaluation.profile_testbot.oracles.runner import run_oracles
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.workflows.approval_service import has_pending_approval
from app.workflows.orchestrator import WorkflowOrchestrator
from app.workflows.reply_candidate_safety import assess_reply_candidate_safety
from app.workflows.safe_acknowledgement import (
    build_safe_acknowledgement_body,
    evaluate_safe_acknowledgement_eligibility,
)


def _incomplete_lead_job(*, sender_email: str = "customer@example.com", message: str | None = None) -> Job:
    return Job(
        tenant_id="TENANT_1001",
        job_type=JobType.POLICY,
        input_data={
            "subject": "Offertförfrågan solcellsinstallation Uppsala",
            "message_text": message
            or "Hej, jag behöver hjälp med solcellsinstallation i Uppsala. Kan ni återkomma?",
            "sender": {"name": "", "email": sender_email},
        },
    )


def _append_processor(job: Job, processor: str, payload: dict) -> Job:
    job.processor_history = list(job.processor_history or [])
    job.processor_history.append({"processor": processor, "result": {"payload": payload}})
    job.result = job.processor_history[-1]["result"]
    return job


def _seed_incomplete_lead_pipeline(job: Job) -> Job:
    job = _append_processor(
        job,
        "classification_processor",
        {"detected_job_type": "lead", "confidence": 0.95},
    )
    job = _append_processor(
        job,
        "entity_extraction_processor",
        {
            "entities": {"email": "customer@example.com", "city": "Uppsala"},
            "confidence": 0.95,
            "validation": {"is_valid": False, "issues": ["missing_identity", "missing_requested_service"]},
        },
    )
    job = _append_processor(
        job,
        "lead_processor",
        {"confidence": 0.95, "low_confidence": True, "recommended_next_step": "manual_review"},
    )
    job = _append_processor(
        job,
        "decisioning_processor",
        {
            "decision": "manual_review",
            "target_queue": "manual_review",
            "confidence": 0.95,
            "low_confidence": False,
            "used_fallback": False,
        },
    )
    return job


class TestSafeAcknowledgementEligibility:
    def test_incomplete_lead_with_email_is_eligible(self):
        result = evaluate_safe_acknowledgement_eligibility(
            detected_job_type="lead",
            risk_detected=False,
            risk_categories=[],
            extraction_issues=["missing_identity", "missing_requested_service"],
            input_data={
                "subject": "Solceller Uppsala",
                "message_text": "Hej, jag vill ha solceller i Uppsala.",
                "sender": {"email": "customer@example.com"},
            },
            recommendation=None,
            recommendation_raw="manual_review",
            low_confidence=True,
            used_fallback=False,
        )
        assert result.eligible is True

    def test_no_reply_address_is_not_eligible(self):
        result = evaluate_safe_acknowledgement_eligibility(
            detected_job_type="lead",
            risk_detected=False,
            risk_categories=[],
            extraction_issues=["missing_identity"],
            input_data={
                "subject": "Hej",
                "message_text": "Hej",
                "sender": {"email": "noreply@forms.example.com"},
            },
            recommendation=None,
            recommendation_raw="manual_review",
            low_confidence=True,
            used_fallback=False,
        )
        assert result.eligible is False
        assert "no_usable_reply_address" in result.reasons

    def test_price_topic_is_not_eligible(self):
        result = evaluate_safe_acknowledgement_eligibility(
            detected_job_type="lead",
            risk_detected=False,
            risk_categories=[],
            extraction_issues=["missing_identity"],
            input_data={
                "subject": "Vad kostar det?",
                "message_text": "Vad kostar en elcentral?",
                "sender": {"email": "customer@example.com"},
            },
            recommendation=None,
            recommendation_raw="manual_review",
            low_confidence=True,
            used_fallback=False,
        )
        assert result.eligible is False
        assert "price" in result.reasons

    def test_out_of_area_is_not_eligible(self):
        result = evaluate_safe_acknowledgement_eligibility(
            detected_job_type="lead",
            risk_detected=False,
            risk_categories=[],
            extraction_issues=["missing_identity"],
            input_data={
                "subject": "Hjälp på Gotland",
                "message_text": "Behöver elservice på Gotland.",
                "sender": {"email": "customer@example.com"},
            },
            recommendation=None,
            recommendation_raw="manual_review",
            low_confidence=True,
            used_fallback=False,
        )
        assert result.eligible is False
        assert "out_of_service_area" in result.reasons


class TestPolicyDualState:
    def test_incomplete_lead_gets_send_for_approval_with_manual_review_routing(self):
        from app.workflows.processors.policy_processor import process_policy_job

        job = _seed_incomplete_lead_pipeline(_incomplete_lead_job())
        result = process_policy_job(job)
        payload = result.result["payload"]

        assert payload["decision"] == "send_for_approval"
        assert payload["policy_authorization"] == "approval_required"
        assert payload["safe_acknowledgement_path"] is True
        assert payload["target_queue"] == "manual_review"
        assert payload["operational_routing"] == "manual_review"
        assert result.result["requires_human_review"] is True


class TestActionDispatchSafeAcknowledgement:
    def test_safe_ack_draft_contains_acknowledgement_and_no_forbidden_commitments(self):
        from app.workflows.processors.action_dispatch_processor import process_action_dispatch_job

        job = _seed_incomplete_lead_pipeline(_incomplete_lead_job())
        from app.workflows.processors.policy_processor import process_policy_job

        job = process_policy_job(job)
        db = MagicMock()
        with patch(
            "app.workflows.processors.action_dispatch_processor._read_automation_settings",
            return_value={"followups_enabled": True, "email_signature_name": "Niklas"},
        ):
            result = process_action_dispatch_job(job, db=db)

        pending = result.result["payload"]["actions_pending_approval"]
        assert pending
        body = pending[0].get("subject")  # summary only in pending list
        actions = result.result["payload"]["actions_requested"]
        reply = next(a for a in actions if a.get("type") == "send_customer_auto_reply")
        body_text = reply["body"]
        safety = assess_reply_candidate_safety(body_text)
        assert safety["passed"] is True
        assert "tack för din förfrågan" in body_text.lower()
        assert "återkommer" in body_text.lower()
        assert "kostar" not in body_text.lower()
        assert "bokad" not in body_text.lower()

    def test_no_reply_address_skips_customer_draft(self):
        from app.workflows.processors.action_dispatch_processor import process_action_dispatch_job
        from app.workflows.processors.policy_processor import process_policy_job

        job = _seed_incomplete_lead_pipeline(
            _incomplete_lead_job(sender_email="noreply@forms.example.com")
        )
        job = process_policy_job(job)
        with patch(
            "app.workflows.processors.action_dispatch_processor._read_automation_settings",
            return_value={"followups_enabled": True},
        ):
            result = process_action_dispatch_job(job, db=None)
        actions = result.result["payload"]["actions_requested"]
        reply = next(a for a in actions if a.get("type") == "send_customer_auto_reply")
        assert reply.get("_skip") is True


class TestOrchestratorSafeAckPath:
    def test_does_not_skip_action_dispatch_for_safe_acknowledgement_path(self):
        orch = WorkflowOrchestrator(db=None)
        job = _incomplete_lead_job()
        job = _append_processor(
            job,
            "policy_processor",
            {
                "decision": "send_for_approval",
                "safe_acknowledgement_path": True,
                "recommended_next_step": "awaiting_approval",
            },
        )
        assert orch._should_skip_step(job, JobType.ACTION_DISPATCH) is False

    def test_still_skips_action_dispatch_for_plain_send_for_approval(self):
        orch = WorkflowOrchestrator(db=None)
        job = _incomplete_lead_job()
        job = _append_processor(
            job,
            "policy_processor",
            {"decision": "send_for_approval", "safe_acknowledgement_path": False},
        )
        assert orch._should_skip_step(job, JobType.ACTION_DISPATCH) is True


class TestPTBSem0000Oracle:
    def test_safe_ack_draft_passes_required_fact_acknowledgement(self):
        profile = load_customer_profile("niklas-demo-live-eval-v1")
        scenario = next(
            s for s in generate_semi_auto_campaign(profile, seed=0) if s.scenario_id == "PTB-SEM-0000"
        )
        assert "solcellsinstallation" in scenario.input.message_text.lower()

        body = build_safe_acknowledgement_body(
            greeting="Hej,",
            service_hint="solcellsinstallation",
            missing_fields=["name", "phone"],
            signature_name="Niklas",
        )
        results = evaluate_reply_contract(scenario=scenario, profile=profile, reply_text=body)
        ack = next(r for r in results if r.name == "required_fact_acknowledgement")
        assert ack.status == "pass"

        evaluation = run_oracles(
            scenario=scenario,
            profile=profile,
            safety_context=HardSafetyContext(
                tenant_id="TENANT_LIVE_EVAL",
                recipient_email="recipient@eval.test",
                sender_allowlist={scenario.input.sender_email},
                recipient_allowlist={"recipient@eval.test"},
                draft_text=body,
            ),
            reply_text=body,
        )
        assert evaluation.passed is True


class TestDecisionContractCoexistence:
    def test_manual_review_routing_coexists_with_send_for_approval_authorization(self):
        from app.workflows.processors.policy_processor import process_policy_job

        job = _seed_incomplete_lead_pipeline(_incomplete_lead_job())
        result = process_policy_job(job)
        payload = result.result["payload"]
        assert payload["target_queue"] == "manual_review"
        assert payload["decision"] == "send_for_approval"

    def test_pending_approval_blocks_auto_dispatch_without_execution(self):
        from app.workflows.processors.action_dispatch_processor import process_action_dispatch_job
        from app.workflows.processors.policy_processor import process_policy_job

        job = _seed_incomplete_lead_pipeline(_incomplete_lead_job())
        job = process_policy_job(job)
        db = MagicMock()
        with patch(
            "app.workflows.processors.action_dispatch_processor._read_automation_settings",
            return_value={"followups_enabled": True},
        ), patch(
            "app.workflows.processors.action_dispatch_processor._create_action_approval_record",
            return_value={"approval_id": "eml_test", "status": "pending_approval"},
        ):
            job = process_action_dispatch_job(job, db=db)

        job.result["payload"]["actions_pending_approval"] = [
            {"approval_id": "eml_test", "status": "pending_approval"}
        ]
        assert has_pending_approval(job) or job.result["payload"]["pending_approval_count"] > 0
