from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.domain.workflows.statuses import JobStatus
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.job_repository import JobRepository
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

from .models import OperationLine, OperationReport, RowAction
from .reserved_tenants import BASELINE_TENANT_ID, BASELINE_TENANT_NAME


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def seed_baseline(db: Session, *, dry_run: bool) -> OperationReport:
    report = OperationReport(command="seed-baseline", dry_run=dry_run)
    tenant_id = BASELINE_TENANT_ID

    if dry_run:
        exists = TenantConfigRepository.get(db, tenant_id) is not None
        report.lines.append(
            OperationLine(
                table="tenant_configs",
                tenant_id=tenant_id,
                rows=0 if exists else 1,
                action=RowAction.SKIP,
                note="would upsert baseline tenant config",
            )
        )
        report.lines.append(
            OperationLine(
                table="jobs",
                tenant_id=tenant_id,
                rows=2,
                action=RowAction.SKIP,
                note="would ensure two fresh baseline jobs",
            )
        )
        report.lines.append(
            OperationLine(
                table="approval_requests",
                tenant_id=tenant_id,
                rows=1,
                action=RowAction.SKIP,
                note="would ensure one pending approval",
            )
        )
        return report

    TenantConfigRepository.upsert(
        db,
        tenant_id=tenant_id,
        name=BASELINE_TENANT_NAME,
        slug="local-ops-baseline",
        status="active",
        enabled_job_types=["lead", "customer_inquiry"],
        allowed_integrations=["google_mail"],
        auto_actions={"lead": "manual", "customer_inquiry": "manual"},
    )
    TenantConfigRepository.update_settings(
        db,
        tenant_id,
        {
            "scheduler": {"run_mode": "manual"},
            "branding": {"company_name": BASELINE_TENANT_NAME},
        },
    )
    report.lines.append(
        OperationLine(
            table="tenant_configs",
            tenant_id=tenant_id,
            rows=1,
            action=RowAction.SKIP,
            note="baseline tenant upserted",
        )
    )

    now = _utcnow()
    existing_jobs = db.query(JobRecord).filter(JobRecord.tenant_id == tenant_id).count()

    if existing_jobs < 2:
        for index, status in enumerate((JobStatus.COMPLETED, JobStatus.PENDING)):
            job = Job(
                job_id=f"baseline-job-{index + 1}-{uuid.uuid4().hex[:8]}",
                tenant_id=tenant_id,
                job_type=JobType.LEAD,
                status=status,
                input_data={
                    "demo_seed": True,
                    "source": {"system": "baseline_seed"},
                    "subject": f"Baseline test job {index + 1}",
                },
                result={"summary": "Baseline seed"},
                created_at=now,
                updated_at=now,
            )
            JobRepository.create_job(db, job)
        report.lines.append(
            OperationLine(
                table="jobs",
                tenant_id=tenant_id,
                rows=2,
                action=RowAction.SKIP,
                note="baseline jobs created",
            )
        )

    pending_exists = (
        db.query(ApprovalRequestRecord)
        .filter(
            ApprovalRequestRecord.tenant_id == tenant_id,
            ApprovalRequestRecord.state == "pending",
        )
        .count()
    )
    if pending_exists == 0:
        first_job = (
            db.query(JobRecord)
            .filter(JobRecord.tenant_id == tenant_id)
            .order_by(JobRecord.created_at.desc())
            .first()
        )
        if first_job:
            db.add(
                ApprovalRequestRecord(
                    approval_id=f"baseline-appr-{uuid.uuid4().hex[:8]}",
                    tenant_id=tenant_id,
                    job_id=first_job.job_id,
                    job_type=first_job.job_type,
                    state="pending",
                    channel="internal",
                    title="Baseline pending approval",
                    summary="Seed approval for local operator panel verification",
                    requested_by="baseline_seed",
                    requested_at=now,
                    created_at=now,
                    updated_at=now,
                    request_payload={"seed": True},
                )
            )
            db.commit()
            report.lines.append(
                OperationLine(
                    table="approval_requests",
                    tenant_id=tenant_id,
                    rows=1,
                    action=RowAction.SKIP,
                    note="baseline pending approval created",
                )
            )

    return report
