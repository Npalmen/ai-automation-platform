"""
Ready-to-market usage analytics.

Read-only aggregation for pilot operators and super admins. The service uses
existing persisted jobs, approvals, integration events, and tenant config rows.
No external APIs are called and no secrets are returned.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.domain.integrations.models import IntegrationEvent
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
from app.workflows.dispatchers.observability import MINUTES_SAVED_PER_SUCCESS

_VALID_RANGES = {"today", "7d", "30d", "all"}
_BLOCKED_JOB_STATUSES = {"awaiting_approval", "manual_review", "failed"}
_AUTOMATED_DISPATCH_MODES = {"approval_required", "full_auto"}
_DISPATCH_TYPE = "controlled_dispatch"


def _normalise_range(range_: str | None) -> str:
    if range_ in _VALID_RANGES:
        return str(range_)
    return "30d"


def _range_bounds(range_: str) -> tuple[datetime | None, datetime]:
    now = datetime.now(timezone.utc)
    if range_ == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0), now
    if range_ == "7d":
        return now - timedelta(days=7), now
    if range_ == "30d":
        return now - timedelta(days=30), now
    return None, now


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _in_range(value: datetime | None, from_dt: datetime | None, to_dt: datetime) -> bool:
    timestamp = _as_aware(value)
    if timestamp is None:
        return False
    if from_dt is not None and timestamp < from_dt:
        return False
    return timestamp <= to_dt


def _payload(record: Any) -> dict[str, Any]:
    payload = getattr(record, "payload", None) or {}
    return payload if isinstance(payload, dict) else {}


def _fetch_records(
    db: Session,
    model: Any,
    tenant_id: str,
    from_dt: datetime | None,
    to_dt: datetime,
) -> list[Any]:
    """Fetch tenant records and defensively filter in Python for easy testability."""
    query = db.query(model).filter(model.tenant_id == tenant_id)
    if from_dt is not None:
        query = query.filter(model.created_at >= from_dt)
    records = query.all()
    return [
        record for record in records
        if getattr(record, "tenant_id", None) == tenant_id
        and _in_range(getattr(record, "created_at", None), from_dt, to_dt)
    ]


def _status(value: Any) -> str:
    return str(value or "unknown").lower()


def _tenant_status(record: Any) -> str:
    value = getattr(record, "status", "active")
    if not isinstance(value, str):
        return "active"
    return value or "active"


def _tenant_usage_summary(
    db: Session,
    record: Any,
    from_dt: datetime | None,
    to_dt: datetime,
) -> dict[str, Any]:
    tenant_id = record.tenant_id
    jobs = _fetch_records(db, JobRecord, tenant_id, from_dt, to_dt)
    approvals = _fetch_records(db, ApprovalRequestRecord, tenant_id, from_dt, to_dt)
    events = _fetch_records(db, IntegrationEvent, tenant_id, from_dt, to_dt)
    dispatch_events = [e for e in events if getattr(e, "integration_type", None) == _DISPATCH_TYPE]

    jobs_by_type: dict[str, int] = {}
    jobs_by_status: dict[str, int] = {}
    blocked_job_ids: set[str] = set()

    for job in jobs:
        job_type = str(getattr(job, "job_type", None) or "unknown")
        job_status = _status(getattr(job, "status", None))
        jobs_by_type[job_type] = jobs_by_type.get(job_type, 0) + 1
        jobs_by_status[job_status] = jobs_by_status.get(job_status, 0) + 1
        if job_status in _BLOCKED_JOB_STATUSES:
            blocked_job_ids.add(str(getattr(job, "job_id", "")))

    pending_approvals = 0
    for approval in approvals:
        if _status(getattr(approval, "state", None)) == "pending":
            pending_approvals += 1
            job_id = getattr(approval, "job_id", None)
            if job_id:
                blocked_job_ids.add(str(job_id))

    dispatch_total = len(dispatch_events)
    dispatch_success = sum(1 for e in dispatch_events if _status(getattr(e, "status", None)) == "success")
    dispatch_failed = sum(1 for e in dispatch_events if _status(getattr(e, "status", None)) == "failed")
    dispatch_skipped = sum(1 for e in dispatch_events if _status(getattr(e, "status", None)) == "skipped")

    automated = 0
    for event in dispatch_events:
        mode = _payload(event).get("dispatch_mode")
        if mode in _AUTOMATED_DISPATCH_MODES:
            automated += 1

    actionable = dispatch_total - dispatch_skipped
    automation_rate = round(automated / actionable * 100) if actionable else 0
    time_saved_hours = round(dispatch_success * MINUTES_SAVED_PER_SUCCESS / 60, 2)

    return {
        "tenant_id": tenant_id,
        "name": getattr(record, "name", None) or tenant_id,
        "status": _tenant_status(record),
        "active_in_range": bool(jobs or approvals or events),
        "jobs_created": len(jobs),
        "jobs_completed": jobs_by_status.get("completed", 0),
        "jobs_by_type": jobs_by_type,
        "jobs_by_status": jobs_by_status,
        "pending_approvals": pending_approvals,
        "blocked_flows": len(blocked_job_ids),
        "dispatches_total": dispatch_total,
        "dispatches_successful": dispatch_success,
        "dispatches_failed": dispatch_failed,
        "dispatches_skipped": dispatch_skipped,
        "dispatches_automated": automated,
        "automation_rate_percent": automation_rate,
        "time_saved_hours": time_saved_hours,
    }


def get_usage_analytics(
    db: Session,
    *,
    range_: str | None = None,
) -> dict[str, Any]:
    """
    Build admin-level usage analytics across all DB tenants.

    Returns aggregate pilot metrics plus per-tenant rows. This is intended for
    super-admin/pilot tooling and should be exposed only behind admin auth.
    """
    range_ = _normalise_range(range_)
    from_dt, to_dt = _range_bounds(range_)
    tenants = TenantConfigRepository.list_all(db)

    tenant_rows = [
        _tenant_usage_summary(db, tenant, from_dt, to_dt)
        for tenant in tenants
    ]

    active_tenants = sum(1 for row in tenant_rows if row["active_in_range"])
    active_customer_count = sum(1 for t in tenants if _tenant_status(t) == "active")
    total_jobs = sum(row["jobs_created"] for row in tenant_rows)
    completed_jobs = sum(row["jobs_completed"] for row in tenant_rows)
    blocked_flows = sum(row["blocked_flows"] for row in tenant_rows)
    pending_approvals = sum(row["pending_approvals"] for row in tenant_rows)
    dispatch_total = sum(row["dispatches_total"] for row in tenant_rows)
    dispatch_success = sum(row["dispatches_successful"] for row in tenant_rows)
    dispatch_failed = sum(row["dispatches_failed"] for row in tenant_rows)
    dispatch_skipped = sum(row["dispatches_skipped"] for row in tenant_rows)
    dispatch_automated = sum(row["dispatches_automated"] for row in tenant_rows)
    time_saved_hours = round(sum(row["time_saved_hours"] for row in tenant_rows), 2)

    actionable = dispatch_total - dispatch_skipped
    automation_rate = round(dispatch_automated / actionable * 100) if actionable else 0

    top_blocked = sorted(
        [
            {
                "tenant_id": row["tenant_id"],
                "name": row["name"],
                "blocked_flows": row["blocked_flows"],
                "pending_approvals": row["pending_approvals"],
            }
            for row in tenant_rows
            if row["blocked_flows"] > 0
        ],
        key=lambda item: item["blocked_flows"],
        reverse=True,
    )[:10]

    return {
        "range": range_,
        "from": from_dt.isoformat() if from_dt else None,
        "to": to_dt.isoformat(),
        "summary": {
            "tenant_count": len(tenants),
            "active_customer_count": active_customer_count,
            "active_tenants_in_range": active_tenants,
            "jobs_created": total_jobs,
            "jobs_completed": completed_jobs,
            "blocked_flows": blocked_flows,
            "pending_approvals": pending_approvals,
            "dispatches_total": dispatch_total,
            "dispatches_successful": dispatch_success,
            "dispatches_failed": dispatch_failed,
            "dispatches_skipped": dispatch_skipped,
            "automation_rate_percent": automation_rate,
            "time_saved_hours": time_saved_hours,
        },
        "tenants": tenant_rows,
        "top_blocked_tenants": top_blocked,
    }
