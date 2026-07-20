from app.ai.schemas import DecisioningResponse
from app.domain.workflows.models import Job
from app.workflows.processors.ai_processor_utils import (
    get_latest_processor_payload,
    run_ai_step,
)


PROCESSOR_NAME = "decisioning_processor"
PROMPT_NAME = "decisioning"


def _build_source_context(job: Job) -> dict:
    input_data = job.input_data or {}
    sender = input_data.get("sender") or {}
    attachments = input_data.get("attachments") or []

    classification_payload = get_latest_processor_payload(job, "classification_processor")
    extraction_payload = get_latest_processor_payload(job, "entity_extraction_processor")
    lead_payload = get_latest_processor_payload(job, "lead_processor")
    inquiry_payload = get_latest_processor_payload(job, "customer_inquiry_processor")

    return {
        "job_id": job.job_id,
        "tenant_id": job.tenant_id,
        "job_type": job.job_type.value,
        "input_data": {
            "subject": input_data.get("subject"),
            "message_text": input_data.get("message_text"),
            "sender": {
                "name": sender.get("name"),
                "email": sender.get("email"),
                "phone": sender.get("phone"),
            },
            "attachments": attachments,
        },
        "history": {
            "classification": classification_payload,
            "entity_extraction": extraction_payload,
            "lead": lead_payload,
            "customer_inquiry": inquiry_payload,
        },
    }


def process_decisioning_job(job: Job, trace=None) -> Job:
    context = _build_source_context(job)

    job = run_ai_step(
        job=job,
        processor_name=PROCESSOR_NAME,
        prompt_name = "decisioning_v1",
        context=context,
        response_model=DecisioningResponse,
        success_summary="Nästa steg beslutat med AI.",
        success_payload_builder=lambda parsed: {
            "decision": parsed.decision,
            "target_queue": parsed.target_queue,
            "action_flags": parsed.action_flags.model_dump(),
            "reasons": parsed.reasons,
            "confidence": parsed.confidence,
            "recommended_next_step": parsed.target_queue,
        },
        fallback_payload_builder=lambda error_message: {
            "decision": "manual_review",
            "target_queue": "manual_review",
            "action_flags": {
                "create_crm_lead": False,
                "notify_human": True,
                "request_missing_data": False,
            },
            "reasons": ["decisioning_failed"],
            "confidence": 0.0,
            "low_confidence": True,
            "used_fallback": True,
            "error": error_message,
            "recommended_next_step": "manual_review",
        },
    )
    if trace is not None and trace.db is not None:
        from app.workflows.decision_record import DecisionRecordType
        from app.workflows.decision_record_service import record_processor_decision
        from app.workflows.processors.ai_processor_utils import get_latest_processor_payload

        payload = get_latest_processor_payload(job, PROCESSOR_NAME)
        record_processor_decision(
            trace.db,
            trace,
            job,
            record_type=DecisionRecordType.DECISIONING_RECOMMENDATION,
            processor_name=PROCESSOR_NAME,
            payload=payload,
        )
    return job