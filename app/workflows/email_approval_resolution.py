"""Sync job state after email_send approval resolution (internal handoff, etc.)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.audit_service import create_audit_event
from app.domain.workflows.models import Job
from app.domain.workflows.statuses import JobStatus
from app.repositories.postgres.action_execution_repository import ActionExecutionRepository
from app.repositories.postgres.action_execution_models import ActionExecutionRecord
from app.repositories.postgres.approval_repository import ApprovalRequestRepository
from app.repositories.postgres.job_repository import JobRepository

INTERNAL_HANDOFF_ACTION = "send_internal_handoff"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _pending_approval_count(db: Session, tenant_id: str, job_id: str) -> int:
    return ApprovalRequestRepository.count_pending_for_job(
        db=db,
        tenant_id=tenant_id,
        job_id=job_id,
    )


def _sync_action_dispatch_processor_history(
    job: Job,
    *,
    approval_id: str,
    approved: bool,
    send_result: dict[str, Any] | None,
    pending_count: int,
) -> Job:
    history = list(job.processor_history)
    for item in reversed(history):
        if item.get("processor") != "action_dispatch_processor":
            continue
        result = dict(item.get("result") or {})
        payload = dict(result.get("payload") or {})
        pending_list = list(payload.get("actions_pending_approval") or [])
        payload["actions_pending_approval"] = [
            entry
            for entry in pending_list
            if entry.get("approval_id") != approval_id
        ]
        payload["pending_approval_count"] = pending_count
        if approved and send_result and send_result.get("status") == "executed":
            executed = list(payload.get("actions_executed") or [])
            executed.append(send_result)
            payload["actions_executed"] = executed
        result["payload"] = payload
        item["result"] = result
        break
    job.processor_history = history
    return job


def _record_email_approval_execution(
    db: Session,
    *,
    tenant_id: str,
    job_id: str,
    approval_id: str,
    delivery: dict[str, Any],
    send_result: dict[str, Any] | None,
    send_error: str | None,
) -> None:
    existing = ActionExecutionRepository.list_for_job(db, tenant_id, job_id)
    for record in existing:
        req = record.request_payload or {}
        if req.get("approval_id") == approval_id:
            return

    action_type = str(delivery.get("type") or "send_email")
    if send_result and send_result.get("status") == "executed":
        ActionExecutionRepository.create_from_executed_action(
            db=db,
            tenant_id=tenant_id,
            job_id=job_id,
            request_action={**delivery, "approval_id": approval_id},
            executed_action=send_result,
        )
        return

    ActionExecutionRepository.create_from_failed_action(
        db=db,
        tenant_id=tenant_id,
        job_id=job_id,
        request_action={**delivery, "approval_id": approval_id},
        failure_payload={
            "type": action_type,
            "status": "failed",
            "error": send_error or "email_send_failed",
            "payload": delivery,
        },
    )


def _apply_post_resolution_job_status(
    job: Job,
    *,
    approved: bool,
    pending_count: int,
    send_result: dict[str, Any] | None,
    send_error: str | None,
    delivery: dict[str, Any],
    approval_id: str,
) -> Job:
    result = dict(job.result or {})

    if pending_count > 0:
        job.status = JobStatus.AWAITING_APPROVAL
        return job

    action_type = str(delivery.get("type") or "")
    send_succeeded = bool(send_result and send_result.get("status") == "executed")

    if not approved:
        job.status = JobStatus.MANUAL_REVIEW
        result["requires_human_review"] = True
        result["summary"] = "Email approval rejected."
        job.result = result
        return job

    if action_type == INTERNAL_HANDOFF_ACTION and send_succeeded:
        job.status = JobStatus.COMPLETED
        result.update(
            {
                "status": "completed",
                "summary": "Intern handoff skickad. Kundärendet väntar på operatör.",
                "requires_human_review": False,
                "internal_handoff_sent_at": _isoformat(_utcnow()),
                "internal_handoff_approval_id": approval_id,
                "customer_case_open": True,
                "automation_phase": "internal_handoff_sent",
            }
        )
        job.result = result
        return job

    if send_succeeded:
        job.status = JobStatus.COMPLETED
        result["status"] = "completed"
        result["requires_human_review"] = False
        job.result = result
        return job

    job.status = JobStatus.MANUAL_REVIEW
    result["requires_human_review"] = True
    result["summary"] = "Godkänd e-post kunde inte skickas."
    if send_error:
        result["send_error"] = send_error
    job.result = result
    return job


def finalize_email_approval_resolution(
    db: Session,
    approval,
    *,
    approved: bool,
    actor: str | None,
    note: str | None,
    send_result: dict[str, Any] | None,
    send_error: str | None,
) -> Job | None:
    """Update job, processor history, and action audit after email approval."""
    job = JobRepository.get_job_by_id(db, approval.tenant_id, approval.job_id)
    if job is None:
        return None

    delivery = dict(approval.delivery_payload or {})

    if approved and delivery:
        _record_email_approval_execution(
            db,
            tenant_id=approval.tenant_id,
            job_id=approval.job_id,
            approval_id=approval.approval_id,
            delivery=delivery,
            send_result=send_result,
            send_error=send_error,
        )

    pending_count = _pending_approval_count(db, approval.tenant_id, approval.job_id)
    job = _sync_action_dispatch_processor_history(
        job,
        approval_id=approval.approval_id,
        approved=approved,
        send_result=send_result,
        pending_count=pending_count,
    )
    job = _apply_post_resolution_job_status(
        job,
        approved=approved,
        pending_count=pending_count,
        send_result=send_result,
        send_error=send_error,
        delivery=delivery,
        approval_id=approval.approval_id,
    )
    job.updated_at = _utcnow()
    persisted = JobRepository.update_job(db, job)

    create_audit_event(
        db=db,
        tenant_id=approval.tenant_id,
        category="approval",
        action="email_approval_resolved",
        status="success" if not send_error else "partial",
        details={
            "approval_id": approval.approval_id,
            "job_id": approval.job_id,
            "approved": approved,
            "actor": actor,
            "pending_approvals_remaining": pending_count,
            "job_status": persisted.status.value if hasattr(persisted.status, "value") else str(persisted.status),
            "action_type": delivery.get("type"),
            "send_status": (send_result or {}).get("status"),
        },
    )
    return persisted


def count_internal_handoffs_sent_since(
    db: Session,
    tenant_id: str,
    since: datetime,
) -> int:
    """Distinct jobs with a successful internal handoff execution since *since*."""
    from sqlalchemy import distinct, func

    return (
        db.query(func.count(distinct(ActionExecutionRecord.job_id)))
        .filter(
            ActionExecutionRecord.tenant_id == tenant_id,
            ActionExecutionRecord.action_type == INTERNAL_HANDOFF_ACTION,
            ActionExecutionRecord.status == "executed",
            ActionExecutionRecord.executed_at >= since,
        )
        .scalar()
        or 0
    )
