"""Invoice Routing Classifier.

Deterministic, keyword-based routing recommendation for invoice-like emails.
No LLM required. Called from invoice_processor after AI extraction.

Routing categories:
- debt_collection_review  : inkasso / kronofogden / kravbrev detected
- payment_reminder_review : påminnelse / förfallodatum passerat detected
- manual_review_required  : missing OCR/reference, validation failed, unknown signals
- forward_to_accounting   : clean validated invoice, no risk signals
- ignore_not_invoice      : email does not appear to be an invoice
"""
from __future__ import annotations

import re

# ── risk signal definitions ───────────────────────────────────────────────────

_DEBT_COLLECTION_KEYWORDS: list[str] = [
    "inkasso",
    "inkassobolag",
    "inkassokrav",
    "kronofogden",
    "kronofogdemyndigheten",
    "betalningsföreläggande",
    "kravbrev",
    "inkassoåtgärd",
    "rättslig åtgärd",
    "juridisk åtgärd",
]

_PAYMENT_REMINDER_KEYWORDS: list[str] = [
    "betalningspåminnelse",
    "påminnelse om betalning",
    "påminnelseavgift",
    "förfallodatum passerat",
    "förfallet",
    "förseningsavgift",
    "dröjsmålsränta",
    "ränta på förfallet",
    "obetalt",
    "påminnelse nr",
]

_NOT_INVOICE_KEYWORDS: list[str] = [
    "nyhetsbrev",
    "newsletter",
    "erbjudande",
    "kampanj",
    "prenumeration",
    "inbjudan",
    "event",
    "marknadsföring",
]


def _any_keyword(text: str, keywords: list[str]) -> tuple[bool, list[str]]:
    """Return (matched, list_of_matched_keywords)."""
    matched = []
    for kw in keywords:
        if re.search(r"\b" + re.escape(kw) + r"\b", text, re.IGNORECASE):
            matched.append(kw)
    return bool(matched), matched


# ── public API ────────────────────────────────────────────────────────────────

def classify_invoice_routing(
    invoice_payload: dict,
    subject: str,
    body: str,
) -> dict:
    """Classify the routing recommendation for an invoice-like email.

    Args:
        invoice_payload: Payload from invoice_processor (validation, missing_critical, etc.)
        subject:         Email subject line.
        body:            Email body text.

    Returns dict with keys:
        invoice_routing : str  — one of the five routing categories
        risk_signals    : list[str] — detected risk keywords
        routing_reason  : str  — human-readable explanation
    """
    combined = f"{subject} {body}"
    risk_signals: list[str] = []

    # 1. Not an invoice at all
    not_inv, not_inv_kws = _any_keyword(combined, _NOT_INVOICE_KEYWORDS)
    validation_status = invoice_payload.get("validation_status", "")
    approval_route = invoice_payload.get("approval_route", "")

    if validation_status == "ignore" or approval_route == "ignore":
        return {
            "invoice_routing": "ignore_not_invoice",
            "risk_signals": [],
            "routing_reason": "Classified as non-invoice by AI extraction.",
        }

    if not_inv and not invoice_payload.get("invoice_data", {}).get("invoice_number"):
        return {
            "invoice_routing": "ignore_not_invoice",
            "risk_signals": not_inv_kws,
            "routing_reason": "Marketing/newsletter content, no invoice number detected.",
        }

    # 2. Debt collection — highest priority risk
    debt, debt_kws = _any_keyword(combined, _DEBT_COLLECTION_KEYWORDS)
    if debt:
        risk_signals.extend(debt_kws)
        return {
            "invoice_routing": "debt_collection_review",
            "risk_signals": risk_signals,
            "routing_reason": (
                f"Debt collection signals detected: {', '.join(debt_kws)}. "
                "Requires immediate manual review."
            ),
        }

    # 3. Payment reminder
    reminder, reminder_kws = _any_keyword(combined, _PAYMENT_REMINDER_KEYWORDS)
    if reminder:
        risk_signals.extend(reminder_kws)
        return {
            "invoice_routing": "payment_reminder_review",
            "risk_signals": risk_signals,
            "routing_reason": (
                f"Payment reminder signals detected: {', '.join(reminder_kws)}. "
                "Review before paying."
            ),
        }

    # 4. Missing OCR / payment reference or validation failed
    missing_critical: list[str] = invoice_payload.get("missing_critical") or []
    reference_missing = any(
        kw in m for m in missing_critical
        for kw in ("reference", "ocr", "invoice_number", "amount")
    )
    validation_failed = not (invoice_payload.get("validation") or {}).get("is_valid", True)
    duplicate = bool(invoice_payload.get("duplicate_suspected"))

    if reference_missing or validation_failed or duplicate or validation_status == "manual_review":
        issues = []
        if reference_missing:
            issues.append("missing payment reference/OCR")
        if validation_failed:
            issues.append("validation failed")
        if duplicate:
            issues.append("duplicate suspected")
        return {
            "invoice_routing": "manual_review_required",
            "risk_signals": risk_signals,
            "routing_reason": (
                f"Invoice requires manual review: {'; '.join(issues) or 'validation issues'}."
            ),
        }

    # 5. Clean invoice — route to accounting
    return {
        "invoice_routing": "forward_to_accounting",
        "risk_signals": [],
        "routing_reason": "Invoice validated with no risk signals. Safe to forward to accounting.",
    }
