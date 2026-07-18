from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.job_models import JobRecord

from .models import OperationLine, OperationReport, RowAction, StaleDataType


def prune_stale_data(
    db: Session,
    *,
    tenant_id: str,
    data_type: StaleDataType,
    older_than_days: int,
    dry_run: bool,
) -> OperationReport:
    if older_than_days < 1:
        raise ValueError("--older-than-days must be at least 1")

    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    report = OperationReport(command="prune-stale-data", dry_run=dry_run)
    normalized_tenant = tenant_id.strip()
    if not normalized_tenant:
        raise ValueError("--tenant-id is required for prune-stale-data")

    if data_type == StaleDataType.PENDING_APPROVALS:
        query = db.query(ApprovalRequestRecord).filter(
            ApprovalRequestRecord.tenant_id == normalized_tenant,
            ApprovalRequestRecord.state == "pending",
            ApprovalRequestRecord.created_at < cutoff,
        )
        count = query.count()
        if count:
            if not dry_run:
                query.delete(synchronize_session=False)
                db.commit()
            report.lines.append(
                OperationLine(
                    table="approval_requests",
                    tenant_id=normalized_tenant,
                    rows=count,
                    action=RowAction.DELETE,
                    note=f"pending approvals older than {older_than_days}d",
                )
            )
        return report

    if data_type == StaleDataType.STUCK_JOBS:
        query = db.query(JobRecord).filter(
            JobRecord.tenant_id == normalized_tenant,
            JobRecord.status.in_(("pending", "processing")),
            JobRecord.updated_at < cutoff,
        )
        count = query.count()
        if count:
            if not dry_run:
                query.delete(synchronize_session=False)
                db.commit()
            report.lines.append(
                OperationLine(
                    table="jobs",
                    tenant_id=normalized_tenant,
                    rows=count,
                    action=RowAction.DELETE,
                    note=f"stuck jobs older than {older_than_days}d",
                )
            )
        return report

    if data_type == StaleDataType.DEMO_SEED_JOBS:
        candidates = (
            db.query(JobRecord)
            .filter(JobRecord.tenant_id == normalized_tenant)
            .all()
        )
        to_delete = []
        for job in candidates:
            input_data = job.input_data or {}
            if input_data.get("demo_seed") is True:
                to_delete.append(job.job_id)
                continue
            source = input_data.get("source") or {}
            if isinstance(source, dict) and source.get("system") == "demo_seed":
                to_delete.append(job.job_id)

        if to_delete:
            if not dry_run:
                (
                    db.query(JobRecord)
                    .filter(
                        JobRecord.tenant_id == normalized_tenant,
                        JobRecord.job_id.in_(to_delete),
                    )
                    .delete(synchronize_session=False)
                )
                db.commit()
            report.lines.append(
                OperationLine(
                    table="jobs",
                    tenant_id=normalized_tenant,
                    rows=len(to_delete),
                    action=RowAction.DELETE,
                    note="demo_seed flagged jobs",
                )
            )
        return report

    raise ValueError(f"Unsupported data type: {data_type}")
