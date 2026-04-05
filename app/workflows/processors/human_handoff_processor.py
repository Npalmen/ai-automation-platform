from app.domain.workflows.models import Job


def process_human_handoff_job(job: Job) -> Job:
    previous_result = job.result or {}
    payload = previous_result.get("payload") or {}

    requires_human_review = previous_result.get("requires_human_review", False)
    detected_job_type = payload.get("detected_job_type", "unknown")
    confidence = payload.get("confidence", 0.0)
    reason_codes = payload.get("reasons", [])

    suggested_next_step = payload.get("recommended_next_step") or payload.get("routing") or payload.get("decision")

    if not requires_human_review:
        result = {
            "status": "completed",
            "summary": "Ingen manuell överlämning behövs.",
            "requires_human_review": False,
            "payload": {
                "processor_name": "human_handoff_processor",
                "handoff_created": False,
                "reason_codes": [],
                "human_summary": None,
                "suggested_next_step": suggested_next_step or "continue_automation",
            },
        }

        job.processor_history.append({
            "processor": "human_handoff_processor",
            "result": result,
        })
        job.result = result
        return job

    result = {
        "status": "completed",
        "summary": "Manuell överlämning skapad.",
        "requires_human_review": True,
        "payload": {
            "processor_name": "human_handoff_processor",
            "handoff_created": True,
            "reason_codes": reason_codes,
            "human_summary": f"Jobbet kräver manuell granskning. Typ: {detected_job_type}. Confidence: {confidence}.",
            "suggested_next_step": "manual_review",
        },
    }

    job.processor_history.append({
        "processor": "human_handoff_processor",
        "result": result,
    })
    job.result = result
    return job