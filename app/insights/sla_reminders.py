"""
SLA reminder engine — deterministic, idempotent, scheduler-safe.

Identifies leads that have not received a response within the SLA window and
produces reminder records. Does NOT send customer-facing email directly —
reminders go through internal notification or approval-gated paths only.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

_DEFAULT_SLA_HOURS = 24
_ELIGIBLE_LEAD_STATUSES = {"new"}
_ELIGIBLE_JOB_STATUSES = {"pending", "processing", "awaiting_approval", "manual_review", "completed"}


def find_sla_breaches(
    db: Session,
    tenant_id: str,
    *,
    sla_hours: int | None = None,
) -> list[dict[str, Any]]:
    """Find leads that have breached or are about to breach SLA.

    Returns a list of breach records (read-only, no side effects).
    """
    now = datetime.now(timezone.utc)
    threshold = sla_hours if sla_hours is not None else _DEFAULT_SLA_HOURS
    cutoff = now - timedelta(hours=threshold)

    leads = (
        db.query(JobRecord)
        .filter(
            JobRecord.tenant_id == tenant_id,
            JobRecord.job_type == "lead",
            JobRecord.status.in_(list(_ELIGIBLE_JOB_STATUSES)),
            JobRecord.created_at < cutoff,
        )
        .order_by(JobRecord.created_at.asc())
        .limit(100)
        .all()
    )

    breaches: list[dict[str, Any]] = []
    for job in leads:
        inp = job.input_data or {}
        lead_status = inp.get("lead_status") or "new"
        if lead_status not in _ELIGIBLE_LEAD_STATUSES:
            continue

        created = _ensure_aware(job.created_at)
        if not created:
            continue

        hours_elapsed = (now - created).total_seconds() / 3600

        has_reply = _has_customer_reply(db, tenant_id, job.job_id)
        if has_reply:
            continue

        breaches.append({
            "job_id": job.job_id,
            "subject": inp.get("subject") or inp.get("latest_message_subject") or "Okänt ämne",
            "customer_name": _customer_name(inp),
            "customer_email": (inp.get("sender") or {}).get("email") or inp.get("sender_email"),
            "hours_elapsed": round(hours_elapsed, 1),
            "sla_hours": threshold,
            "breach_severity": "critical" if hours_elapsed > threshold * 2 else "high",
            "lead_status": lead_status,
            "created_at": job.created_at.isoformat() if job.created_at else None,
        })

    return breaches


def run_sla_reminder_pass(
    db: Session,
    tenant_id: str,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Run the SLA reminder pass for a tenant (called from scheduler).

    Idempotent: checks scheduler_state to avoid duplicate reminders per day.
    Does NOT send customer-facing email — only creates internal notification records.
    """
    scheduler_state = settings.get("scheduler_state") or {}
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    last_sla_run = scheduler_state.get("last_sla_reminder_at", "")
    if last_sla_run[:10] == today_str:
        return {"skipped": True, "reason": "already_run_today"}

    demo_mode = settings.get("control", {}).get("demo_mode", False)
    if demo_mode:
        return {"skipped": True, "reason": "demo_mode"}

    auto_actions = settings.get("auto_actions") or {}
    lead_auto = auto_actions.get("lead")
    if lead_auto is False or lead_auto == "disabled":
        return {"skipped": True, "reason": "lead_automation_disabled"}

    breaches = find_sla_breaches(db, tenant_id)

    result = {
        "skipped": False,
        "breaches_found": len(breaches),
        "reminders_created": 0,
        "checked_at": now.isoformat(),
    }

    for breach in breaches:
        _create_internal_reminder(db, tenant_id, breach, now)
        result["reminders_created"] += 1

    return result


def _create_internal_reminder(
    db: Session,
    tenant_id: str,
    breach: dict[str, Any],
    now: datetime,
) -> None:
    """Create an internal approval record as a reminder.

    Uses the existing approval_requests table with a 'sla_reminder' discriminator.
    The operator sees this in the approvals queue and can act on it.
    No customer-facing email is sent.
    """
    import uuid

    existing = (
        db.query(ApprovalRequestRecord)
        .filter(
            ApprovalRequestRecord.tenant_id == tenant_id,
            ApprovalRequestRecord.job_id == breach["job_id"],
            ApprovalRequestRecord.next_on_approve == "sla_reminder",
            ApprovalRequestRecord.state == "pending",
        )
        .first()
    )
    if existing:
        return

    record = ApprovalRequestRecord(
        approval_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        job_id=breach["job_id"],
        job_type="lead",
        state="pending",
        channel="system",
        title=f"SLA-påminnelse: {breach['subject']}",
        summary=(
            f"Lead har väntat {breach['hours_elapsed']:.0f} timmar utan svar. "
            f"Kund: {breach.get('customer_name') or 'okänd'}. "
            f"SLA-gräns: {breach['sla_hours']}h."
        ),
        requested_by="sla_engine",
        requested_at=now,
        next_on_approve="sla_reminder",
        request_payload={
            "breach": breach,
            "reminder_type": "sla_unanswered_lead",
        },
    )
    db.add(record)
    db.flush()


def _has_customer_reply(db: Session, tenant_id: str, job_id: str) -> bool:
    """Check if any email action has been executed for this job."""
    from app.repositories.postgres.action_execution_models import ActionExecutionRecord

    count = (
        db.query(func.count(ActionExecutionRecord.execution_id))
        .filter(
            ActionExecutionRecord.tenant_id == tenant_id,
            ActionExecutionRecord.job_id == job_id,
            ActionExecutionRecord.action_type.in_(["send_email", "send_customer_auto_reply"]),
        )
        .scalar() or 0
    )
    return count > 0


def _customer_name(inp: dict) -> str | None:
    sender = inp.get("sender") or {}
    return sender.get("name") or inp.get("sender_name")


def _ensure_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
