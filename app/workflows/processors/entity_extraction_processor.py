import re

from app.domain.workflows.models import Job


def extract_invoice_number(text: str):
    patterns = [
        r"(?:faktura|invoice)[^\w]?(\d{3,}[-/]\d+|\d{4,})",
        r"\b(\d{4,}[-/]\d+)\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    return None


def extract_amount(text: str):
    patterns = [
        r"(\d+(?:[ \.,]\d{3})*(?:[.,]\d{2})?)\s*(?:sek|kr)\b",
        r"\b(?:belopp|summa|att betala|total)\s*[:\-]?\s*(\d+(?:[ \.,]\d{3})*(?:[.,]\d{2})?)",
        r"\b(\d{4,})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            raw_value = match.group(1).strip()
            normalized = raw_value.replace(" ", "")

            if "," in normalized and "." in normalized:
                normalized = normalized.replace(".", "").replace(",", ".")
            elif "," in normalized:
                normalized = normalized.replace(",", ".")
            else:
                normalized = normalized

            try:
                value = float(normalized)
                if value.is_integer():
                    return int(value)
                return value
            except ValueError:
                continue

    return None


def extract_email(text: str):
    match = re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", text, re.IGNORECASE)
    if match:
        return match.group(0).strip().lower()
    return None


def extract_phone(text: str):
    match = re.search(r"(\+46\s?7\d[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}|0\d{2,3}[\s-]?\d{5,8})", text)
    if match:
        return match.group(1).strip()
    return None


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
    supplier_name = (sender.get("name") or "").strip()

    has_pdf_attachment = any(
        (att.get("filename") or "").lower().endswith(".pdf")
        for att in attachments
    )

    currency = None
    if "sek" in combined_text.lower() or "kr" in combined_text.lower():
        currency = "SEK"

    extracted = {
        "invoice_number": invoice_number,
        "amount": amount,
        "currency": currency,
        "supplier_name": supplier_name,
        "due_date": None,
        "email": email,
        "phone": phone,
        "customer_name": customer_name,
        "subject": subject,
        "message_text": message_text,
        "attachment_count": len(attachments),
        "has_pdf_attachment": has_pdf_attachment,
    }

    missing_critical = []
    if not subject and not message_text:
        missing_critical.append("missing_text_content")

    result = {
        "status": "completed",
        "summary": "Fält extraherade.",
        "requires_human_review": len(missing_critical) > 0,
        "payload": {
            "processor_name": "entity_extraction_processor",
            "extracted_entities": extracted,
            "missing_critical": missing_critical,
        },
    }

    job.processor_history.append({
        "processor": "entity_extraction_processor",
        "result": result,
    })
    job.result = result

    return job