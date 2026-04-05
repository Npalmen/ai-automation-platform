from typing import Any


def map_invoice_to_fortnox_customer(job_payload: dict[str, Any]) -> dict[str, Any]:
    data = job_payload.get("data", {}) or {}

    customer_number = (
        data.get("customer_number")
        or data.get("customer_no")
        or data.get("customer_id")
        or data.get("organization_number")
        or data.get("email")
        or "AUTO-CUSTOMER"
    )

    customer = {
        "CustomerNumber": str(customer_number)[:50],
    }

    if data.get("customer_name"):
        customer["Name"] = data["customer_name"]

    if data.get("organization_number"):
        customer["OrganisationNumber"] = data["organization_number"]

    if data.get("email"):
        customer["Email"] = data["email"]

    if data.get("phone"):
        customer["Phone1"] = data["phone"]

    if data.get("address1"):
        customer["Address1"] = data["address1"]

    if data.get("zip_code"):
        customer["ZipCode"] = data["zip_code"]

    if data.get("city"):
        customer["City"] = data["city"]

    if data.get("country_code"):
        customer["CountryCode"] = data["country_code"]

    return customer


def map_invoice_to_fortnox_invoice(job_payload: dict[str, Any]) -> dict[str, Any]:
    data = job_payload.get("data", {}) or {}

    customer_number = (
        data.get("customer_number")
        or data.get("customer_no")
        or data.get("customer_id")
        or data.get("organization_number")
        or data.get("email")
        or "AUTO-CUSTOMER"
    )

    amount = data.get("amount") or 0
    description = data.get("description") or data.get("invoice_description") or "Invoice"
    article_name = data.get("article_name") or description
    quantity = data.get("quantity") or 1
    unit_price = data.get("unit_price") or amount
    vat = data.get("vat") or 25

    invoice = {
        "CustomerNumber": str(customer_number)[:50],
        "InvoiceDate": data.get("invoice_date"),
        "DueDate": data.get("due_date"),
        "YourOrderNumber": data.get("external_reference") or data.get("invoice_number"),
        "Comments": data.get("comments") or description,
        "InvoiceRows": [
            {
                "Description": article_name,
                "DeliveredQuantity": quantity,
                "Price": unit_price,
                "VAT": vat,
            }
        ],
    }

    invoice = {k: v for k, v in invoice.items() if v not in (None, "", [])}
    return invoice