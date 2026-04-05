from app.ai.schemas import LeadScoringResponse
from app.domain.workflows.models import Job
from app.workflows.processors.ai_processor_utils import (
    get_latest_processor_payload,
    run_ai_step,
)


PROCESSOR_NAME = "lead_processor"
PROMPT_NAME = "lead_scoring"


def _build_source_context(job: Job) -> dict:
    input_data = job.input_data or {}
    sender = input_data.get("sender") or {}
    attachments = input_data.get("attachments") or []

    classification_payload = get_latest_processor_payload(job, "classification_processor")
    extraction_payload = get_latest_processor_payload(job, "entity_extraction_processor")

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
        },
    }


def process_lead_job(job: Job) -> Job:
    context = _build_source_context(job)

    return run_ai_step(
        job=job,
        processor_name=PROCESSOR_NAME,
        prompt_name = "lead_scoring_v1",
        context=context,
        response_model=LeadScoringResponse,
        success_summary="Lead score beräknad med AI.",
        success_payload_builder=lambda parsed: {
            "lead_score": parsed.lead_score,
            "priority": parsed.priority,
            "routing": parsed.routing,
            "reasons": parsed.reasons,
            "confidence": parsed.confidence,
            "recommended_next_step": parsed.routing,
        },
        fallback_payload_builder=lambda error_message: {
            "lead_score": 0,
            "priority": "low",
            "routing": "manual_review",
            "reasons": ["lead_scoring_failed"],
            "confidence": 0.0,
            "error": error_message,
            "recommended_next_step": "manual_review",
        },
    )