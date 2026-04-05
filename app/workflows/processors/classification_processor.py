from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job


def process_classification_job(job: Job) -> Job:
    payload = job.input_data or {}

    subject = (payload.get("subject") or "").strip().lower()
    message_text = (payload.get("message_text") or "").strip().lower()
    attachments = payload.get("attachments") or []

    combined_text = f"{subject} {message_text}"

    detected_type = JobType.UNKNOWN
    confidence = 0.50
    reasons = []

    if "faktura" in combined_text or "invoice" in combined_text:
        detected_type = JobType.INVOICE
        confidence = 0.90
        reasons.append("keyword_invoice")

    elif "avtal" in combined_text or "contract" in combined_text:
        detected_type = JobType.UNKNOWN
        confidence = 0.60
        reasons.append("contract_detected_but_not_enabled")

    elif any(word in combined_text for word in ["offert", "quote", "pris", "price"]):
        detected_type = JobType.LEAD
        confidence = 0.80
        reasons.append("keyword_lead")

    elif any(word in combined_text for word in ["hjälp", "support", "problem", "fel"]):
        detected_type = JobType.CUSTOMER_INQUIRY
        confidence = 0.75
        reasons.append("keyword_support")

    elif attachments and any(
        (att.get("filename") or "").lower().endswith(".pdf")
        for att in attachments
    ):
        detected_type = JobType.INVOICE
        confidence = 0.70
        reasons.append("pdf_attachment_hint")

    result = {
        "status": "completed",
        "summary": "Ärendet klassificerat.",
        "requires_human_review": confidence < 0.70,
        "payload": {
            "processor_name": "classification_processor",
            "detected_job_type": detected_type.value,
            "confidence": confidence,
            "reasons": reasons,
            "recommended_next_step": detected_type.value,
        },
    }

    job.processor_history.append({
        "processor": "classification_processor",
        "result": result,
    })
    job.result = result
    return job