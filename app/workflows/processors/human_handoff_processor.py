from app.domain.workflows.models import Job
from app.workflows.approval_service import build_approval_request
from app.workflows.processors.ai_processor_utils import (
    append_processor_result,
    get_latest_processor_payload,
)

PROCESSOR_NAME = "human_handoff_processor"


def process_human_handoff_job(job: Job) -> Job:
    previous_result = job.result or {}
    payload = previous_result.get("payload") or {}
    requires_human_review = previous_result.get("requires_human_review", False)

    policy_payload = get_latest_processor_payload(job, "policy_processor")
    detected_job_type = policy_payload.get(
        "detected_job_type",
        payload.get("detected_job_type", "unknown"),
    )
    confidence = (
        payload.get("confidence")
        or payload.get("classification_confidence")
        or policy_payload.get("classification_confidence")
        or 0.0
    )
    reason_codes = policy_payload.get("reasons", []) or payload.get("reasons", [])
    suggested_next_step = (
        policy_payload.get("recommended_next_step")
        or payload.get("recommended_next_step")
        or payload.get("routing")
        or payload.get("decision")
        or payload.get("target_queue")
    )
    policy_decision = policy_payload.get("decision")

    if policy_decision == "send_for_approval":
        approval_request = build_approval_request(job)

        result = {
            "status": "completed",
            "summary": "Approval request created.",
            "requires_human_review": False,
            "payload": {
                "processor_name": PROCESSOR_NAME,
                "handoff_created": True,
                "handoff_type": "approval_request",
                "reason_codes": reason_codes,
                "human_summary": approval_request["summary"],
                "approval_request": approval_request,
                "suggested_next_step": "awaiting_approval",
            },
        }
        return append_processor_result(job, PROCESSOR_NAME, result)

    if not requires_human_review:
        result = {
            "status": "completed",
            "summary": "Ingen manuell överlämning behövs.",
            "requires_human_review": False,
            "payload": {
                "processor_name": PROCESSOR_NAME,
                "handoff_created": False,
                "handoff_type": None,
                "reason_codes": [],
                "human_summary": None,
                "suggested_next_step": suggested_next_step or "continue_automation",
            },
        }
        return append_processor_result(job, PROCESSOR_NAME, result)

    result = {
        "status": "completed",
        "summary": "Manuell överlämning skapad.",
        "requires_human_review": True,
        "payload": {
            "processor_name": PROCESSOR_NAME,
            "handoff_created": True,
            "handoff_type": "manual_review",
            "reason_codes": reason_codes,
            "human_summary": (
                f"Jobbet kräver manuell granskning. "
                f"Typ: {detected_job_type}. "
                f"Confidence: {confidence}. "
                f"Reasons: {', '.join(reason_codes) if reason_codes else 'n/a'}."
            ),
            "suggested_next_step": "manual_review",
        },
    }
    return append_processor_result(job, PROCESSOR_NAME, result)