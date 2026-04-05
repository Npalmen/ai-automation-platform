from app.domain.workflows.models import Job


AUTO_APPROVE_LIMIT = 10000


def get_extracted_entities(job: Job) -> dict:
    for item in reversed(job.processor_history):
        if item.get("processor") == "entity_extraction_processor":
            result = item.get("result") or {}
            payload = result.get("payload") or {}
            return payload.get("extracted_entities") or {}
    return {}


def normalize_supplier_name(value: str | None) -> str:
    return (value or "").strip().lower()


def build_duplicate_key(invoice_number: str | None, supplier_name: str | None, amount) -> str | None:
    if not invoice_number or not supplier_name or amount in (None, ""):
        return None
    return f"{normalize_supplier_name(supplier_name)}::{str(invoice_number).strip().lower()}::{amount}"


def invoice_seen_before(job: Job, duplicate_key: str | None) -> bool:
    if not duplicate_key:
        return False

    for item in job.processor_history:
        if item.get("processor") != "invoice_processor":
            continue

        result = item.get("result") or {}
        payload = result.get("payload") or {}
        invoice_data = payload.get("invoice_data") or {}

        existing_key = invoice_data.get("duplicate_key")
        if existing_key == duplicate_key:
            return True

    return False


def process_invoice_job(job: Job) -> Job:
    extracted = get_extracted_entities(job)

    invoice_number = extracted.get("invoice_number")
    amount = extracted.get("amount")
    currency = extracted.get("currency")
    supplier_name = extracted.get("supplier_name")
    due_date = extracted.get("due_date")
    has_pdf_attachment = extracted.get("has_pdf_attachment", False)

    missing_critical = []
    if not invoice_number:
        missing_critical.append("missing_invoice_number")
    if amount in (None, ""):
        missing_critical.append("missing_amount")
    if not supplier_name:
        missing_critical.append("missing_supplier_name")

    duplicate_key = build_duplicate_key(
        invoice_number=invoice_number,
        supplier_name=supplier_name,
        amount=amount,
    )
    duplicate_suspected = invoice_seen_before(job, duplicate_key)

    approval_route = "manual_review"
    if not missing_critical and not duplicate_suspected:
        if isinstance(amount, (int, float)) and amount <= AUTO_APPROVE_LIMIT:
            approval_route = "auto_approve"
        else:
            approval_route = "approval_required"

    requires_human_review = (
        len(missing_critical) > 0
        or duplicate_suspected
        or approval_route in {"approval_required", "manual_review"}
    )

    validation_status = "validated"
    if missing_critical:
        validation_status = "incomplete"
    elif duplicate_suspected:
        validation_status = "duplicate_suspected"

    result = {
        "status": "completed",
        "summary": "Faktura analyserad.",
        "requires_human_review": requires_human_review,
        "payload": {
            "processor_name": "invoice_processor",
            "invoice_data": {
                "invoice_number": invoice_number,
                "amount": amount,
                "currency": currency,
                "supplier_name": supplier_name,
                "due_date": due_date,
                "has_pdf_attachment": has_pdf_attachment,
                "duplicate_key": duplicate_key,
            },
            "missing_critical": missing_critical,
            "duplicate_suspected": duplicate_suspected,
            "validation_status": validation_status,
            "approval_route": approval_route,
            "auto_approve_limit": AUTO_APPROVE_LIMIT,
            "recommended_next_step": approval_route,
        },
    }

    job.processor_history.append({
        "processor": "invoice_processor",
        "result": result,
    })
    job.result = result
    return job