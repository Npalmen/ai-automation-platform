from app.ai.schemas import ClassificationResponse
from app.domain.workflows.models import Job
from app.workflows.processors.ai_processor_utils import run_ai_step


PROCESSOR_NAME = "classification_processor"
PROMPT_NAME = "classification"

# Priority order (highest → lowest):
# spam > newsletter > internal > invoice > supplier > partnership > lead > customer_inquiry
# 'unknown' is never returned by deterministic path — it is an LLM-only output.

_SPAM_KEYWORDS = {
    "you won", "click here to claim", "lottery", "nigerian prince",
    "free money", "make money fast", "enlarge", "casino bonus",
    "phishing", "wire transfer urgent", "verify your account immediately",
}

_NEWSLETTER_KEYWORDS = {
    "nyhetsbrev", "newsletter", "unsubscribe", "avregistrera",
    "monthly update", "campaign", "product update", "webinar invite",
    "event invite", "promotional", "our latest offers", "denna veckas erbjudanden",
    "denna månads kampanjer", "kampanjer", "prenumerera",
}

_INTERNAL_KEYWORDS = {
    "intern notering", "internt", "internal note", "team update",
    "staff notice", "internal memo", "admin notice", "system notification",
}

_INVOICE_KEYWORDS = {"faktura", "invoice", "payment request", "billing document"}

_SUPPLIER_KEYWORDS = {
    "orderbekräftelse", "order confirmation", "leveransbekräftelse",
    "delivery confirmation", "shipment notification", "din beställning",
    "your order", "purchase confirmation", "order status", "material order",
    "kvitto", "receipt",
}

_PARTNERSHIP_KEYWORDS = {
    "samarbete", "partnership", "collaboration", "affiliate",
    "business proposal", "b2b", "subcontractor", "partner opportunity",
    "samarbetsförslag", "vi vill diskutera", "potentiellt samarbete",
    "joint venture", "strategic alliance",
}

_LEAD_KEYWORDS = {
    "offert", "pris", "köpa", "intresserad", "installation", "montering",
    "besiktning", "reparation", "service", "bokning", "boka",
    "quote", "pricing", "buy", "purchase", "interested",
    "demo", "trial", "inspection", "repair",
}


def _classify_deterministic(subject: str, body: str) -> str:
    """Return a classification type based on keyword priority order.

    Priority: spam > newsletter > internal > invoice > supplier > partnership > lead > customer_inquiry
    Never returns 'unknown' — that is reserved for the LLM.
    """
    return classify_email_type(subject, body)


def classify_email_type(subject: str, body: str) -> str:
    """Public deterministic classifier for inbox taxonomy v2.

    Reusable by any intake path (inbox, webhook, manual POST).
    Priority order: spam > newsletter > internal > invoice > supplier > partnership > lead > customer_inquiry
    """
    combined = f"{subject} {body}".lower()

    if any(kw in combined for kw in _SPAM_KEYWORDS):
        return "spam"
    if any(kw in combined for kw in _NEWSLETTER_KEYWORDS):
        return "newsletter"
    if any(kw in combined for kw in _INTERNAL_KEYWORDS):
        return "internal"
    if any(kw in combined for kw in _INVOICE_KEYWORDS):
        return "invoice"
    if any(kw in combined for kw in _SUPPLIER_KEYWORDS):
        return "supplier"
    if any(kw in combined for kw in _PARTNERSHIP_KEYWORDS):
        return "partnership"
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