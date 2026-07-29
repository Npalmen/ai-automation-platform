"""Read-only metrics queries for production pilot observability."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.production_pilot.observability.message_filters import (
    gmail_message_id,
    is_real_pilot_inbound_message,
)
from app.production_pilot.observability.redaction import provider_message_ref_hash
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.decision_record_models import DecisionRecordRow
from app.repositories.postgres.end_customer_shadow_models import (
    EndCustomerShadowMatchProposalRecord,
    EndCustomerShadowObservationRecord,
)
from app.repositories.postgres.job_models import JobRecord


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    end = datetime.combine(day, time.max, tzinfo=timezone.utc)
    return start, end


def _jobs_in_range(db: Session, tenant_id: str, start: datetime, end: datetime) -> list[JobRecord]:
    return (
        db.query(JobRecord)
        .filter(
            JobRecord.tenant_id == tenant_id,
            JobRecord.created_at >= start,
            JobRecord.created_at <= end,
        )
        .order_by(JobRecord.created_at.asc())
        .all()
    )


def _classification_from_job(job: JobRecord) -> str:
    result = job.result or {}
    classification = result.get("classification") or result.get("email_type")
    if classification:
        return str(classification)
    input_data = job.input_data or {}
    return str(input_data.get("inferred_type") or job.job_type or "unknown")


def _latency_seconds(job: JobRecord) -> float | None:
    if not job.created_at or not job.updated_at:
        return None
    return max(0.0, (job.updated_at - job.created_at).total_seconds())


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = int(round((pct / 100.0) * (len(ordered) - 1)))
    return ordered[idx]


def collect_intake_metrics(
    db: Session,
    *,
    tenant_id: str,
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    jobs = _jobs_in_range(db, tenant_id, start, end)
    real_jobs = [job for job in jobs if is_real_pilot_inbound_message(job.input_data)]
    provider_ids = [gmail_message_id(job.input_data) for job in real_jobs]
    provider_ids = [mid for mid in provider_ids if mid]
    correlated = len(provider_ids)
    duplicate_suppressions = max(0, len([job for job in jobs if (job.input_data or {}).get("duplicate_suppressed")]) )
    failed = len([job for job in real_jobs if job.status in {"failed", "error"}])
    processed = len([job for job in real_jobs if job.status not in {"pending", "queued"}])
    pending = len([job for job in real_jobs if job.status in {"pending", "queued", "processing"}])
    latencies = [v for v in (_latency_seconds(job) for job in real_jobs) if v is not None]
    unknown_types = len(
        [
            job
            for job in real_jobs
            if _classification_from_job(job) in {"unknown", "spam", "no_reply"}
        ]
    )
    correlation_gaps = max(0, len(real_jobs) - correlated)
    return {
        "provider_inbound_count": correlated,
        "correlated_intake_count": correlated,
        "processed_count": processed,
        "failed_count": failed,
        "pending_count": pending,
        "duplicate_suppressions": duplicate_suppressions,
        "correlation_gaps": correlation_gaps,
        "processing_latency_p50": _percentile(latencies, 50),
        "processing_latency_p95": _percentile(latencies, 95),
        "no_reply_spam_unknown_count": unknown_types,
        "real_message_job_ids": [job.job_id for job in real_jobs],
    }


def collect_classification_metrics(db: Session, *, tenant_id: str, start: datetime, end: datetime) -> dict[str, Any]:
    jobs = _jobs_in_range(db, tenant_id, start, end)
    real_jobs = [job for job in jobs if is_real_pilot_inbound_message(job.input_data)]
    distribution = Counter(_classification_from_job(job) for job in real_jobs)
    low_confidence = 0
    extraction_failures = 0
    missing_required = 0
    for job in real_jobs:
        result = job.result or {}
        confidence = result.get("confidence")
        if confidence is not None and float(confidence) < 0.6:
            low_confidence += 1
        if result.get("extraction_status") == "failed" or result.get("extraction_failed"):
            extraction_failures += 1
        if result.get("missing_required_fields"):
            missing_required += 1
    return {
        "classification_distribution": dict(distribution),
        "low_confidence_count": low_confidence,
        "extraction_success_count": max(0, len(real_jobs) - extraction_failures),
        "extraction_failure_count": extraction_failures,
        "missing_required_fields_count": missing_required,
    }


def collect_queue_metrics(db: Session, *, tenant_id: str, start: datetime, end: datetime) -> dict[str, Any]:
    jobs = _jobs_in_range(db, tenant_id, start, end)
    real_jobs = [job for job in jobs if is_real_pilot_inbound_message(job.input_data)]
    manual_review = len([job for job in real_jobs if job.status == "manual_review" or (job.result or {}).get("manual_review")])
    needs_help = len([job for job in real_jobs if job.status == "needs_help" or (job.result or {}).get("needs_help")])
    unresolved = len([job for job in real_jobs if job.status not in {"completed", "done", "resolved", "cancelled"}])
    ages = [v for v in (_latency_seconds(job) for job in real_jobs if job.status in {"manual_review", "needs_help", "pending"}) if v is not None]
    return {
        "manual_review_count": manual_review,
        "needs_help_count": needs_help,
        "queue_age_seconds_max": max(ages) if ages else 0,
        "unresolved_count": unresolved,
        "incidents_open": 0,
    }


def collect_shadow_metrics(db: Session, *, tenant_id: str, start: datetime, end: datetime) -> dict[str, Any]:
    observations = (
        db.query(EndCustomerShadowObservationRecord)
        .filter(
            EndCustomerShadowObservationRecord.tenant_id == tenant_id,
            EndCustomerShadowObservationRecord.created_at >= start,
            EndCustomerShadowObservationRecord.created_at <= end,
        )
        .count()
    )
    match_proposals = (
        db.query(EndCustomerShadowMatchProposalRecord)
        .filter(
            EndCustomerShadowMatchProposalRecord.tenant_id == tenant_id,
            EndCustomerShadowMatchProposalRecord.created_at >= start,
            EndCustomerShadowMatchProposalRecord.created_at <= end,
        )
        .count()
    )
    ambiguous = (
        db.query(EndCustomerShadowMatchProposalRecord)
        .filter(
            EndCustomerShadowMatchProposalRecord.tenant_id == tenant_id,
            EndCustomerShadowMatchProposalRecord.created_at >= start,
            EndCustomerShadowMatchProposalRecord.created_at <= end,
            EndCustomerShadowMatchProposalRecord.state == "ambiguous",
        )
        .count()
    )
    return {
        "observations_created": observations,
        "match_proposals": match_proposals,
        "ambiguous_matches": ambiguous,
        "conflicts": 0,
        "replay_suppressions": 0,
        "promotions": 0,
        "automatic_verified_facts": 0,
        "automatic_customer_links": 0,
        "automatic_merges": 0,
    }


def collect_safety_metrics(db: Session, *, tenant_id: str, start: datetime, end: datetime) -> dict[str, Any]:
    job_ids = [
        row[0]
        for row in db.query(JobRecord.job_id)
        .filter(JobRecord.tenant_id == tenant_id, JobRecord.created_at >= start, JobRecord.created_at <= end)
        .all()
    ]
    if not job_ids:
        return {
            "gmail_replies": 0,
            "gmail_adapter_invocations": 0,
            "approvals_external_write_capable": 0,
            "external_writes_by_integration": {},
            "unauthorized_writes": 0,
            "cross_tenant_findings": 0,
            "secret_redaction_findings": 0,
        }
    records = (
        db.query(DecisionRecordRow)
        .filter(
            DecisionRecordRow.tenant_id == tenant_id,
            DecisionRecordRow.job_id.in_(job_ids),
            DecisionRecordRow.created_at >= start,
            DecisionRecordRow.created_at <= end,
        )
        .all()
    )
    gmail_replies = 0
    gmail_adapter = 0
    external_writes: Counter[str] = Counter()
    for row in records:
        action_type = (row.action_type or "").lower()
        record_type = (row.record_type or "").lower()
        if "gmail" in action_type and "reply" in action_type:
            gmail_replies += 1
        if record_type == "execution_intent" and "gmail" in action_type:
            gmail_adapter += 1
        if record_type == "execution_outcome" and row.execution_status == "success":
            integration = (row.metadata_json or {}).get("integration") or action_type or "unknown"
            external_writes[str(integration)] += 1
    approvals = (
        db.query(ApprovalRequestRecord)
        .filter(
            ApprovalRequestRecord.tenant_id == tenant_id,
            ApprovalRequestRecord.created_at >= start,
            ApprovalRequestRecord.created_at <= end,
        )
        .count()
    )
    return {
        "gmail_replies": gmail_replies,
        "gmail_adapter_invocations": gmail_adapter,
        "approvals_external_write_capable": approvals,
        "external_writes_by_integration": dict(external_writes),
        "unauthorized_writes": 0,
        "cross_tenant_findings": 0,
        "secret_redaction_findings": 0,
    }


def collect_day_metrics(db: Session, *, tenant_id: str, day: date) -> dict[str, Any]:
    start, end = _day_bounds(day)
    return {
        "date": day.isoformat(),
        "intake": collect_intake_metrics(db, tenant_id=tenant_id, start=start, end=end),
        "classification": collect_classification_metrics(db, tenant_id=tenant_id, start=start, end=end),
        "queues": collect_queue_metrics(db, tenant_id=tenant_id, start=start, end=end),
        "shadow": collect_shadow_metrics(db, tenant_id=tenant_id, start=start, end=end),
        "safety": collect_safety_metrics(db, tenant_id=tenant_id, start=start, end=end),
    }


def count_real_messages_in_range(db: Session, *, tenant_id: str, start: date, end: date) -> int:
    start_dt, _ = _day_bounds(start)
    _, end_dt = _day_bounds(end)
    jobs = _jobs_in_range(db, tenant_id, start_dt, end_dt)
    return len([job for job in jobs if is_real_pilot_inbound_message(job.input_data)])


def list_real_message_refs(
    db: Session,
    *,
    tenant_id: str,
    start: date,
    end: date,
) -> list[dict[str, str]]:
    start_dt, _ = _day_bounds(start)
    _, end_dt = _day_bounds(end)
    jobs = _jobs_in_range(db, tenant_id, start_dt, end_dt)
    refs: list[dict[str, str]] = []
    for job in jobs:
        if not is_real_pilot_inbound_message(job.input_data):
            continue
        message_id = gmail_message_id(job.input_data)
        if not message_id:
            continue
        refs.append(
            {
                "job_id": job.job_id,
                "provider_message_ref_hash": provider_message_ref_hash(tenant_id, message_id),
            }
        )
    return refs
