from app.ai.schemas import ClassificationResponse
from app.domain.workflows.models import Job
from app.workflows.intelligence_safety import assess_content_risk
from app.workflows.processors.ai_processor_utils import run_ai_step


PROCESSOR_NAME = "classification_processor"
PROMPT_NAME = "classification"

# Priority order (highest -> lowest):
# spam > wrong_recipient/unclear > newsletter > internal > invoice > supplier
# > partnership > support/customer_inquiry > lead > customer_inquiry.
# The deterministic path returns "unknown" for empty/unclear/wrong-recipient
# content so the system does not confidently automate ambiguous input.

_SPAM_KEYWORDS = {
    "you won", "click here to claim", "lottery", "nigerian prince",
    "free money", "make money fast", "enlarge", "casino bonus",
    "phishing", "wire transfer urgent", "verify your account immediately",
    "spam", "säljutskick", "seo erbjudande", "köp länkar", "billiga länkar",
    "massmail", "cold outreach", "leadlista",
}

_WRONG_RECIPIENT_KEYWORDS = {
    "fel person", "fel bolag", "fel företag", "inte avsett för er",
    "wrong person", "wrong company", "wrong recipient",
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
    "offert", "pris", "köpa", "intresserad", "installera", "installation av",
    "boka installation", "montering", "besiktning", "kostnadsförslag",
    "förfrågan", "vill ha",
    "quote", "pricing", "buy", "purchase", "interested",
    "demo", "trial", "inspection", "repair",
}

_SUPPORT_KEYWORDS = {
    "fungerar inte", "producerar inget", "trasig", "felkod", "larm",
    "driftstopp", "helt nere", "problem med", "support",
    "boka om", "omboka", "flytta min bokade tid", "avboka",
    "reklamation", "missnöjd", "häva avtalet", "avtalsfråga",
    "inkasso", "betalningskrav", "garanti", "klagomål",
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
    if not combined.strip():
        return "unknown"

    if any(kw in combined for kw in _SPAM_KEYWORDS):
        return "spam"
    if any(kw in combined for kw in _WRONG_RECIPIENT_KEYWORDS):
        return "unknown"
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
    if any(kw in combined for kw in _SUPPORT_KEYWORDS):
        return "customer_inquiry"
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


def process_classification_job(job: Job, trace=None) -> Job:
    context = _build_source_context(job)

    input_data = job.input_data or {}

    def _deterministic_fallback(error_message: str) -> dict:
        detected = _classify_deterministic(
            subject=input_data.get("subject") or "",
            body=input_data.get("message_text") or "",
        )
        risk = assess_content_risk(input_data)
        reasons = ["deterministic_fallback", "llm_unavailable"] + risk["reasons"]
        confidence = 0.35 if detected == "unknown" or risk["risk_detected"] else 0.5
        return {
            "detected_job_type": detected,
            "confidence": confidence,
            "reasons": reasons,
            "error": error_message,
            "recommended_next_step": "manual_review" if risk["risk_detected"] else detected,
            "risk": risk,
        }

    job = run_ai_step(
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
    if trace is not None and trace.db is not None:
        from app.workflows.decision_record import DecisionRecordType
        from app.workflows.decision_record_service import record_processor_decision
        from app.workflows.processors.ai_processor_utils import get_latest_processor_payload

        payload = get_latest_processor_payload(job, PROCESSOR_NAME)
        record_processor_decision(
            trace.db,
            trace,
            job,
            record_type=DecisionRecordType.CLASSIFICATION,
            processor_name=PROCESSOR_NAME,
            payload=payload,
        )
    return job