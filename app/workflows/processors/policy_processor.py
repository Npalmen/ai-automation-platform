from __future__ import annotations

from typing import Any

from app.domain.workflows.models import Job
from app.workflows.processors.ai_processor_utils import (
    append_processor_result,
    get_latest_processor_payload,
)

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


def process_policy_job(job: Job) -> Job:
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

    decisioning_decision = decisioning_payload.get("decision")
    decisioning_target_queue = decisioning_payload.get("target_queue")
    decisioning_actions = decisioning_payload.get("actions") or []

    reasons: list[str] = []
    missing_critical: list[str] = []
    duplicate_suspected = False
    validation_status: str | None = None
    target_queue: str | None = None
    approval_route: str | None = None
    decision = "assist"
    requires_human_review = False
    recommended_next_step = "continue_automation"

    if extraction_issues:
        reasons.extend(extraction_issues)

    if input_data.get("force_approval_test") is True:
        result = {
            "status": "completed",
            "summary": "Policy bedömd.",
            "requires_human_review": False,
            "payload": {
                "processor_name": PROCESSOR_NAME,
                "decision": "send_for_approval",
                "reasons": ["forced_approval_test"],
                "detected_job_type": detected_job_type,
                "classification_confidence": classification_confidence,
                "extraction_confidence": extraction_confidence,
                "lead_confidence": lead_confidence,
                "inquiry_confidence": inquiry_confidence,
                "invoice_confidence": invoice_confidence,
                "decisioning_confidence": decisioning_confidence,
                "target_queue": None,
                "validation_status": "approval_test_mode",
                "missing_critical": [],
                "duplicate_suspected": False,
                "approval_route": "approval_required",
                "recommended_next_step": "awaiting_approval",
            },
        }
        return append_processor_result(job, PROCESSOR_NAME, result)

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

        if reasons or missing_critical or duplicate_suspected:
            decision = "hold_for_review"
            requires_human_review = True
            approval_route = "manual_review"
            recommended_next_step = "manual_review"
            target_queue = None
        else:
            decision = "send_for_approval"
            requires_human_review = False
            approval_route = "approval_required"
            recommended_next_step = "awaiting_approval"
            target_queue = None

    elif detected_job_type == "lead":
        target_queue = decisioning_target_queue or lead_target_queue
        approval_route = decisioning_payload.get("approval_route")

        low_confidence = bool(
            lead_payload.get("low_confidence", False)
            or decisioning_payload.get("low_confidence", False)
        )

        if low_confidence:
            reasons.append("lead_low_confidence")

        if extraction_issues:
            reasons.append("lead_missing_identity")

        if decisioning_decision == "send_for_approval":
            decision = "send_for_approval"
            requires_human_review = False
            approval_route = approval_route or "approval_required"
            recommended_next_step = "awaiting_approval"
        elif decisioning_decision == "auto_execute":
            decision = "auto_execute"
            requires_human_review = False
            approval_route = None
            recommended_next_step = "action_dispatch"
        elif low_confidence:
            decision = "hold_for_review"
            requires_human_review = True
            approval_route = "manual_review"
            recommended_next_step = "manual_review"
            target_queue = target_queue or "manual_review"
        else:
            decision = "auto_execute"
            requires_human_review = False
            approval_route = None
            recommended_next_step = (
                decisioning_payload.get("recommended_next_step")
                or lead_routing
                or "action_dispatch"
            )

    elif detected_job_type == "customer_inquiry":
        target_queue = decisioning_target_queue or inquiry_target_queue
        approval_route = decisioning_payload.get("approval_route")

        low_confidence = bool(
            inquiry_payload.get("low_confidence", False)
            or decisioning_payload.get("low_confidence", False)
        )

        if low_confidence:
            reasons.append("inquiry_low_confidence")

        if extraction_issues:
            reasons.append("inquiry_missing_identity")

        if decisioning_decision == "send_for_approval":
            decision = "send_for_approval"
            requires_human_review = False
            approval_route = approval_route or "approval_required"
            recommended_next_step = "awaiting_approval"
        elif decisioning_decision == "auto_execute":
            decision = "auto_execute"
            requires_human_review = False
            approval_route = None
            recommended_next_step = "action_dispatch"
        elif low_confidence:
            decision = "hold_for_review"
            requires_human_review = True
            approval_route = "manual_review"
            recommended_next_step = "manual_review"
            target_queue = target_queue or "manual_review"
        else:
            decision = "auto_execute"
            requires_human_review = False
            approval_route = None
            recommended_next_step = (
                decisioning_payload.get("recommended_next_step")
                or inquiry_routing
                or "action_dispatch"
            )

    else:
        decision = "hold_for_review"
        requires_human_review = True
        approval_route = "manual_review"
        recommended_next_step = "manual_review"
        target_queue = "manual_review"
        reasons.append("unknown_job_type")

    reasons = _dedupe(reasons)
    missing_critical = _dedupe(missing_critical)

    result = {
        "status": "completed",
        "summary": "Policy bedömd.",
        "requires_human_review": requires_human_review,
        "payload": {
            "processor_name": PROCESSOR_NAME,
            "decision": decision,
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
        },
    }

    return append_processor_result(job, PROCESSOR_NAME, result)