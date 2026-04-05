from pydantic import BaseModel


class InvoiceExtractionResult(BaseModel):
    invoice_number: str | None = None
    amount: float | None = None
    supplier_name: str | None = None


def extract_invoice_data(text: str, fallback_amount=None) -> InvoiceExtractionResult:
    amount = None

    if fallback_amount is not None:
        try:
            amount = float(fallback_amount)
        except (TypeError, ValueError):
            amount = None

    return InvoiceExtractionResult(
        invoice_number=None,
        amount=amount,
        supplier_name=None,
    )