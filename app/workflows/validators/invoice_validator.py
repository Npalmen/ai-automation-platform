from app.workflows.validators.common import is_positive_amount, normalize_text


def build_invoice_fingerprint(invoice_data: dict) -> str:
    supplier_name = normalize_text(invoice_data.get("supplier_name")) or ""
    invoice_number = normalize_text(invoice_data.get("invoice_number")) or ""
    amount_inc_vat = invoice_data.get("amount_inc_vat")

    return "|".join(
        [
            supplier_name.lower(),
            invoice_number.lower(),
            str(amount_inc_vat or ""),
        ]
    )


def detect_duplicate(invoice_data: dict, history: list[dict]) -> bool:
    current_fp = build_invoice_fingerprint(invoice_data)

    if not current_fp.strip("|"):
        return False

    for step in history:
        result = step.get("result") or {}
        payload = result.get("payload") or {}

        processor_name = payload.get("processor_name")
        if processor_name not in {None, "invoice_processor"}:
            continue

        prev_invoice_data = payload.get("invoice_data") or {}
        prev_fp = build_invoice_fingerprint(prev_invoice_data)

        if prev_fp and prev_fp == current_fp:
            return True

    return False


def validate_invoice_data(invoice_data: dict, history: list[dict]) -> dict:
    issues: list[str] = []

    supplier_name = normalize_text(invoice_data.get("supplier_name"))
    organization_number = normalize_text(invoice_data.get("organization_number"))
    invoice_number = normalize_text(invoice_data.get("invoice_number"))
    invoice_date = normalize_text(invoice_data.get("invoice_date"))
    due_date = normalize_text(invoice_data.get("due_date"))
    currency = normalize_text(invoice_data.get("currency"))
    reference = normalize_text(invoice_data.get("reference"))

    amount_ex_vat = invoice_data.get("amount_ex_vat")
    vat_amount = invoice_data.get("vat_amount")
    amount_inc_vat = invoice_data.get("amount_inc_vat")

    if not supplier_name:
        issues.append("missing_supplier_name")

    if not invoice_number:
        issues.append("missing_invoice_number")

    if not due_date:
        issues.append("missing_due_date")

    if not is_positive_amount(amount_inc_vat):
        issues.append("invalid_amount_inc_vat")

    if currency and len(currency) not in {3, 4}:
        issues.append("invalid_currency")

    normalized = {
        "supplier_name": supplier_name,
        "organization_number": organization_number,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "due_date": due_date,
        "currency": currency,
        "amount_ex_vat": amount_ex_vat,
        "vat_amount": vat_amount,
        "amount_inc_vat": amount_inc_vat,
        "reference": reference,
    }

    duplicate = detect_duplicate(normalized, history)

    if duplicate:
        issues.append("duplicate_invoice_detected")

    return {
        "is_valid": len(issues) == 0,
        "issues": issues,
        "duplicate_suspected": duplicate,
        "normalized_invoice_data": normalized,
    }