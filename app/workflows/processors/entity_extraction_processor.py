import re

from app.domain.workflows.models import Job


def process_entity_extraction_job(job: Job) -> Job:
    payload = job.input_data or {}

    subject = (payload.get("subject") or "").strip()
    message_text = (payload.get("message_text") or "").strip()
    sender = payload.get("sender") or {}
    attachments = payload.get("attachments") or []

    combined_text = f"{subject}\n{message_text}"

    invoice_number = extract_invoice_number(combined_text)
    amount = extract_amount(combined_text)
    email = extract_email(combined_text) or (sender.get("email") or "").strip().lower()
    phone = extract_phone(combined_text) or (sender.get("phone") or "").strip()
    customer_name = (sender.get("name") or "").strip()

    extracted = {
        "invoice_number": invoice_number,
        "amount": amount,
        "email": email,
        "phone": phone,
        "customer_name": customer_name,
        "subject": subject,
        "attachment_count": len(attachments),
    }

    missing_critical = []
    if not subject and not message_text:
        missing_critical.append("missing_text_content")

    job.result = {
        "status": "completed",
        "summary": "Fält extraherade.",
        "requires_human_review": len(missing_critical) > 0,
        "payload": {
            "processor_name": "entity_extraction_processor",
            "extracted_entities": extracted,
            "missing_critical": missing_critical,
        },
    }

    return job


def extract_invoice_number(text: str) -> str | None:
    patterns = [
        r"(?:faktura(?:nummer)?|invoice(?: number)?)[:\s#-]*([A-Za-z0-9-]+)",
        r"\b(?:INV|FAK)[- ]?(\d{3,})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return None


def extract_amount(text: str) -> float | None:
    patterns = [
        r"(\d+[.,]\d{2})\s*kr",
        r"belopp[:\s]+(\d+[.,]\d{2})",
        r"total[:\s]+(\d+[.,]\d{2})",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            raw = match.group(1).replace(",", ".")
            try:
                return float(raw)
            except ValueError:
                return None

    return None


def extract_email(text: str) -> str | None:
    match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    if match:
        return match.group(0).strip().lower()
    return None


def extract_phone(text: str) -> str | None:
    match = re.search(r"(\+46\s?\d{1,3}\s?\d{2,3}\s?\d{2,3}\s?\d{2,3}|0\d{1,3}[- ]?\d{2,3}[- ]?\d{2,3}[- ]?\d{2,3})", text)
    if match:
        return match.group(1).strip()
    return None