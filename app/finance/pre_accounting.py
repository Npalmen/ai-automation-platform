from __future__ import annotations

import re
from typing import Any


_AMOUNT_NUM_RE = re.compile(r"(\d{1,3}(?:[\s.]\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)")

_EX_VAT_RE = re.compile(
    r"(?:ex(?:kl(?:usive)?)?\s*(?:\.|)\s*moms|before vat|netto)\D{0,20}(\d[\d\s.,]*)",
    re.IGNORECASE,
)
_VAT_AMOUNT_RE = re.compile(
    r"(?:moms|vat)\D{0,20}(\d[\d\s.,]*)",
    re.IGNORECASE,
)
_TOTAL_RE = re.compile(
    r"(?:totalt|att betala|inkl(?:usive)?\s*(?:\.|)\s*moms|grand total)\D{0,20}(\d[\d\s.,]*)",
    re.IGNORECASE,
)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    m = _AMOUNT_NUM_RE.search(text)
    if not m:
        return None
    candidate = m.group(1).replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(candidate)
    except ValueError:
        return None


def _money(value: Any) -> float:
    parsed = _safe_float(value)
    return round(parsed or 0.0, 2)


def _sum_money_items(items: Any, *keys: str) -> float:
    if not isinstance(items, list):
        return 0.0
    total = 0.0
    for item in items:
        if not isinstance(item, dict):
            total += _money(item)
            continue
        for key in keys:
            if key in item:
                total += _money(item.get(key))
                break
    return round(total, 2)


def _extract_amount(pattern: re.Pattern[str], text: str) -> float | None:
    m = pattern.search(text or "")
    if not m:
        return None
    return _safe_float(m.group(1))


def _extract_vat_amount(text: str) -> float | None:
    for m in _VAT_AMOUNT_RE.finditer(text or ""):
        prefix = (text or "")[max(0, m.start() - 20):m.start()].strip().lower()
        if prefix.endswith(("exkl", "exklusive", "inkl", "inklusive")):
            continue
        return _safe_float(m.group(1))
    return None


def classify_vat_rate(text: str) -> int:
    lower = (text or "").lower()
    if any(k in lower for k in ("momsfri", "momsfritt", "omvänd moms", "reverse charge", "0% moms")):
        return 0
    if "12% moms" in lower or "moms 12" in lower or "12 % moms" in lower:
        return 12
    if "6% moms" in lower or "moms 6" in lower or "6 % moms" in lower:
        return 6
    return 25


def classify_expense_category(text: str) -> tuple[str, str]:
    lower = (text or "").lower()
    if any(k in lower for k in ("diesel", "bensin", "drivmedel", "fuel")):
        return ("fuel", "5610")
    if any(k in lower for k in ("resa", "travel", "hotell", "taxi", "mileage")):
        return ("travel", "5800")
    if any(k in lower for k in ("abonnemang", "programvara", "licens", "saas", "software")):
        return ("software", "6540")
    if any(k in lower for k in ("underentrepren", "konsult", "consulting")):
        return ("subcontractor", "4535")
    if any(k in lower for k in ("material", "komponent", "produkt", "vara")):
        return ("materials", "4010")
    return ("services", "4531")


def build_invoice_draft(
    *,
    tenant_id: str,
    job_id: str,
    input_data: dict[str, Any],
    invoice_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = invoice_payload or {}
    subject = str(input_data.get("subject") or "")
    message_text = str(input_data.get("message_text") or "")
    text = f"{subject}\n{message_text}".strip()

    invoice_number = payload.get("invoice_number")
    supplier_name = payload.get("supplier_name")
    due_date = payload.get("due_date")

    ex_vat = payload.get("amount_ex_vat")
    vat_amount = payload.get("vat_amount")
    inc_vat = payload.get("amount_inc_vat")
    fallback_amount = payload.get("amount")

    amount_ex_vat = _safe_float(ex_vat) or _extract_amount(_EX_VAT_RE, text)
    amount_vat = _safe_float(vat_amount) or _extract_vat_amount(text)
    amount_inc_vat = _safe_float(inc_vat) or _extract_amount(_TOTAL_RE, text) or _safe_float(fallback_amount)

    vat_rate = classify_vat_rate(text)
    if amount_ex_vat is None and amount_inc_vat is not None and vat_rate not in (0,):
        amount_ex_vat = round(amount_inc_vat / (1 + (vat_rate / 100.0)), 2)
    if amount_vat is None and amount_inc_vat is not None and amount_ex_vat is not None:
        amount_vat = round(amount_inc_vat - amount_ex_vat, 2)
    if amount_inc_vat is None and amount_ex_vat is not None and amount_vat is not None:
        amount_inc_vat = round(amount_ex_vat + amount_vat, 2)

    category, account_code = classify_expense_category(text)
    sender = input_data.get("sender") or {}
    supplier_email = sender.get("email") or input_data.get("sender_email")
    supplier_phone = sender.get("phone") or input_data.get("sender_phone")

    return {
        "tenant_id": tenant_id,
        "job_id": job_id,
        "invoice_number": invoice_number,
        "supplier_name": supplier_name or sender.get("name") or input_data.get("sender_name"),
        "supplier_email": supplier_email,
        "supplier_phone": supplier_phone,
        "due_date": due_date,
        "currency": payload.get("currency") or "SEK",
        "amount_ex_vat": amount_ex_vat,
        "vat_amount": amount_vat,
        "amount_inc_vat": amount_inc_vat,
        "vat_rate": vat_rate,
        "expense_category": category,
        "account_code_suggestion": account_code,
        "source_summary": {
            "subject": subject,
            "has_message_text": bool(message_text),
        },
    }


def build_visma_export_payload(draft: dict[str, Any]) -> dict[str, Any]:
    """Build Visma customer + customer-invoice payload from a finance draft."""
    from datetime import date

    from app.integrations.visma.mappers import (
        map_invoice_to_visma_customer,
        map_invoice_to_visma_invoice,
    )

    # Leave customerNumber empty in invoice payload when only a draft lookup hint exists.
    # Visma customer creation runs in the approved export path when needed.
    customer_ref = ""
    row_price = draft.get("amount_ex_vat") or draft.get("amount_inc_vat") or 0.0
    job_payload = {
        "data": {
            "customer_name": draft.get("supplier_name") or "Leverantör okänd",
            "customer_number": customer_ref,
            "email": draft.get("supplier_email"),
            "phone": draft.get("supplier_phone"),
            "city": "Sandboxstad",
            "zip_code": "11122",
            "country_code": "SE",
            "is_private_person": True,
            "amount": row_price,
            "unit_price": row_price,
            "quantity": 1,
            "description": (
                f"{draft.get('expense_category', 'services')} "
                f"(job {draft.get('job_id')})"
            ),
            "invoice_date": date.today().isoformat(),
            "due_date": draft.get("due_date"),
            "vat_rate": draft.get("vat_rate", 25),
            "external_reference": draft.get("invoice_number") or draft.get("job_id"),
            "comments": (
                f"Pre-accounting draft ({draft.get('expense_category')}) "
                f"konto {draft.get('account_code_suggestion')}"
            ),
        }
    }
    return {
        "customer": map_invoice_to_visma_customer(job_payload),
        "invoice": map_invoice_to_visma_invoice(job_payload),
    }


def build_fortnox_export_payload(draft: dict[str, Any]) -> dict[str, Any]:
    supplier_name = draft.get("supplier_name") or "Leverantör okänd"
    customer_number = (
        draft.get("supplier_email")
        or draft.get("supplier_name")
        or f"AUTO-{draft.get('job_id', 'UNKNOWN')}"
    )
    row_price = draft.get("amount_ex_vat") or draft.get("amount_inc_vat") or 0.0

    customer = {
        "CustomerNumber": str(customer_number)[:50],
        "Name": supplier_name,
    }
    if draft.get("supplier_email"):
        customer["Email"] = draft["supplier_email"]
    if draft.get("supplier_phone"):
        customer["Phone1"] = draft["supplier_phone"]

    invoice = {
        "CustomerNumber": str(customer_number)[:50],
        "InvoiceDate": None,
        "DueDate": draft.get("due_date"),
        "YourOrderNumber": draft.get("invoice_number") or draft.get("job_id"),
        "Comments": (
            f"Pre-accounting draft ({draft.get('expense_category')}) "
            f"konto {draft.get('account_code_suggestion')}"
        ),
        "InvoiceRows": [
            {
                "Description": (
                    f"{draft.get('expense_category', 'services')} "
                    f"(job {draft.get('job_id')})"
                ),
                "DeliveredQuantity": 1,
                "Price": row_price,
                "VAT": int(draft.get("vat_rate") or 25),
            }
        ],
    }
    return {
        "customer": customer,
        "invoice": invoice,
    }


def build_project_profitability(
    *,
    tenant_id: str,
    job_id: str,
    input_data: dict[str, Any],
    invoice_draft: dict[str, Any] | None = None,
) -> dict[str, Any]:
    workspace = input_data.get("operations_workspace") or {}
    finance = workspace.get("finance") or input_data.get("project_finance") or {}

    revenue = (
        _safe_float(finance.get("actual_revenue"))
        or _safe_float(finance.get("estimated_revenue"))
        or _safe_float(finance.get("contract_value"))
        or _safe_float((invoice_draft or {}).get("amount_ex_vat"))
        or _safe_float((invoice_draft or {}).get("amount_inc_vat"))
        or 0.0
    )
    material_cost = _money(finance.get("material_cost")) + _sum_money_items(
        finance.get("materials"), "cost", "amount", "total"
    )
    external_cost = _money(finance.get("external_cost")) + _sum_money_items(
        finance.get("external_costs"), "cost", "amount", "total"
    )
    other_cost = _money(finance.get("other_cost")) + _sum_money_items(
        finance.get("other_costs"), "cost", "amount", "total"
    )

    labor_hours = _safe_float(finance.get("labor_hours")) or _safe_float(finance.get("hours")) or 0.0
    labor_rate = _safe_float(finance.get("labor_rate")) or _safe_float(finance.get("hourly_rate")) or 0.0
    labor_cost = _money(finance.get("labor_cost")) or round(labor_hours * labor_rate, 2)

    total_cost = round(material_cost + external_cost + other_cost + labor_cost, 2)
    margin_amount = round(float(revenue) - total_cost, 2)
    margin_percent = round((margin_amount / float(revenue)) * 100, 1) if revenue else None

    if not revenue:
        status = "unknown"
        risk_reason = "Missing project revenue estimate."
    elif margin_amount < 0:
        status = "loss"
        risk_reason = "Costs exceed revenue."
    elif margin_percent is not None and margin_percent < 20:
        status = "risk"
        risk_reason = "Margin is below 20 percent."
    else:
        status = "healthy"
        risk_reason = None

    return {
        "tenant_id": tenant_id,
        "job_id": job_id,
        "currency": finance.get("currency") or (invoice_draft or {}).get("currency") or "SEK",
        "revenue": round(float(revenue), 2),
        "costs": {
            "materials": round(material_cost, 2),
            "labor": round(labor_cost, 2),
            "external": round(external_cost, 2),
            "other": round(other_cost, 2),
            "total": total_cost,
        },
        "labor": {
            "hours": round(float(labor_hours), 2),
            "rate": round(float(labor_rate), 2),
        },
        "margin_amount": margin_amount,
        "margin_percent": margin_percent,
        "status": status,
        "risk_reason": risk_reason,
        "source_summary": {
            "has_operations_workspace": bool(workspace),
            "has_finance_block": bool(finance),
            "used_invoice_draft": bool(invoice_draft),
        },
    }
