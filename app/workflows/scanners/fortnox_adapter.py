"""
Fortnox workflow scanner adapter.

Reads customers, articles, and invoices from the Fortnox REST API.
Read-only: does NOT create, update, or delete any Fortnox records.
Does NOT auto-route. Does NOT write any accounting data.

Populated output (system_map.fortnox)
--------------------------------------
customers : list of customer objects (customer_number, name, email, organisation_number, phone)
articles  : list of article objects (article_number, description, unit, sales_price)
invoices  : list of invoice objects (document_number, customer_number, customer_name,
            total, balance, status, due_date)

Summary (workflow_scan.summary.fortnox)
-----------------------------------------
customers_scanned           : int
articles_scanned            : int
invoices_scanned            : int
customer_emails_detected    : int
invoice_statuses_detected   : sorted unique list of invoice statuses
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.workflows.scanners.base import BaseWorkflowScannerAdapter, ScanResult
from app.core.settings import get_settings

_CUSTOMERS_LIMIT = 50
_ARTICLES_LIMIT  = 50
_INVOICES_LIMIT  = 50


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------

def _build_fortnox_client(settings: Any):
    """Construct a FortnoxClient from app settings. Returns None if not configured."""
    from app.integrations.fortnox.client import FortnoxClient

    access_token  = getattr(settings, "FORTNOX_ACCESS_TOKEN", "") or ""
    client_secret = getattr(settings, "FORTNOX_CLIENT_SECRET", "") or ""
    api_url       = getattr(settings, "FORTNOX_API_URL", "https://api.fortnox.se/3") or "https://api.fortnox.se/3"

    if not access_token.strip() or not client_secret.strip():
        return None

    return FortnoxClient(
        access_token=access_token,
        client_secret=client_secret,
        api_url=api_url,
    )


# ---------------------------------------------------------------------------
# Pure analysis functions — no I/O, testable in isolation
# ---------------------------------------------------------------------------

def _normalise_customer(raw: dict) -> dict:
    return {
        "customer_number":   str(raw.get("CustomerNumber") or raw.get("customer_number") or ""),
        "name":              raw.get("Name") or raw.get("name") or "",
        "email":             raw.get("Email") or raw.get("email") or "",
        "organisation_number": raw.get("OrganisationNumber") or raw.get("organisation_number") or "",
        "phone":             raw.get("Phone1") or raw.get("phone") or "",
    }


def _normalise_article(raw: dict) -> dict:
    price = raw.get("SalesPrice") or raw.get("sales_price")
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        price = None
    return {
        "article_number": str(raw.get("ArticleNumber") or raw.get("article_number") or ""),
        "description":    raw.get("Description") or raw.get("description") or "",
        "unit":           raw.get("Unit") or raw.get("unit") or "",
        "sales_price":    price,
    }


def _normalise_invoice(raw: dict) -> dict:
    def _num(v):
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None
    return {
        "document_number": str(raw.get("DocumentNumber") or raw.get("document_number") or ""),
        "customer_number": str(raw.get("CustomerNumber") or raw.get("customer_number") or ""),
        "customer_name":   raw.get("CustomerName") or raw.get("customer_name") or "",
        "total":           _num(raw.get("Total") or raw.get("total")),
        "balance":         _num(raw.get("Balance") or raw.get("balance")),
        "status":          raw.get("DocumentStatus") or raw.get("status") or "",
        "due_date":        raw.get("DueDate") or raw.get("due_date") or None,
    }


def analyse_fortnox_data(
    raw_customers: list[dict],
    raw_articles: list[dict],
    raw_invoices: list[dict],
) -> tuple[dict, dict]:
    """
    Pure analysis function — no network or DB I/O.
    Returns (fortnox_system_map, fortnox_summary).
    Public so it can be tested and imported without the adapter.
    """
    customers = [_normalise_customer(c) for c in raw_customers]
    articles  = [_normalise_article(a)  for a in raw_articles]
    invoices  = [_normalise_invoice(i)  for i in raw_invoices]

    customer_emails = [c["email"] for c in customers if c["email"]]
    invoice_statuses = sorted({i["status"] for i in invoices if i["status"]})

    fortnox_map = {
        "customers": customers,
        "articles":  articles,
        "invoices":  invoices,
        "summary": {
            "customers_scanned":         len(customers),
            "articles_scanned":          len(articles),
            "invoices_scanned":          len(invoices),
            "customer_emails_detected":  len(customer_emails),
            "invoice_statuses_detected": invoice_statuses,
        },
    }

    fortnox_summary = {
        "customers_scanned":         len(customers),
        "articles_scanned":          len(articles),
        "invoices_scanned":          len(invoices),
        "customer_emails_detected":  len(customer_emails),
        "invoice_statuses_detected": invoice_statuses,
    }

    return fortnox_map, fortnox_summary


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class FortnoxWorkflowScannerAdapter(BaseWorkflowScannerAdapter):
    system_key = "fortnox"

    def run(self, db: Any, tenant_id: str) -> ScanResult:
        scanned_at = datetime.now(timezone.utc).isoformat()
        settings = get_settings()

        client = _build_fortnox_client(settings)
        if client is None:
            return ScanResult(
                system="fortnox",
                status="failed",
                scanned_at=scanned_at,
                error=(
                    "Fortnox credentials not configured "
                    "(FORTNOX_ACCESS_TOKEN and FORTNOX_CLIENT_SECRET are required)."
                ),
            )

        raw_customers = client.get_customers(limit=_CUSTOMERS_LIMIT)
        raw_articles  = client.get_articles(limit=_ARTICLES_LIMIT)
        raw_invoices  = client.get_invoices(limit=_INVOICES_LIMIT)

        fortnox_map, fortnox_summary = analyse_fortnox_data(
            raw_customers, raw_articles, raw_invoices
        )

        return ScanResult(
            system="fortnox",
            status="completed",
            scanned_at=scanned_at,
            data=fortnox_map,
            summary=fortnox_summary,
        )
