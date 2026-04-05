from app.domain.workflows.models import Job


def process_policy_job(job: Job) -> Job:
    classification_result = {}

    for item in reversed(job.processor_history):
        if item.get("processor") == "classification_processor":
            classification_result = item.get("result") or {}
            break

    classification_payload = classification_result.get("payload") or {}
    detected_job_type = classification_payload.get("detected_job_type", "unknown")
    confidence = classification_payload.get("confidence", 0.0)

    invoice_result = {}
    for item in reversed(job.processor_history):
        if item.get("processor") == "invoice_processor":
            invoice_result = item.get("result") or {}
            break

    invoice_payload = invoice_result.get("payload") or {}
    validation_status = invoice_payload.get("validation_status")
    missing_critical = invoice_payload.get("missing_critical", [])
    duplicate_suspected = invoice_payload.get("duplicate_suspected", False)
    approval_route = invoice_payload.get("approval_route")

    requires_human_review = False
    reasons = []

    if confidence < 0.75:
        requires_human_review = True
        reasons.append("low_confidence")

    if detected_job_type == "unknown":
        requires_human_review = True
        reasons.append("unknown_job_type")

    decision = "allow_auto"

    if detected_job_type == "invoice":
        if validation_status == "incomplete":
            requires_human_review = True
            reasons.append("invoice_incomplete")
            decision = "hold_for_review"

        elif validation_status == "duplicate_suspected" or duplicate_suspected:
            requires_human_review = True
            reasons.append("invoice_duplicate_suspected")
            decision = "hold_for_review"

        elif approval_route == "approval_required":
            requires_human_review = True
            reasons.append("invoice_requires_approval")
            decision = "send_for_approval"

        elif approval_route == "auto_approve" and validation_status == "validated":
            requires_human_review = False
            decision = "auto_approve"

    if detected_job_type != "invoice":
        if requires_human_review:
            decision = "hold_for_review"
        else:
            decision = "allow_auto"

    result = {
        "status": "completed",
        "summary": "Policy bedömd.",
        "requires_human_review": requires_human_review,
        "payload": {
            "processor_name": "policy_processor",
            "decision": decision,
            "reasons": reasons,
            "detected_job_type": detected_job_type,
            "confidence": confidence,
            "validation_status": validation_status,
            "missing_critical": missing_critical,
            "duplicate_suspected": duplicate_suspected,
            "approval_route": approval_route,
        },
    }

    job.processor_history.append({
        "processor": "policy_processor",
        "result": result,
    })
    job.result = result
    return job