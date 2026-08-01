"""Safe acknowledgement path for incomplete but low-risk leads.

Separates operational routing (manual_review) from communication authorization
(send_for_approval) so a bounded customer reply can be drafted and gated by approval.

Eligibility is owned by app.workflows.safe_ack_eligibility — this module provides
backward-compatible shims and legacy body builder delegation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.workflows.decision_contract import DecisionRecommendation
from app.workflows.missing_fact_plan import MissingFactPlan, build_missing_fact_plan
from app.workflows.reply_planning import (
    CustomerReplyPlan,
    build_customer_reply_plan,
    render_customer_reply,
)
from app.workflows.safe_ack_eligibility import (
    SafeAckEligibilityResult,
    evaluate_safe_ack_eligibility,
)


@dataclass(frozen=True)
class SafeAcknowledgementEligibility:
    eligible: bool
    reasons: tuple[str, ...] = ()

    @classmethod
    def from_result(cls, result: SafeAckEligibilityResult) -> SafeAcknowledgementEligibility:
        if result.eligible:
            return cls(True, result.supporting_reason_codes)
        return cls(False, result.blocker_codes)


def evaluate_safe_acknowledgement_eligibility(
    *,
    detected_job_type: str,
    risk_detected: bool,
    risk_categories: list[str] | None,
    extraction_issues: list[str],
    input_data: dict[str, Any],
    recommendation: DecisionRecommendation | None,
    recommendation_raw: str | None,
    low_confidence: bool,
    used_fallback: bool,
    decisioning_reasons: list[str] | None = None,
    threat_assessment: dict[str, Any] | None = None,
    business_intent: dict[str, Any] | None = None,
    extracted_fact_set: dict[str, Any] | None = None,
) -> SafeAcknowledgementEligibility:
    """Backward-compatible shim — delegates to central safe_ack_eligibility."""
    result = evaluate_safe_ack_eligibility(
        detected_job_type=detected_job_type,
        risk_detected=risk_detected,
        risk_categories=risk_categories,
        extraction_issues=extraction_issues,
        input_data=input_data,
        recommendation=recommendation,
        recommendation_raw=recommendation_raw,
        low_confidence=low_confidence,
        used_fallback=used_fallback,
        decisioning_reasons=decisioning_reasons,
        threat_assessment=threat_assessment,
        business_intent=business_intent,
        extracted_fact_set=extracted_fact_set,
    )
    return SafeAcknowledgementEligibility.from_result(result)


def build_safe_acknowledgement_body(
    *,
    greeting: str,
    service_hint: str,
    missing_fields: list[str],
    signature_name: str,
    location_hint: str = "",
    question_labels: list[str] | None = None,
) -> str:
    """Build a bounded acknowledgement that requests missing information only."""
    labels = question_labels
    if labels is None:
        prompts: list[str] = []
        if "customer_name" in missing_fields or "name" in missing_fields or "contact_name" in missing_fields:
            prompts.append("Ditt namn")
        if "phone" in missing_fields or "phone_or_email" in missing_fields:
            prompts.append("Telefonnummer")
        if "address" in missing_fields or "location" in missing_fields:
            prompts.append("Adress eller ort")
        if "requested_service" in missing_fields or "service_type" in missing_fields:
            prompts.append("Vilken tjänst det gäller")
        labels = prompts or ["Namn", "Telefonnummer", "Adress"]

    plan = CustomerReplyPlan(
        acknowledgement_intent="safe_incomplete_lead_ack",
        verified_facts=(),
        service_hint=service_hint or "din förfrågan",
        location_hint=location_hint,
        missing_questions=tuple(labels),
        forbidden_commitments=("price", "booking", "warranty"),
        language="sv",
        tone="professional",
        next_step_wording="Förfrågan granskas av oss innan vi återkommer.",
        greeting=greeting,
        signature_name=signature_name,
        profile_service_type="legacy",
        fallback_template_key="safe_ack_incomplete_lead_v1",
        plan_provenance=("legacy_builder",),
        policy_version="reply_planning_v1",
    )
    return render_customer_reply(plan)
