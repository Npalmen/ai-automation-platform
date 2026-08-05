"""Shared qualification scenario plan builder (no render / no LLM / no writes)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario
from app.workflows.missing_fact_plan import build_missing_fact_plan
from app.workflows.reply_quality.customer_surface import extract_city_phrase
from app.workflows.reply_quality.pipeline import build_coworker_reply_plan_v2
from app.workflows.reply_quality.plan_v2 import CustomerReplyPlanV2
from app.workflows.safe_ack_eligibility import evaluate_safe_ack_eligibility


@dataclass(frozen=True)
class QualificationScenarioPlanContext:
    scenario: ProfileScenario
    input_data: dict[str, Any]
    entities: dict[str, Any]
    missing_fact_plan: Any
    eligibility: Any
    business_intent: str
    plan: CustomerReplyPlanV2


def build_qualification_scenario_inputs(
    scenario: ProfileScenario,
) -> tuple[dict[str, Any], dict[str, Any]]:
    setup = scenario.customer_state_setup or {}
    input_data = {
        "subject": scenario.input.subject,
        "message_text": scenario.input.message_text,
        "language": scenario.input.language,
        "_force_service_type": setup.get("service_type"),
        "_coworker_hermetic_eval": True,
        "_coworker_scenario_family": setup.get("coworker_family") or scenario.family,
        "sender": {
            "name": scenario.input.sender_name,
            "email": scenario.input.sender_email,
        },
    }
    entities: dict[str, Any] = {"email": scenario.input.sender_email}
    for key in setup.get("known_entities") or []:
        if key == "city":
            entities[key] = (
                extract_city_phrase(text=scenario.input.message_text, entities={}) or "Uppsala"
            )
        else:
            entities[key] = f"known-{key}"
    return input_data, entities


def _resolve_playbook_intent(scenario: ProfileScenario, eligibility) -> tuple[Any, str]:
    setup = scenario.customer_state_setup or {}
    playbook_intent = str(setup.get("business_intent") or "lead")
    coworker_family = setup.get("coworker_family")
    if coworker_family == "complaint_warranty":
        playbook_intent = "support_complaint"
    if not eligibility.eligible and playbook_intent in {"support_status", "support_complaint"}:
        eligibility = evaluate_safe_ack_eligibility(
            detected_job_type="lead",
            risk_detected=False,
            risk_categories=[],
            extraction_issues=[],
            input_data={
                "subject": scenario.input.subject,
                "message_text": scenario.input.message_text,
                "language": scenario.input.language,
            },
            recommendation=None,
            recommendation_raw="manual_review",
            low_confidence=True,
            used_fallback=False,
            business_intent={"primary_intent": "lead"},
        )
        if coworker_family == "complaint_warranty":
            playbook_intent = "support_complaint"
        elif coworker_family in {"existing_support_symptom", "existing_support_followup"}:
            playbook_intent = "support_status"
        else:
            playbook_intent = str(setup.get("business_intent") or "lead")
    return eligibility, playbook_intent


def build_qualification_scenario_reply_plan(
    scenario: ProfileScenario,
    *,
    signature_name: str = "Niklas",
    profile_id: str | None = None,
) -> CustomerReplyPlanV2 | None:
    """Build CustomerReplyPlanV2 for a qualification scenario without rendering."""
    _ = profile_id  # reserved for future profile-hash binding in callers
    setup = scenario.customer_state_setup or {}
    input_data, entities = build_qualification_scenario_inputs(scenario)
    missing = build_missing_fact_plan(
        input_data=input_data,
        entities=entities,
        service_type=setup.get("service_type"),
    )
    eligibility = evaluate_safe_ack_eligibility(
        detected_job_type="lead",
        risk_detected=False,
        risk_categories=[],
        extraction_issues=[],
        input_data=input_data,
        recommendation=None,
        recommendation_raw="manual_review",
        low_confidence=True,
        used_fallback=False,
        business_intent={"primary_intent": setup.get("business_intent")},
    )
    eligibility, playbook_intent = _resolve_playbook_intent(scenario, eligibility)
    if not eligibility.eligible:
        return None

    prev = os.environ.get("DIGITAL_COWORKER_REPLY_ENABLED")
    os.environ["DIGITAL_COWORKER_REPLY_ENABLED"] = "true"
    try:
        plan = build_coworker_reply_plan_v2(
            greeting="Hej,",
            signature_name=signature_name,
            missing_fact_plan=missing,
            eligibility=eligibility,
            input_data=input_data,
            entities=entities,
            business_intent=playbook_intent,
            thread_state=str(setup.get("thread_state") or "new_thread"),
        )
    finally:
        if prev is None:
            os.environ.pop("DIGITAL_COWORKER_REPLY_ENABLED", None)
        else:
            os.environ["DIGITAL_COWORKER_REPLY_ENABLED"] = prev
    return plan
