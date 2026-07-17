"""Shared read-only alert signal sources (Kapitel 10).

Single source of truth for job/approval signals used by triage, evaluators, and digest.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
from app.workflows.manual_review_handoff import is_unresolved_manual_review

STUCK_JOB_WINDOW_H = 48
FAILED_JOBS_WINDOW_H = 48
STALE_APPROVAL_WINDOW_H = 24
MANUAL_REVIEW_STALE_H = 48
REPEATED_FAILURE_THRESHOLD = 3


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def fingerprint_payload(parts: dict[str, Any]) -> str:
    raw = "|".join(f"{k}={v}" for k, v in sorted(parts.items()))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


@dataclass
class ApprovalStaleSignal:
    tenant_id: str
    tenant_name: str
    approval_id: str
    job_id: str
    kind: str
    age_hours: int
    created_at: datetime
    source_id: str


@dataclass
class StuckJobSignal:
    tenant_id: str
    tenant_name: str
    job_id: str
    job_type: str
    status: str
    age_hours: int
    updated_at: datetime
    source_id: str


@dataclass
class FailedJobSignal:
    tenant_id: str
    tenant_name: str
    job_id: str
    job_type: str
    error_summary: str
    updated_at: datetime
    source_id: str


@dataclass
class ManualReviewStaleSignal:
    tenant_id: str
    tenant_name: str
    job_id: str
    job_type: str
    age_hours: int
    updated_at: datetime
    source_id: str


def collect_stale_approval_signals(
    db: Session,
    *,
    tenant_id: str,
    tenant_name: str,
    stale_hours: int = STALE_APPROVAL_WINDOW_H,
    limit: int = 50,
) -> list[ApprovalStaleSignal]:
    cutoff = _utcnow() - timedelta(hours=stale_hours)
    rows: list[ApprovalStaleSignal] = []
    try:
        stale = (
            db.query(ApprovalRequestRecord)
            .filter(
                ApprovalRequestRecord.tenant_id == tenant_id,
                ApprovalRequestRecord.state == "pending",
                ApprovalRequestRecord.created_at < cutoff,
            )
            .order_by(ApprovalRequestRecord.created_at.asc())
            .limit(limit)
            .all()
        )
        for appr in stale:
            kind = appr.next_on_approve or "pipeline"
            created = _ensure_aware(appr.created_at)
            age = int((_utcnow() - created).total_seconds() / 3600)
            rows.append(
                ApprovalStaleSignal(
                    tenant_id=tenant_id,
                    tenant_name=tenant_name,
                    approval_id=appr.approval_id,
                    job_id=appr.job_id,
                    kind=kind,
                    age_hours=age,
                    created_at=created,
                    source_id=f"approval:{appr.approval_id}",
                )
            )
    except Exception:
        pass
    return rows


def collect_stuck_job_signals(
    db: Session,
    *,
    tenant_id: str,
    tenant_name: str,
    stuck_hours: int = STUCK_JOB_WINDOW_H,
    limit: int = 50,
) -> list[StuckJobSignal]:
    cutoff = _utcnow() - timedelta(hours=stuck_hours)
    rows: list[StuckJobSignal] = []
    try:
        stuck = (
            db.query(JobRecord)
            .filter(
                JobRecord.tenant_id == tenant_id,
                JobRecord.status.in_(("pending", "processing")),
                JobRecord.updated_at < cutoff,
            )
            .order_by(JobRecord.updated_at.asc())
            .limit(limit)
            .all()
        )
        for job in stuck:
            updated = _ensure_aware(job.updated_at)
            age = int((_utcnow() - updated).total_seconds() / 3600)
            rows.append(
                StuckJobSignal(
                    tenant_id=tenant_id,
                    tenant_name=tenant_name,
                    job_id=job.job_id,
                    job_type=job.job_type,
                    status=job.status,
                    age_hours=age,
                    updated_at=updated,
                    source_id=f"job:{job.job_id}",
                )
            )
    except Exception:
        pass
    return rows


def collect_failed_job_signals(
    db: Session,
    *,
    tenant_id: str,
    tenant_name: str,
    window_hours: int = FAILED_JOBS_WINDOW_H,
    limit: int = 50,
) -> list[FailedJobSignal]:
    cutoff = _utcnow() - timedelta(hours=window_hours)
    rows: list[FailedJobSignal] = []
    try:
        failed_jobs = (
            db.query(JobRecord)
            .filter(
                JobRecord.tenant_id == tenant_id,
                JobRecord.status == "failed",
                JobRecord.updated_at >= cutoff,
            )
            .order_by(JobRecord.updated_at.desc())
            .limit(limit)
            .all()
        )
        for job in failed_jobs:
            result = job.result or {}
            error_msg = result.get("error") or result.get("message") or "No error detail."
            rows.append(
                FailedJobSignal(
                    tenant_id=tenant_id,
                    tenant_name=tenant_name,
                    job_id=job.job_id,
                    job_type=job.job_type,
                    error_summary=str(error_msg)[:200],
                    updated_at=_ensure_aware(job.updated_at),
                    source_id=f"job:{job.job_id}",
                )
            )
    except Exception:
        pass
    return rows


def collect_manual_review_stale_signals(
    db: Session,
    *,
    tenant_id: str,
    tenant_name: str,
    stale_hours: int = MANUAL_REVIEW_STALE_H,
    limit: int = 50,
) -> list[ManualReviewStaleSignal]:
    cutoff = _utcnow() - timedelta(hours=stale_hours)
    rows: list[ManualReviewStaleSignal] = []
    try:
        jobs = (
            db.query(JobRecord)
            .filter(
                JobRecord.tenant_id == tenant_id,
                JobRecord.status == "manual_review",
                JobRecord.updated_at < cutoff,
            )
            .order_by(JobRecord.updated_at.asc())
            .limit(limit)
            .all()
        )
        for job in jobs:
            from app.domain.workflows.models import Job

            domain_job = Job(
                job_id=job.job_id,
                tenant_id=job.tenant_id,
                job_type=job.job_type,
                status=job.status,
                input_data=job.input_data or {},
                result=job.result or {},
                created_at=job.created_at,
                updated_at=job.updated_at,
            )
            if not is_unresolved_manual_review(domain_job):
                continue
            updated = _ensure_aware(job.updated_at)
            age = int((_utcnow() - updated).total_seconds() / 3600)
            rows.append(
                ManualReviewStaleSignal(
                    tenant_id=tenant_id,
                    tenant_name=tenant_name,
                    job_id=job.job_id,
                    job_type=job.job_type,
                    age_hours=age,
                    updated_at=updated,
                    source_id=f"job:{job.job_id}",
                )
            )
    except Exception:
        pass
    return rows


def count_recent_failed_jobs(
    db: Session,
    tenant_id: str,
    *,
    window_hours: int = FAILED_JOBS_WINDOW_H,
) -> int:
    cutoff = _utcnow() - timedelta(hours=window_hours)
    try:
        return (
            db.query(JobRecord)
            .filter(
                JobRecord.tenant_id == tenant_id,
                JobRecord.status == "failed",
                JobRecord.updated_at >= cutoff,
            )
            .count()
        )
    except Exception:
        return 0


def iter_active_tenants(db: Session) -> list[tuple[str, str]]:
    tenants: list[tuple[str, str]] = []
    try:
        for record in TenantConfigRepository.list_all(db):
            name = record.slug or record.tenant_id
            tenants.append((record.tenant_id, name))
    except Exception:
        pass
    return tenants


def scheduler_expected_state(settings: dict) -> str:
    """Server-side expected scheduler state. paused/manual => no failure alerts."""
    scheduler = settings.get("scheduler") or {}
    run_mode = str(scheduler.get("run_mode") or "manual").strip().lower()
    if run_mode in ("paused", "manual"):
        return "not_running"
    if run_mode == "scheduled":
        return "running"
    return "not_running"
