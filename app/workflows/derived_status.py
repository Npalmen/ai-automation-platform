"""Derived status helper.

Reads from job.processor_history to return a human-readable derived status
that is richer than the raw JobStatus enum. Used by the daily report and
the MVP gate verifier. Pure function — no DB or side effects.

Derived status values:
    waiting_for_customer       — questions sent, awaiting customer reply
    waiting_for_internal_review — job in approval queue (no offer draft)
    ready_for_quote            — lead scored high, quote workflow started
    quote_draft_prepared       — offer_draft present in processor history
    invoice_routing_needed     — invoice requires accounting/review action
    risk_review_required       — manual_review status or risk detected
    completed                  — job completed with no active action needed
    unknown                    — cannot determine from available history
"""
from __future__ import annotations

from app.domain.workflows.models import Job
from app.domain.workflows.statuses import JobStatus
from app.workflows.processors.ai_processor_utils import get_latest_processor_payload


def derive_job_status(job: Job) -> dict:
    """Return derived status context for a job.

    Returns:
        derived_status    : str  — one of the labels above
        lead_status       : str | None — lead_status from lead_analyzer if present
        invoice_routing   : str | None — invoice_routing from invoice_processor if present
        offer_draft_present : bool — True if offer_draft exists in lead_analyzer payload
        next_action       : str | None — next_action from lead_analyzer if present
    """
    lead_payload = get_latest_processor_payload(job, "lead_analyzer_processor")
    invoice_payload = get_latest_processor_payload(job, "invoice_processor")
    policy_payload = get_latest_processor_payload(job, "policy_processor")

    lead_status: str | None = lead_payload.get("lead_status")
    next_action: str | None = lead_payload.get("next_action")
    offer_draft_present: bool = bool(lead_payload.get("offer_draft"))
    invoice_routing: str | None = invoice_payload.get("invoice_routing")
    risk = (policy_payload.get("risk") or {}).get("risk_detected", False)

    # 1. Manual review / risk
    if job.status == JobStatus.MANUAL_REVIEW or risk:
        return _result(
            "risk_review_required",
            lead_status=lead_status,
            invoice_routing=invoice_routing,
            offer_draft_present=offer_draft_present,
            next_action=next_action,
        )

    # 2. Lead path — offer draft produced
    if offer_draft_present:
        return _result(
            "quote_draft_prepared",
            lead_status=lead_status,
            invoice_routing=invoice_routing,
            offer_draft_present=True,
            next_action=next_action,
        )

    # 3. Lead path — questions asked, waiting for customer
    if next_action == "ask_questions" or lead_status == "waiting_for_customer":
        return _result(
            "waiting_for_customer",
            lead_status=lead_status,
            invoice_routing=invoice_routing,
            offer_draft_present=False,
            next_action=next_action,
        )

    # 4. Lead path — scored ready but draft not yet built (ready_to_dispatch)
    if next_action == "ready_to_dispatch" or lead_status in ("offer_ready", "quote_draft_prepared"):
        return _result(
            "ready_for_quote",
            lead_status=lead_status,
            invoice_routing=invoice_routing,
            offer_draft_present=offer_draft_present,
            next_action=next_action,
        )

    # 5. Invoice routing needed (not clean forwarding)
    if invoice_routing and invoice_routing != "forward_to_accounting":
        return _result(
            "invoice_routing_needed",
            lead_status=lead_status,
            invoice_routing=invoice_routing,
            offer_draft_present=False,
            next_action=next_action,
        )

    # 6. Awaiting approval without offer draft
    if job.status == JobStatus.AWAITING_APPROVAL:
        return _result(
            "waiting_for_internal_review",
            lead_status=lead_status,
            invoice_routing=invoice_routing,
            offer_draft_present=False,
            next_action=next_action,
        )

    # 7. Completed
    if job.status == JobStatus.COMPLETED:
        return _result(
            "completed",
            lead_status=lead_status,
            invoice_routing=invoice_routing,
            offer_draft_present=offer_draft_present,
            next_action=next_action,
        )

    return _result(
        "unknown",
        lead_status=lead_status,
        invoice_routing=invoice_routing,
        offer_draft_present=offer_draft_present,
        next_action=next_action,
    )


def _result(
    derived_status: str,
    lead_status: str | None,
    invoice_routing: str | None,
    offer_draft_present: bool,
    next_action: str | None,
) -> dict:
    return {
        "derived_status": derived_status,
        "lead_status": lead_status,
        "invoice_routing": invoice_routing,
        "offer_draft_present": offer_draft_present,
        "next_action": next_action,
    }
