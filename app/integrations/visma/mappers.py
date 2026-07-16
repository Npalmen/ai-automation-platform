from typing import Any


def map_invoice_to_visma_customer(job_payload: dict[str, Any]) -> dict[str, Any]:
    data = job_payload.get("data", {}) or {}

    customer: dict[str, Any] = {
        "Name": data.get("customer_name") or "Unknown customer",
        "IsPrivatePerson": bool(data.get("is_private_person", True)),
        "InvoiceCity": data.get("city") or data.get("invoice_city") or "Sandboxstad",
        "InvoicePostalCode": data.get("zip_code") or "11122",
        "CountryCode": data.get("country_code") or "SE",
    }

    if data.get("customer_number"):
        customer["CustomerNumber"] = str(data["customer_number"])

    if data.get("organization_number"):
        customer["CorporateIdentityNumber"] = data["organization_number"]

    if data.get("email"):
        customer["Email"] = data["email"]

    if data.get("phone"):
        customer["Phone"] = data["phone"]

    if data.get("address1"):
        customer["Address1"] = data["address1"]

    if data.get("zip_code"):
        customer["ZipCode"] = data["zip_code"]

    if data.get("city"):
        customer["City"] = data["city"]

    if data.get("country_code"):
        customer["CountryCode"] = data["country_code"]

    return customer


def map_invoice_to_visma_invoice(job_payload: dict[str, Any]) -> dict[str, Any]:
    data = job_payload.get("data", {}) or {}

    quantity = data.get("quantity") or 1
    amount = data.get("amount") or 0
    unit_price = data.get("unit_price") or amount
    description = data.get("description") or data.get("invoice_description") or "Invoice line"
    vat_percent = data.get("vat_rate", 25)

    invoice: dict[str, Any] = {
        "CustomerNumber": str(
            data.get("customer_number")
            or data.get("customer_no")
            or data.get("customer_id")
            or ""
        ),
        "InvoiceDate": data.get("invoice_date"),
        "DueDate": data.get("due_date"),
        "YourReference": data.get("external_reference") or data.get("invoice_number"),
        "NoteText": data.get("comments") or description,
        "Rows": [
            {
                "Text": description,
                "Quantity": quantity,
                "UnitPrice": unit_price,
                "VatPercent": vat_percent,
            }
        ],
    }

    return {k: v for k, v in invoice.items() if v not in (None, "", [])}
