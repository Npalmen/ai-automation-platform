# app/integrations/monday/mappers.py

from typing import Any


def map_lead_to_monday_item(job_payload: dict[str, Any]) -> dict[str, Any]:
    data = job_payload.get("data", {})
    classification = job_payload.get("classification") or {}
    scoring = job_payload.get("scoring") or {}

    name = data.get("name") or data.get("customer_name") or "New Lead"
    email = data.get("email")
    phone = data.get("phone")

    column_values = {
        "text": name,
        "email": {"email": email, "text": email} if email else None,
        "phone": {"phone": phone, "countryShortName": "SE"} if phone else None,
        "numbers": scoring.get("score"),
        "status": {"label": classification.get("type", "New")},
    }

    # rensa None
    column_values = {k: v for k, v in column_values.items() if v is not None}

    return {
        "item_name": name,
        "column_values": column_values,
    }


def map_inquiry_to_monday_item(job_payload: dict[str, Any]) -> dict[str, Any]:
    data = job_payload.get("data", {})
    classification = job_payload.get("classification") or {}

    subject = data.get("subject") or "New Inquiry"

    column_values = {
        "text": subject,
        "long_text": data.get("message"),
        "status": {"label": classification.get("category", "New")},
    }

    column_values = {k: v for k, v in column_values.items() if v is not None}

    return {
        "item_name": subject,
        "column_values": column_values,
    }


def map_invoice_to_monday_item(job_payload: dict[str, Any]) -> dict[str, Any]:
    data = job_payload.get("data", {})
    validation = job_payload.get("validation") or {}

    name = f"Invoice {data.get('invoice_number', 'unknown')}"

    column_values = {
        "text": data.get("supplier_name"),
        "numbers": data.get("amount"),
        "status": {"label": "Validated" if validation.get("valid") else "Review"},
    }

    column_values = {k: v for k, v in column_values.items() if v is not None}

    return {
        "item_name": name,
        "column_values": column_values,
    }