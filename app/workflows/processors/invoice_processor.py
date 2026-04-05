from app.domain.workflows.models import Job
from app.workflows.processors.result_builder import build_processor_result
from app.workflows.processors.invoice_extractor import extract_invoice_data


from app.domain.workflows.models import Job


def process_invoice_job(job: Job) -> Job:
    payload = job.input_data or {}

    subject = (payload.get("subject") or "").strip()
    message_text = (payload.get("message_text") or "").strip()
    sender = payload.get("sender") or {}
    attachments = payload.get("attachments") or []

    extracted = extract_entities_from_history(job)

    invoice_number = extracted.get("invoice_number")
    amount = extracted.get("amount")
    supplier_name = extracted.get("customer_name") or (sender.get("name") or "").strip()
    supplier_email = extracted.get("email") or (sender.get("email") or "").strip().lower()

    risk_level = "low"
    requires_human_review = False
    reasons = []

    if not invoice_number:
        risk_level = "medium"
        requires_human_review = True
        reasons.append("missing_invoice_number")

    if amount is None:
        risk_level = "medium"
        requires_human_review = True
        reasons.append("missing_amount")

    if not attachments:
        risk_level = "medium"
        reasons.append("missing_attachment")

    if amount is not None and amount > 50000:
        risk_level = "high"
        requires_human_review = True
        reasons.append("high_amount")

    result = {
        "status": "completed",
        "summary": "Faktura behandlad.",
        "requires_human_review": requires_human_review,
        "payload": {
            "processor_name": "invoice_processor",
            "invoice_data": {
                "invoice_number": invoice_number,
                "amount": amount,
                "supplier_name": supplier_name,
                "supplier_email": supplier_email,
                "subject": subject,
                "message_text": message_text,
                "attachment_count": len(attachments),
            },
            "risk_level": risk_level,
            "reasons": reasons,
            "recommended_next_step": (
                "manual_review" if requires_human_review else "finance_approval"
            ),
        },
    }

    job.processor_history.append({
        "processor": "invoice_processor",
        "result": result,
    })

    job.result = result
    return job


def extract_entities_from_history(job: Job) -> dict:
    for item in reversed(job.processor_history):
        if item.get("processor") == "entity_extraction_processor":
            result = item.get("result") or {}
            payload = result.get("payload") or {}
            return payload.get("extracted_entities") or {}
    return {}