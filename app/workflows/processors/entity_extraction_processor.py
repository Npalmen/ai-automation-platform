from app.ai.schemas import EntityExtractionResponse
from app.domain.workflows.models import Job
from app.workflows.processors.ai_processor_utils import (
    get_latest_processor_payload,
    run_ai_step,
)
from app.workflows.validators.entity_validator import validate_entities


PROCESSOR_NAME = "entity_extraction_processor"
PROMPT_NAME = "entity_extraction"


def _get_intake_origin(job: Job) -> dict:
    """Return origin dict from normalized intake payload, or empty dict."""
    intake_payload = get_latest_processor_payload(job, "universal_intake_processor")
    return intake_payload.get("origin") or {}


def _build_source_context(job: Job) -> dict:
    input_data = job.input_data or {}
    sender = input_data.get("sender") or {}
    attachments = input_data.get("attachments") or []

    # Include flat sender_* keys so the LLM prompt receives them when nested dict is absent.
    def _sender_field(nested_key: str, flat_key: str) -> str | None:
        return sender.get(nested_key) or input_data.get(flat_key) or None

    classification_payload = get_latest_processor_payload(job, "classification_processor")

    return {
        "job_id": job.job_id,
        "tenant_id": job.tenant_id,
        "job_type": job.job_type.value,
        "input_data": {
            "subject": input_data.get("subject"),
            "message_text": input_data.get("message_text"),
            "sender": {
                "name": _sender_field("name", "sender_name"),
                "email": _sender_field("email", "sender_email"),
                "phone": _sender_field("phone", "sender_phone"),
            },
            "attachments": attachments,
        },
        "history": {
            "classification": classification_payload,
        },
    }


def _apply_intake_fallback(entities: dict, origin: dict) -> dict:
    """
    Fill null entity fields from normalized intake origin when LLM left them empty.
    Only fills customer_name, email, and phone — the identity/contact fields.
    """
    result = dict(entities)
    if not result.get("customer_name"):
        result["customer_name"] = origin.get("sender_name") or None
    if not result.get("email"):
        result["email"] = origin.get("sender_email") or None
    if not result.get("phone"):
        result["phone"] = origin.get("sender_phone") or None
    return result


def process_entity_extraction_job(job: Job) -> Job:
    context = _build_source_context(job)
    origin = _get_intake_origin(job)

    def success_payload_builder(parsed):
        entities = _apply_intake_fallback(parsed.entities.model_dump(), origin)
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
        # Apply intake origin fallback so known sender data is not lost on LLM failure.
        entities = _apply_intake_fallback(
            {
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
            origin,
        )
        validation = validate_entities(entities)
        return {
            "processor_name": PROCESSOR_NAME,
            "entities": entities,
            "confidence": 0.0,
            "validation": {
                "is_valid": validation["is_valid"],
                "issues": validation["issues"],
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