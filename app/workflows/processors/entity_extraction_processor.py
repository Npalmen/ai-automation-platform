from app.ai.schemas import EntityExtractionResponse
from app.domain.workflows.models import Job
from app.workflows.processors.ai_processor_utils import (
    get_latest_processor_payload,
    run_ai_step,
)
from app.workflows.validators.entity_validator import validate_entities


PROCESSOR_NAME = "entity_extraction_processor"
PROMPT_NAME = "entity_extraction"


def _build_source_context(job: Job) -> dict:
    input_data = job.input_data or {}
    sender = input_data.get("sender") or {}
    attachments = input_data.get("attachments") or []

    classification_payload = get_latest_processor_payload(job, "classification_processor")

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
        },
    }


def process_entity_extraction_job(job: Job) -> Job:
    context = _build_source_context(job)

    def success_payload_builder(parsed):
        entities = parsed.entities.model_dump()
        validation = validate_entities(entities)

        return {
            "processor_name": PROCESSOR_NAME,
            "entities": validation["normalized_entities"],
            "confidence": parsed.confidence,
            "validation": {
                "is_valid": validation["is_valid"],
                "issues": validation["issues"],
            },
            "recommended_next_step": (
                "manual_review" if not validation["is_valid"] else None
            ),
        }

    def fallback_payload_builder(error_message: str):
        return {
            "processor_name": PROCESSOR_NAME,
            "entities": {
                "customer_name": None,
                "company_name": None,
                "email": None,
                "phone": None,
                "organization_number": None,
                "invoice_number": None,
                "amount": None,
                "currency": None,
                "due_date": None,
                "requested_service": None,
                "address": None,
                "city": None,
                "notes": None,
            },
            "confidence": 0.0,
            "validation": {
                "is_valid": False,
                "issues": ["entity_extraction_failed"],
            },
            "error": error_message,
            "recommended_next_step": "manual_review",
        }

    updated_job = run_ai_step(
        job=job,
        processor_name=PROCESSOR_NAME,
        prompt_name = "entity_extraction_v1",
        context=context,
        response_model=EntityExtractionResponse,
        success_summary="Entiteter extraherade med AI.",
        success_payload_builder=success_payload_builder,
        fallback_payload_builder=fallback_payload_builder,
    )

    payload = updated_job.result["payload"]
    validation = payload.get("validation", {})
    if not validation.get("is_valid", True):
        updated_job.result["requires_human_review"] = True

    return updated_job