from typing import Any


def map_invoice_to_visma_customer(job_payload: dict[str, Any]) -> dict[str, Any]:
    data = job_payload.get("data", {}) or {}

    customer = {
        "name": data.get("customer_name") or "Unknown customer",
    }

    if data.get("customer_number"):
        customer["customerNumber"] = str(data["customer_number"])

    if data.get("organization_number"):
        customer["corporateIdentityNumber"] = data["organization_number"]

    if data.get("email"):
        customer["email"] = data["email"]

    if data.get("phone"):
        customer["phone"] = data["phone"]

    if data.get("address1"):
        customer["address"] = data["address1"]

    if data.get("zip_code"):
        customer["zipCode"] = data["zip_code"]

    if data.get("city"):
        customer["city"] = data["city"]

    if data.get("country_code"):
        customer["countryCode"] = data["country_code"]

    return customer


def map_invoice_to_visma_invoice(job_payload: dict[str, Any]) -> dict[str, Any]:
    data = job_payload.get("data", {}) or {}

    quantity = data.get("quantity") or 1
    amount = data.get("amount") or 0
    unit_price = data.get("unit_price") or amount
    description = data.get("description") or data.get("invoice_description") or "Invoice line"

    invoice = {
        "customerNumber": str(
            data.get("customer_number")
            or data.get("customer_no")
            or data.get("customer_id")
            or ""
        ),
        "invoiceDate": data.get("invoice_date"),
        "dueDate": data.get("due_date"),
        "yourReference": data.get("external_reference") or data.get("invoice_number"),
        "noteText": data.get("comments") or description,
        "rows": [
            {
                "text": description,
                "quantity": quantity,
                "unitPrice": unit_price,
            }
        ],
    }

    invoice = {k: v for k, v in invoice.items() if v not in (None, "", [])}
    return invoice