"""Daily Report Generator.

Produces a structured morning summary for a tenant covering the last N hours.
Pure service function — callable from a FastAPI endpoint, a script, or a test.
No scheduler plumbing required.

Usage:
    from app.reporting.daily_report import generate_daily_report
    report = generate_daily_report(db, tenant_id="TENANT_1001", since_hours=24)
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.repositories.postgres.job_repository import JobRepository
from app.repositories.postgres.approval_repository import ApprovalRequestRepository
from app.domain.workflows.models import Job
from app.domain.workflows.statuses import JobStatus
from app.workflows.derived_status import derive_job_status
from app.workflows.processors.ai_processor_utils import get_latest_processor_payload
from app.workflows.manual_review_handoff import is_unresolved_manual_review
from app.workflows.email_approval_resolution import count_internal_handoffs_sent_since


def generate_daily_report(
    db: Session,
    tenant_id: str,
    since_hours: int = 24,
) -> dict:
    """Generate a daily summary report for a tenant.

    Fetches recent jobs, derives statuses, counts categories, and builds
    a rendered text report. Read-only — no side effects.

    Returns:
        dict with keys: tenant_id, period_hours, generated_at,
                        counts, top_priorities, rendered_text
    """
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=since_hours)

    # Fetch recent jobs — high limit, filter by created_at in Python
    # (avoids adding a new DB query method; reasonable for tenant-scale data)
    all_jobs = JobRepository.list_jobs(db, tenant_id=tenant_id, limit=500, offset=0)
    recent_jobs: list[Job] = [j for j in all_jobs if j.created_at >= cutoff]

    # Count pending approvals
    pending_approvals = ApprovalRequestRepository.count_pending_for_tenant(db, tenant_id)

    unresolved_manual_review = sum(
        1
        for j in recent_jobs
        if is_unresolved_manual_review(j)
    )

    internal_handoffs_sent = count_internal_handoffs_sent_since(
        db=db,
        tenant_id=tenant_id,
        since=cutoff,
    )

    # Categorise each job
    counts = {
        "new_leads": 0,
        "leads_ready_for_quote": 0,
        "leads_waiting_for_customer": 0,
        "inquiries_needing_response": 0,
        "invoice_items_needing_action": 0,
        "risk_review_required": 0,
        "pending_approvals": pending_approvals,
        "unresolved_manual_review": unresolved_manual_review,
        "internal_handoffs_sent": internal_handoffs_sent,
    }

    priority_items: list[dict[str, Any]] = []

    for job in recent_jobs:
        ds = derive_job_status(job)
        derived = ds["derived_status"]
        job_type_val = job.job_type.value if hasattr(job.job_type, "value") else str(job.job_type)

        if derived == "risk_review_required":
            counts["risk_review_required"] += 1
            priority_items.append(_priority_item(job, ds, "risk_review"))

        elif derived == "quote_draft_prepared":
            counts["leads_ready_for_quote"] += 1
            priority_items.append(_priority_item(job, ds, "approve_quote"))

        elif derived == "ready_for_quote":
            counts["leads_ready_for_quote"] += 1

        elif derived == "waiting_for_customer":
            counts["leads_waiting_for_customer"] += 1

        elif derived == "invoice_routing_needed":
            counts["invoice_items_needing_action"] += 1
            priority_items.append(_priority_item(job, ds, "invoice_review"))

        elif derived == "waiting_for_internal_review":
            # Could be an inquiry awaiting approval
            if "inquiry" in job_type_val or "customer" in job_type_val:
                counts["inquiries_needing_response"] += 1
            elif "lead" in job_type_val:
                counts["new_leads"] += 1

        else:
            # New / fresh leads
            if "lead" in job_type_val and job.status in (
                JobStatus.COMPLETED, JobStatus.AWAITING_APPROVAL
            ):
                counts["new_leads"] += 1
            elif "inquiry" in job_type_val and job.status == JobStatus.AWAITING_APPROVAL:
                counts["inquiries_needing_response"] += 1

    # Sort priorities: risk first, then quotes, then invoices
    _PRIORITY_ORDER = {"risk_review": 0, "approve_quote": 1, "invoice_review": 2}
    priority_items.sort(key=lambda x: _PRIORITY_ORDER.get(x.get("action_type", ""), 99))
    top_priorities = priority_items[:5]

    rendered = _render_text(counts, top_priorities, since_hours)

    return {
        "tenant_id": tenant_id,
        "period_hours": since_hours,
        "generated_at": now.isoformat(),
        "counts": counts,
        "top_priorities": top_priorities,
        "rendered_text": rendered,
    }


def _priority_item(job: Job, ds: dict, action_type: str) -> dict:
    """Build a priority item dict from a job and its derived status."""
    lead_payload = get_latest_processor_payload(job, "lead_analyzer_processor")
    invoice_payload = get_latest_processor_payload(job, "invoice_processor")

    # Customer name from lead analyzer or entity extraction
    entity_payload = get_latest_processor_payload(job, "entity_extraction_processor")
    entities = entity_payload.get("entities") or {}
    customer = (
        entities.get("customer_name")
        or entities.get("company_name")
        or (job.input_data or {}).get("sender", {}).get("name")
        or "okänd kund"
    )

    service = lead_payload.get("service_profile_type") or "okänd tjänst"
    invoice_routing = ds.get("invoice_routing")
    supplier = (invoice_payload.get("invoice_data") or {}).get("supplier_name")

    label = _action_label(action_type, customer, service, invoice_routing, supplier)

    return {
        "job_id": job.job_id,
        "action_type": action_type,
        "label": label,
        "derived_status": ds["derived_status"],
        "customer": customer,
        "service": service if action_type != "invoice_review" else None,
        "invoice_routing": invoice_routing,
    }


def _action_label(
    action_type: str,
    customer: str,
    service: str,
    invoice_routing: str | None,
    supplier: str | None,
) -> str:
    if action_type == "risk_review":
        return f"Granska riskärende för {customer}"
    if action_type == "approve_quote":
        return f"Granska offertunderlag för {customer} ({service.replace('_', ' ')})"
    if action_type == "invoice_review":
        src = supplier or "okänd leverantör"
        route_label = {
            "debt_collection_review": "inkasso/krav",
            "payment_reminder_review": "påminnelse",
            "manual_review_required": "manuell granskning",
        }.get(invoice_routing or "", "granskning")
        return f"Granska faktura/brev från {src} — {route_label}"
    return f"Åtgärd krävs för {customer}"


def _render_text(counts: dict, priorities: list[dict], since_hours: int) -> str:
    period_label = "sedan igår" if since_hours == 24 else f"de senaste {since_hours} timmarna"

    lines = [
        "God morgon.",
        "",
        f"Krowolf hittade {period_label}:",
        "",
    ]

    def bullet(label: str, count: int) -> str:
        return f"* {count} {label}"

    if counts["new_leads"]:
        lines.append(bullet("nya leads", counts["new_leads"]))
    if counts["leads_ready_for_quote"]:
        lines.append(bullet("leads redo för offert", counts["leads_ready_for_quote"]))
    if counts["leads_waiting_for_customer"]:
        lines.append(bullet("leads som väntar på kundinformation", counts["leads_waiting_for_customer"]))
    if counts["inquiries_needing_response"]:
        lines.append(bullet("kundärenden som behöver svar", counts["inquiries_needing_response"]))
    if counts["invoice_items_needing_action"]:
        lines.append(bullet("faktura/betalningsärenden som kräver åtgärd", counts["invoice_items_needing_action"]))
    if counts["risk_review_required"]:
        lines.append(bullet("högriskärenden", counts["risk_review_required"]))
    if counts["pending_approvals"]:
        lines.append(bullet("väntande godkännanden", counts["pending_approvals"]))
    if counts.get("unresolved_manual_review"):
        lines.append(
            bullet("ärenden i manuell granskning (ej lösta)", counts["unresolved_manual_review"])
        )
    if counts.get("internal_handoffs_sent"):
        lines.append(
            bullet("interna handoffs skickade", counts["internal_handoffs_sent"])
        )

    if not any(v for v in counts.values() if isinstance(v, int) and v > 0):
        lines.append("* Inga nya ärenden")

    if priorities:
        lines.extend(["", "Viktigast idag:", ""])
        for i, p in enumerate(priorities, 1):
            lines.append(f"{i}. {p['label']}")

    return "\n".join(lines)
