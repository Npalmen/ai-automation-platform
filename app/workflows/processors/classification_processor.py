from app.ai.schemas import ClassificationResponse
from app.domain.workflows.models import Job
from app.workflows.processors.ai_processor_utils import run_ai_step


PROCESSOR_NAME = "classification_processor"
PROMPT_NAME = "classification"


def _build_source_context(job: Job) -> dict:
    input_data = job.input_data or {}
    sender = input_data.get("sender") or {}
    attachments = input_data.get("attachments") or []

    return {
        "job_id": job.job_id,
        "tenant_id": job.tenant_id,
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
    }


def process_classification_job(job: Job) -> Job:
    context = _build_source_context(job)

    return run_ai_step(
        job=job,
        processor_name=PROCESSOR_NAME,
        prompt_name = "classification_v1",
        context=context,
        response_model=ClassificationResponse,
        success_summary="Ärendet klassificerat med AI.",
        success_payload_builder=lambda parsed: {
            "detected_job_type": parsed.detected_job_type,
            "confidence": parsed.confidence,
            "reasons": parsed.reasons,
            "recommended_next_step": parsed.detected_job_type,
        },
        fallback_payload_builder=lambda error_message: {
            "detected_job_type": "unknown",
            "confidence": 0.0,
            "reasons": ["classification_failed"],
            "error": error_message,
            "recommended_next_step": "manual_review",
        },
    )