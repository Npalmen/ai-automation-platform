from app.domain.workflows.models import Job


def process_human_handoff_job(job: Job) -> Job:
    previous_result = job.result or {}
    payload = previous_result.get("payload") or {}

    requires_human_review = previous_result.get("requires_human_review", False)
    reasons = payload.get("reasons") or []

    if not requires_human_review:
        job.result = {
            "status": "completed",
            "summary": "Ingen manuell överlämning behövs.",
            "requires_human_review": False,
            "payload": {
                "processor_name": "human_handoff_processor",
                "handoff_created": False,
                "reason_codes": [],
                "human_summary": "",
                "suggested_next_step": "continue_automation",
            },
        }
        return job

    detected_job_type = payload.get("detected_job_type", "unknown")
    confidence = payload.get("confidence", 0.0)

    human_summary = (
        f"Jobbet kräver manuell granskning. "
        f"Typ: {detected_job_type}. "
        f"Confidence: {confidence}."
    )

    job.result = {
        "status": "completed",
        "summary": "Manuell överlämning skapad.",
        "requires_human_review": True,
        "payload": {
            "processor_name": "human_handoff_processor",
            "handoff_created": True,
            "reason_codes": reasons,
            "human_summary": human_summary,
            "suggested_next_step": "manual_review",
        },
    }

    return job