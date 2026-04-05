from app.workflows.validators.common import is_valid_email, is_valid_phone, normalize_text


def validate_entities(entities: dict) -> dict:
    issues: list[str] = []

    customer_name = normalize_text(entities.get("customer_name"))
    company_name = normalize_text(entities.get("company_name"))
    email = normalize_text(entities.get("email"))
    phone = normalize_text(entities.get("phone"))
    requested_service = normalize_text(entities.get("requested_service"))

    if email and not is_valid_email(email):
        issues.append("invalid_email")

    if phone and not is_valid_phone(phone):
        issues.append("invalid_phone")

    if not customer_name and not company_name:
        issues.append("missing_identity")

    if not requested_service:
        issues.append("missing_requested_service")

    return {
        "is_valid": len(issues) == 0,
        "issues": issues,
        "normalized_entities": {
            **entities,
            "customer_name": customer_name,
            "company_name": company_name,
            "email": email,
            "phone": phone,
            "requested_service": requested_service,
        },
    }