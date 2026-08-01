from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.domain.workflows.models import Job
from app.workflows.decision_contract import (
    PolicyAuthorization,
    is_force_approval_test_allowed,
    normalize_decision_recommendation,
    project_approval_route,
    project_policy_decision,
    project_recommended_next_step,
    resolve_policy_authorization,
)
from app.workflows.business_intent import BusinessIntentResult
from app.workflows.intelligence_safety import assess_content_risk
from app.workflows.reply_planning import build_internal_operator_note
from app.workflows.safe_ack_eligibility import evaluate_safe_ack_eligibility
from app.workflows.threat_assessment import ThreatAssessment
from app.workflows.processors.ai_processor_utils import (
    append_processor_result,
    get_latest_processor_payload,
)
from app.workflows.tenant_automation import read_tenant_auto_actions

from app.workflows.decision_record import DecisionRecordType
from app.workflows.decision_record_service import record_processor_decision

PROCESSOR_NAME = "policy_processor"


def _as_float(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    try:
        return float(str(value).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []

    for item in items:
        if not item:
            continue
        if item in seen:
            continue
        seen.add(item)
        result.append(item)

    return result


def process_policy_job(job: Job, db: Session | None = None, trace=None) -> Job:
    input_data = job.input_data or {}
    latest_payload = (job.result or {}).get("payload") or {}

    classification_payload = get_latest_processor_payload(job, "classification_processor")
    extraction_payload = get_latest_processor_payload(job, "entity_extraction_processor")
    invoice_payload = get_latest_processor_payload(job, "invoice_processor")
    lead_payload = get_latest_processor_payload(job, "lead_processor")
    inquiry_payload = get_latest_processor_payload(job, "customer_inquiry_processor")
    decisioning_payload = get_latest_processor_payload(job, "decisioning_processor")

    detected_job_type = (
        classification_payload.get("detected_job_type")
        or latest_payload.get("detected_job_type")
        or job.job_type.value
    )

    classification_confidence = _as_float(classification_payload.get("confidence"))
    extraction_confidence = _as_float(extraction_payload.get("confidence"))
    lead_confidence = _as_float(lead_payload.get("confidence"))
    inquiry_confidence = _as_float(inquiry_payload.get("confidence"))
    invoice_confidence = _as_float(invoice_payload.get("confidence"))
    decisioning_confidence = _as_float(decisioning_payload.get("confidence"))

    extraction_validation = extraction_payload.get("validation") or {}
    extraction_issues = extraction_validation.get("issues") or []

    invoice_validation = invoice_payload.get("validation") or {}
    invoice_issues = invoice_validation.get("issues") or []
    invoice_missing_critical = invoice_payload.get("missing_critical") or []
    invoice_duplicate_suspected = bool(invoice_payload.get("duplicate_suspected", False))
    invoice_validation_status = invoice_payload.get("validation_status")

    lead_routing = lead_payload.get("routing")
    lead_target_queue = lead_payload.get("target_queue")

    inquiry_routing = inquiry_payload.get("routing")
    inquiry_target_queue = inquiry_payload.get("target_queue")

    decisioning_raw = decisioning_payload.get("decision")
    decisioning_target_queue = decisioning_payload.get("target_queue")
    decisioning_actions = decisioning_payload.get("actions") or []
    used_fallback = bool(decisioning_payload.get("used_fallback"))

    reasons: list[str] = []
    missing_critical: list[str] = []
    duplicate_suspected = False
    validation_status: str | None = None
    target_queue: str | None = None

    risk = assess_content_risk(input_data)
    if risk["risk_detected"]:
        reasons.extend(risk["reasons"])

    if extraction_issues:
        reasons.extend(extraction_issues)

    recommendation = normalize_decision_recommendation(
        decisioning_raw,
        used_fallback=used_fallback,
    )

    low_confidence = False
    if detected_job_type == "lead":
        low_confidence = bool(
            lead_payload.get("low_confidence", False)
            or decisioning_payload.get("low_confidence", False)
        )
        target_queue = decisioning_target_queue or lead_target_queue
    elif detected_job_type == "customer_inquiry":
        low_confidence = bool(
            inquiry_payload.get("low_confidence", False)
            or decisioning_payload.get("low_confidence", False)
        )
        target_queue = decisioning_target_queue or inquiry_target_queue

    if low_confidence:
        reasons.append(f"{detected_job_type}_low_confidence")

    if detected_job_type == "lead" and extraction_issues:
        reasons.append("lead_missing_identity")
    if detected_job_type == "customer_inquiry" and extraction_issues:
        reasons.append("inquiry_missing_identity")

    invoice_has_issues = False
    if detected_job_type == "invoice":
        missing_critical.extend(invoice_missing_critical)
        duplicate_suspected = invoice_duplicate_suspected
        validation_status = invoice_validation_status

        if invoice_issues:
            reasons.extend(invoice_issues)

        if invoice_validation_status == "manual_review":
            reasons.append("invoice_not_validated")

        invoice_requires_review = bool(
            invoice_payload.get("recommended_next_step") == "manual_review"
            or latest_payload.get("recommended_next_step") == "manual_review"
        )
        if invoice_requires_review:
            reasons.append("invoice_requires_review")

        if duplicate_suspected:
            reasons.append("duplicate_suspected")

        invoice_has_issues = bool(reasons or missing_critical or duplicate_suspected)

    settings = get_settings()
    force_allowed = is_force_approval_test_allowed(
        input_data,
        allow_flag=settings.ALLOW_FORCE_APPROVAL_TEST,
    )

    auth_result = resolve_policy_authorization(
        detected_job_type=detected_job_type,
        recommendation=recommendation,
        recommendation_raw=str(decisioning_raw) if decisioning_raw is not None else None,
        auto_actions=read_tenant_auto_actions(job, db),
        low_confidence=low_confidence,
        used_fallback=used_fallback,
        risk_detected=bool(risk["risk_detected"]),
        force_approval_test=force_allowed,
        invoice_has_issues=invoice_has_issues,
    )

    decisioning_reasons = list(decisioning_payload.get("reasons") or [])

    intake_payload = get_latest_processor_payload(job, "universal_intake_processor")
    threat = ThreatAssessment.from_dict(intake_payload.get("threat_assessment"))
    threat_dict = threat.to_dict() if threat else None

    business_intent = BusinessIntentResult.from_dict(
        classification_payload.get("business_intent")
    )
    extracted_fact_set = extraction_payload.get("extracted_fact_set")

    safe_ack = evaluate_safe_ack_eligibility(
        detected_job_type=detected_job_type,
        risk_detected=bool(risk["risk_detected"]),
        risk_categories=list(risk.get("categories") or []),
        extraction_issues=list(extraction_issues),
        input_data=input_data,
        recommendation=recommendation,
        recommendation_raw=str(decisioning_raw) if decisioning_raw is not None else None,
        low_confidence=low_confidence,
        used_fallback=used_fallback,
        decisioning_reasons=decisioning_reasons,
        threat_assessment=threat,
        business_intent=business_intent,
        extracted_fact_set=extracted_fact_set,
    )
    safe_acknowledgement_path = safe_ack.eligible
    safe_ack_dict = safe_ack.to_dict()
    internal_operator_note = None
    if not safe_ack.customer_draft_allowed:
        internal_operator_note = build_internal_operator_note(
            threat_assessment=threat_dict,
            extracted_fact_set=extracted_fact_set,
            eligibility=safe_ack,
            hold_reason=safe_ack.blocker_codes[0] if safe_ack.blocker_codes else None,
            risk_categories=list(risk.get("categories") or []),
        ).to_dict()

    if threat and not threat.customer_draft_allowed:
        safe_acknowledgement_path = False
        authorization = PolicyAuthorization.HOLD_FOR_REVIEW
        reasons.append(f"threat_{threat.threat_class}")
        target_queue = threat.required_routing
        requires_human_review_override = True
    else:
        requires_human_review_override = False

    reasons.extend(auth_result.reasons)
    authorization = auth_result.authorization if not requires_human_review_override else authorization

    if safe_acknowledgement_path:
        authorization = PolicyAuthorization.APPROVAL_REQUIRED
        reasons.append("safe_acknowledgement_path")
        reasons.extend(safe_ack.supporting_reason_codes)
        if not target_queue:
            target_queue = "manual_review"

    decision = project_policy_decision(authorization)
    approval_route = project_approval_route(authorization)
    recommended_next_step = project_recommended_next_step(authorization)
    requires_human_review = authorization in (
        PolicyAuthorization.HOLD_FOR_REVIEW,
        PolicyAuthorization.NO_ACTION,
    )
    if safe_acknowledgement_path:
        requires_human_review = True
        target_queue = target_queue or "manual_review"
        recommended_next_step = "manual_review"

    if requires_human_review and not target_queue:
        target_queue = "manual_review"

    if detected_job_type == "lead" and authorization == PolicyAuthorization.EXECUTION_ALLOWED:
        recommended_next_step = (
            decisioning_payload.get("recommended_next_step")
            or lead_routing
            or recommended_next_step
        )
    if detected_job_type == "customer_inquiry" and authorization == PolicyAuthorization.EXECUTION_ALLOWED:
        recommended_next_step = (
            decisioning_payload.get("recommended_next_step")
            or inquiry_routing
            or recommended_next_step
        )

    reasons = _dedupe(reasons)
    missing_critical = _dedupe(missing_critical)

    result = {
        "status": "completed",
        "summary": "Policy bedömd.",
        "requires_human_review": requires_human_review,
        "payload": {
            "processor_name": PROCESSOR_NAME,
            "decision": decision,
            "policy_authorization": authorization.value,
            "decisioning_recommendation": (
                auth_result.recommendation.value if auth_result.recommendation else None
            ),
            "decisioning_recommendation_raw": auth_result.recommendation_raw,
            "reasons": reasons,
            "detected_job_type": detected_job_type,
            "classification_confidence": classification_confidence,
            "extraction_confidence": extraction_confidence,
            "lead_confidence": lead_confidence,
            "inquiry_confidence": inquiry_confidence,
            "invoice_confidence": invoice_confidence,
            "decisioning_confidence": decisioning_confidence,
            "target_queue": target_queue,
            "validation_status": validation_status,
            "missing_critical": missing_critical,
            "duplicate_suspected": duplicate_suspected,
            "approval_route": approval_route,
            "recommended_next_step": recommended_next_step,
            "actions_present": bool(decisioning_actions or input_data.get("actions")),
            "risk": risk,
            "needs_human": requires_human_review,
            "approval_required": approval_route in ("approval_required", "manual_review"),
            "route_to": target_queue,
            "next_best_action": recommended_next_step,
            "safe_acknowledgement_path": safe_acknowledgement_path,
            "safe_ack_eligibility": safe_ack_dict,
            "operational_routing": target_queue if safe_acknowledgement_path else None,
            "threat_assessment": threat_dict,
            "internal_operator_note": internal_operator_note,
        },
    }

    job = append_processor_result(job, PROCESSOR_NAME, result)
    record_processor_decision(
        db,
        trace,
        job,
        record_type=DecisionRecordType.POLICY_AUTHORIZATION,
        processor_name=PROCESSOR_NAME,
        payload=result["payload"],
    )
    return job
