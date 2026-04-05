from app.domain.workflows.models import Job


def process_policy_job(job: Job) -> Job:
    payload = job.input_data or {}
    previous_result = job.result or {}

    classification_payload = previous_result.get("payload") or {}
    detected_job_type = classification_payload.get("detected_job_type", "unknown")
    confidence = classification_payload.get("confidence", 0.0)

    requires_human_review = False
    reasons = []

    if confidence < 0.70:
        requires_human_review = True
        reasons.append("low_confidence")

    if detected_job_type == "unknown":
        requires_human_review = True
        reasons.append("unknown_job_type")

    if detected_job_type in {"contract", "approval", "payment_followup"}:
        requires_human_review = True
        reasons.append("sensitive_job_type")

    decision = "allow_auto"
    if requires_human_review:
        decision = "hold_for_review"

    job.result = {
        "status": "completed",
        "summary": "Policy bedömd.",
        "requires_human_review": requires_human_review,
        "payload": {
            "processor_name": "policy_processor",
            "decision": decision,
            "reasons": reasons,
            "detected_job_type": detected_job_type,
            "confidence": confidence,
        },
    }

    return job