from app.domain.workflows.models import Job
from app.workflows.processors.ai_processor_utils import (
    append_processor_result,
    get_latest_processor_payload,
)


PROCESSOR_NAME = "policy_processor"

LOW_CONFIDENCE_THRESHOLD = 0.70
VERY_LOW_CONFIDENCE_THRESHOLD = 0.50


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def process_policy_job(job: Job) -> Job:
    classification_payload = get_latest_processor_payload(job, "classification_processor")
    extraction_payload = get_latest_processor_payload(job, "entity_extraction_processor")
    invoice_payload = get_latest_processor_payload(job, "invoice_processor")
    lead_payload = get_latest_processor_payload(job, "lead_processor")
    inquiry_payload = get_latest_processor_payload(job, "customer_inquiry_processor")
    decisioning_payload = get_latest_processor_payload(job, "decisioning_processor")
    dispatch_payload = get_latest_processor_payload(job, "action_dispatch_processor")

    detected_job_type = classification_payload.get("detected_job_type", "unknown")

    classification_confidence = _to_float(classification_payload.get("confidence"))
    extraction_confidence = _to_float(extraction_payload.get("confidence"))
    lead_confidence = _to_float(lead_payload.get("confidence"))
    inquiry_confidence = _to_float(inquiry_payload.get("confidence"))
    invoice_confidence = _to_float(invoice_payload.get("confidence"))
    decisioning_confidence = _to_float(decisioning_payload.get("confidence"))

    validation_status = invoice_payload.get("validation_status")
    missing_critical = invoice_payload.get("missing_critical", [])
    duplicate_suspected = bool(invoice_payload.get("duplicate_suspected", False))
    approval_route = invoice_payload.get("approval_route")

    extraction_validation = extraction_payload.get("validation", {}) or {}
    invoice_validation = invoice_payload.get("validation", {}) or {}

    lead_routing = lead_payload.get("routing")
    inquiry_routing = inquiry_payload.get("routing")
    decision = decisioning_payload.get("decision")
    target_queue = decisioning_payload.get("target_queue")

    dispatch_errors = dispatch_payload.get("dispatch_errors", []) or []

    requires_human_review = False
    reasons: list[str] = []
    final_decision = "allow_auto"

    # hard fail / unknown
    if detected_job_type == "unknown":
        requires_human_review = True
        reasons.append("unknown_job_type")
        final_decision = "hold_for_review"

    # base confidence gate
    if classification_confidence < LOW_CONFIDENCE_THRESHOLD:
        requires_human_review = True
        reasons.append("low_classification_confidence")

    # extraction gate
    if extraction_payload:
        if extraction_confidence < LOW_CONFIDENCE_THRESHOLD:
            requires_human_review = True
            reasons.append("low_extraction_confidence")

        if not extraction_validation.get("is_valid", True):
            requires_human_review = True
            reasons.extend(extraction_validation.get("issues", []))

    # domain-specific gates
    if detected_job_type == "lead":
        if lead_confidence < LOW_CONFIDENCE_THRESHOLD:
            requires_human_review = True
            reasons.append("low_lead_confidence")

        if lead_routing == "manual_review":
            requires_human_review = True
            reasons.append("lead_requires_manual_review")

        # conflict: AI says lead, but decision route is missing/weird
        if decisioning_payload:
            if decisioning_confidence < LOW_CONFIDENCE_THRESHOLD:
                requires_human_review = True
                reasons.append("low_decisioning_confidence")

            if decision == "manual_review":
                requires_human_review = True
                reasons.append("decisioning_manual_review")

            elif decision == "hold":
                requires_human_review = True
                reasons.append("decisioning_hold")

            elif decision == "auto_route" and not target_queue:
                requires_human_review = True
                reasons.append("missing_target_queue")

    elif detected_job_type == "customer_inquiry":
        if inquiry_confidence < LOW_CONFIDENCE_THRESHOLD:
            requires_human_review = True
            reasons.append("low_inquiry_confidence")

        if inquiry_routing == "manual_review":
            requires_human_review = True
            reasons.append("inquiry_requires_manual_review")

        if decisioning_payload:
            if decisioning_confidence < LOW_CONFIDENCE_THRESHOLD:
                requires_human_review = True
                reasons.append("low_decisioning_confidence")

            if decision == "manual_review":
                requires_human_review = True
                reasons.append("decisioning_manual_review")

            elif decision == "hold":
                requires_human_review = True
                reasons.append("decisioning_hold")

    elif detected_job_type == "invoice":
        if invoice_confidence < LOW_CONFIDENCE_THRESHOLD:
            requires_human_review = True
            reasons.append("low_invoice_confidence")

        if not invoice_validation.get("is_valid", True):
            requires_human_review = True
            reasons.extend(invoice_validation.get("issues", []))

        if validation_status in {"incomplete", "manual_review"}:
            requires_human_review = True
            reasons.append("invoice_not_validated")

        if duplicate_suspected:
            requires_human_review = True
            reasons.append("invoice_duplicate_suspected")

        if approval_route in {"approval_required", "manual_review"}:
            requires_human_review = True
            reasons.append("invoice_requires_review")

    # very low confidence gate across processors
    confidence_map = {
        "classification": classification_confidence,
        "extraction": extraction_confidence,
        "lead": lead_confidence,
        "inquiry": inquiry_confidence,
        "invoice": invoice_confidence,
        "decisioning": decisioning_confidence,
    }

    for name, value in confidence_map.items():
        if value and value < VERY_LOW_CONFIDENCE_THRESHOLD:
            requires_human_review = True
            reasons.append(f"very_low_{name}_confidence")

    # dispatch gate
    if dispatch_errors:
        requires_human_review = True
        reasons.append("dispatch_failed")

    # final decision
    if detected_job_type == "invoice":
        if not requires_human_review and approval_route == "auto_approve":
            final_decision = "auto_approve"
        elif requires_human_review:
            final_decision = "hold_for_review"
        else:
            final_decision = "send_for_approval"

    else:
        final_decision = "hold_for_review" if requires_human_review else "allow_auto"

    # dedupe reasons
    reasons = sorted(set(reasons))

    result = {
        "status": "completed",
        "summary": "Policy bedömd.",
        "requires_human_review": requires_human_review,
        "payload": {
            "processor_name": PROCESSOR_NAME,
            "decision": final_decision,
            "reasons": reasons,
            "detected_job_type": detected_job_type,
            "classification_confidence": classification_confidence,
            "extraction_confidence": extraction_confidence,
            "lead_confidence": lead_confidence or None,
            "inquiry_confidence": inquiry_confidence or None,
            "invoice_confidence": invoice_confidence or None,
            "decisioning_confidence": decisioning_confidence or None,
            "target_queue": target_queue,
            "validation_status": validation_status,
            "missing_critical": missing_critical,
            "duplicate_suspected": duplicate_suspected,
            "approval_route": approval_route,
            "recommended_next_step": (
                "manual_review"
                if requires_human_review
                else (target_queue or final_decision)
            ),
        },
    }

    return append_processor_result(job, PROCESSOR_NAME, result)