from app.domain.workflows.models import Job
from app.workflows.processors.ai_processor_utils import append_processor_result


PROCESSOR_NAME = "human_handoff_processor"


def process_human_handoff_job(job: Job) -> Job:
    previous_result = job.result or {}
    payload = previous_result.get("payload") or {}

    requires_human_review = previous_result.get("requires_human_review", False)
    detected_job_type = payload.get("detected_job_type", "unknown")
    confidence = payload.get("confidence") or payload.get("classification_confidence") or 0.0
    reason_codes = payload.get("reasons", [])
    suggested_next_step = (
        payload.get("recommended_next_step")
        or payload.get("routing")
        or payload.get("decision")
        or payload.get("target_queue")
    )

    if not requires_human_review:
        result = {
            "status": "completed",
            "summary": "Ingen manuell överlämning behövs.",
            "requires_human_review": False,
            "payload": {
                "processor_name": PROCESSOR_NAME,
                "handoff_created": False,
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