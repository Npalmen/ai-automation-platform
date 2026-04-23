from app.ai.schemas import ClassificationResponse
from app.domain.workflows.models import Job
from app.workflows.processors.ai_processor_utils import run_ai_step


PROCESSOR_NAME = "classification_processor"
PROMPT_NAME = "classification"

_INVOICE_KEYWORDS = {"faktura", "invoice"}

_LEAD_KEYWORDS = {
    "offert", "pris", "köpa", "intresserad",
    "quote", "pricing", "buy", "purchase", "interested",
    "demo", "trial",
}


def _classify_deterministic(subject: str, body: str) -> str:
    """Return 'invoice', 'lead', or 'customer_inquiry' based on keyword match.

    Priority order: invoice > lead > customer_inquiry.
    Checks combined subject+body text case-insensitively.
    """
    combined = f"{subject} {body}".lower()
    if any(kw in combined for kw in _INVOICE_KEYWORDS):
        return "invoice"
    if any(kw in combined for kw in _LEAD_KEYWORDS):
        return "lead"
    return "customer_inquiry"


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

    input_data = job.input_data or {}

    def _deterministic_fallback(error_message: str) -> dict:
        detected = _classify_deterministic(
            subject=input_data.get("subject") or "",
            body=input_data.get("message_text") or "",
        )
        return {
            "detected_job_type": detected,
            "confidence": 0.5,
            "reasons": ["deterministic_fallback", "llm_unavailable"],
            "error": error_message,
            "recommended_next_step": detected,
        }

    return run_ai_step(
        job=job,
        processor_name=PROCESSOR_NAME,
        prompt_name="classification_v1",
        context=context,
        response_model=ClassificationResponse,
        success_summary="Ärendet klassificerat med AI.",
        success_payload_builder=lambda parsed: {
            "detected_job_type": parsed.detected_job_type,
            "confidence": parsed.confidence,
            "reasons": parsed.reasons,
            "recommended_next_step": parsed.detected_job_type,
        },
        fallback_payload_builder=_deterministic_fallback,
    )