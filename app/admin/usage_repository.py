"""Batched read-only queries for usage/cost/capacity aggregation (Kapitel 7)."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.admin.incident_models import IncidentRecord
from app.admin.tenant_directory import _batch_count_by_tenant, _batch_max_created_at
from app.domain.integrations.models import IntegrationEvent
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.job_models import JobRecord


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def compute_period_bounds(
    days: int,
    *,
    now: datetime | None = None,
) -> dict[str, datetime | int]:
    """Half-open UTC intervals: current [now-days, now), comparison [now-2*days, now-days)."""
    anchor = now if now is not None else _utcnow()
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    current_start = anchor - timedelta(days=days)
    comparison_start = anchor - timedelta(days=2 * days)
    return {
        "days": days,
        "started_at": current_start,
        "ended_at": anchor,
        "comparison_started_at": comparison_start,
        "comparison_ended_at": current_start,
    }


def _half_open(column: Any, start: datetime, end: datetime) -> Any:
    return and_(column >= start, column < end)


def batch_jobs_received_by_tenant(
    db: Session,
    *,
    start: datetime,
    end: datetime,
) -> dict[str, int]:
    query = (
        db.query(JobRecord.tenant_id, func.count())
        .filter(_half_open(JobRecord.created_at, start, end))
        .group_by(JobRecord.tenant_id)
    )
    return {tenant_id: count for tenant_id, count in query.all()}


def batch_jobs_terminal_by_tenant(
    db: Session,
    *,
    status: str,
    start: datetime,
    end: datetime,
) -> dict[str, int]:
    query = (
        db.query(JobRecord.tenant_id, func.count())
        .filter(
            JobRecord.status == status,
            _half_open(JobRecord.updated_at, start, end),
        )
        .group_by(JobRecord.tenant_id)
    )
    return {tenant_id: count for tenant_id, count in query.all()}


def batch_audit_by_tenant(
    db: Session,
    *,
    category: str,
    start: datetime,
    end: datetime,
    action: str | None = None,
) -> dict[str, int]:
    filters = [
        AuditEventRecord.category == category,
        _half_open(AuditEventRecord.created_at, start, end),
    ]
    if action is not None:
        filters.append(AuditEventRecord.action == action)
    query = (
        db.query(AuditEventRecord.tenant_id, func.count())
        .filter(*filters)
        .group_by(AuditEventRecord.tenant_id)
    )
    return {tenant_id: count for tenant_id, count in query.all()}


def batch_incidents_created_by_tenant(
    db: Session,
    *,
    start: datetime,
    end: datetime,
) -> dict[str, int]:
    from app.admin.incident_models import IncidentTenantRecord

    result = (
        db.query(
            IncidentTenantRecord.tenant_id,
            func.count(func.distinct(IncidentRecord.incident_id)),
        )
        .join(
            IncidentRecord,
            IncidentRecord.incident_id == IncidentTenantRecord.incident_id,
        )
        .filter(
            IncidentTenantRecord.unlinked_at.is_(None),
            _half_open(IncidentRecord.created_at, start, end),
        )
        .group_by(IncidentTenantRecord.tenant_id)
    )
    return {tenant_id: count for tenant_id, count in result.all()}


def count_incidents_created_global(
    db: Session,
    *,
    start: datetime,
    end: datetime,
) -> int:
    return (
        db.query(func.count())
        .select_from(IncidentRecord)
        .filter(_half_open(IncidentRecord.created_at, start, end))
        .scalar()
        or 0
    )


def count_incidents_resolved_global(
    db: Session,
    *,
    start: datetime,
    end: datetime,
) -> int:
    return (
        db.query(func.count())
        .select_from(IncidentRecord)
        .filter(
            IncidentRecord.resolved_at.isnot(None),
            _half_open(IncidentRecord.resolved_at, start, end),
        )
        .scalar()
        or 0
    )


def count_critical_incidents_created_global(
    db: Session,
    *,
    start: datetime,
    end: datetime,
) -> int:
    return (
        db.query(func.count())
        .select_from(IncidentRecord)
        .filter(
            IncidentRecord.severity == "critical",
            _half_open(IncidentRecord.created_at, start, end),
        )
        .scalar()
        or 0
    )


def batch_incidents_resolved_by_tenant(
    db: Session,
    *,
    start: datetime,
    end: datetime,
) -> dict[str, int]:
    from app.admin.incident_models import IncidentTenantRecord

    result = (
        db.query(IncidentTenantRecord.tenant_id, func.count(func.distinct(IncidentRecord.incident_id)))
        .join(
            IncidentRecord,
            IncidentRecord.incident_id == IncidentTenantRecord.incident_id,
        )
        .filter(
            IncidentTenantRecord.unlinked_at.is_(None),
            IncidentRecord.resolved_at.isnot(None),
            _half_open(IncidentRecord.resolved_at, start, end),
        )
        .group_by(IncidentTenantRecord.tenant_id)
    )
    return {tenant_id: count for tenant_id, count in result.all()}


def batch_critical_incidents_by_tenant(
    db: Session,
    *,
    start: datetime,
    end: datetime,
) -> dict[str, int]:
    from app.admin.incident_models import IncidentTenantRecord

    result = (
        db.query(IncidentTenantRecord.tenant_id, func.count(func.distinct(IncidentRecord.incident_id)))
        .join(
            IncidentRecord,
            IncidentRecord.incident_id == IncidentTenantRecord.incident_id,
        )
        .filter(
            IncidentTenantRecord.unlinked_at.is_(None),
            IncidentRecord.severity == "critical",
            _half_open(IncidentRecord.created_at, start, end),
        )
        .group_by(IncidentTenantRecord.tenant_id)
    )
    return {tenant_id: count for tenant_id, count in result.all()}


def batch_integration_errors_by_tenant(
    db: Session,
    *,
    start: datetime,
    end: datetime,
) -> dict[str, int]:
    query = (
        db.query(IntegrationEvent.tenant_id, func.count())
        .filter(
            IntegrationEvent.status == "failed",
            _half_open(IntegrationEvent.created_at, start, end),
        )
        .group_by(IntegrationEvent.tenant_id)
    )
    return {tenant_id: count for tenant_id, count in query.all()}


def count_global_from_batch(batch: dict[str, int]) -> int:
    return sum(batch.values())


def sum_jobs_received_global(
    db: Session,
    *,
    start: datetime,
    end: datetime,
) -> int:
    return (
        db.query(func.count())
        .select_from(JobRecord)
        .filter(_half_open(JobRecord.created_at, start, end))
        .scalar()
        or 0
    )


def sum_jobs_terminal_global(
    db: Session,
    *,
    status: str,
    start: datetime,
    end: datetime,
) -> int:
    return (
        db.query(func.count())
        .select_from(JobRecord)
        .filter(
            JobRecord.status == status,
            _half_open(JobRecord.updated_at, start, end),
        )
        .scalar()
        or 0
    )


def sum_audit_global(
    db: Session,
    *,
    category: str,
    start: datetime,
    end: datetime,
    action: str | None = None,
) -> int:
    filters = [
        AuditEventRecord.category == category,
        _half_open(AuditEventRecord.created_at, start, end),
    ]
    if action is not None:
        filters.append(AuditEventRecord.action == action)
    return (
        db.query(func.count())
        .select_from(AuditEventRecord)
        .filter(*filters)
        .scalar()
        or 0
    )


def sum_integration_errors_global(
    db: Session,
    *,
    start: datetime,
    end: datetime,
) -> int:
    return (
        db.query(func.count())
        .select_from(IntegrationEvent)
        .filter(
            IntegrationEvent.status == "failed",
            _half_open(IntegrationEvent.created_at, start, end),
        )
        .scalar()
        or 0
    )


def compute_peak_jobs_per_hour(
    db: Session,
    *,
    start: datetime,
    end: datetime,
) -> int:
    """Dialect-neutral peak hour bucket via Python (SQLite + Postgres safe)."""
    rows = (
        db.query(JobRecord.created_at)
        .filter(_half_open(JobRecord.created_at, start, end))
        .all()
    )
    if not rows:
        return 0
    buckets: Counter[datetime] = Counter()
    for (created_at,) in rows:
        if created_at is None:
            continue
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        hour_key = created_at.replace(minute=0, second=0, microsecond=0)
        buckets[hour_key] += 1
    return max(buckets.values()) if buckets else 0


def batch_pending_approvals_by_tenant(db: Session) -> dict[str, int]:
    return _batch_count_by_tenant(
        db,
        ApprovalRequestRecord,
        extra_filter=ApprovalRequestRecord.state == "pending",
    )


def batch_open_manual_reviews_by_tenant(db: Session) -> dict[str, int]:
    return _batch_count_by_tenant(
        db,
        JobRecord,
        extra_filter=JobRecord.status == "manual_review",
    )


def batch_latest_activity_by_tenant(db: Session) -> dict[str, datetime]:
    job_activity = (
        db.query(
            JobRecord.tenant_id,
            func.max(JobRecord.updated_at),
        )
        .group_by(JobRecord.tenant_id)
        .all()
    )
    job_map = {tenant_id: ts for tenant_id, ts in job_activity if ts}
    approval_map = _batch_max_created_at(db, ApprovalRequestRecord)
    audit_map = _batch_max_created_at(db, AuditEventRecord)
    integration_map = _batch_max_created_at(db, IntegrationEvent)

    tenants = set(job_map) | set(approval_map) | set(audit_map) | set(integration_map)
    result: dict[str, datetime] = {}
    for tenant_id in tenants:
        candidates = [
            job_map.get(tenant_id),
            approval_map.get(tenant_id),
            audit_map.get(tenant_id),
            integration_map.get(tenant_id),
        ]
        valid = [ts for ts in candidates if ts is not None]
        if valid:
            result[tenant_id] = max(valid)
    return result


def tenants_with_jobs_in_period(
    db: Session,
    *,
    start: datetime,
    end: datetime,
) -> set[str]:
    rows = (
        db.query(JobRecord.tenant_id)
        .filter(_half_open(JobRecord.created_at, start, end))
        .distinct()
        .all()
    )
    return {tenant_id for (tenant_id,) in rows}
