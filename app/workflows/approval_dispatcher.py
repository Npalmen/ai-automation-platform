from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.audit_service import create_audit_event
from app.domain.workflows.models import Job
from app.repositories.postgres.approval_repository import ApprovalRequestRepository
from app.repositories.postgres.job_repository import JobRepository
from app.workflows.approval_service import action_dispatch_pending_approval_count, get_pending_approval
from app.workflows.processors.ai_processor_utils import append_processor_result

PROCESSOR_NAME = "approval_dispatcher"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _extract_delivery_target(job: Job, channel: str) -> str | None:
    input_data = job.input_data or {}

    if channel == "email":
        return input_data.get("approval_email")

    if channel == "slack":
        return input_data.get("approval_slack_channel")

    if channel == "teams":
        return input_data.get("approval_teams_channel")

    if channel == "dashboard":
        return "default"

    return None


def _build_delivery_payload(job: Job, approval_request: dict[str, Any]) -> dict[str, Any]:
    channel = approval_request.get("channel", "dashboard")
    target = _extract_delivery_target(job, channel)
    now = _utcnow()

    return {
        "delivery_id": f"{approval_request['approval_id']}:{channel}",
        "channel": channel,
        "target": target,
        "status": "sent",
        "sent_at": _isoformat(now),
        "message": {
            "title": approval_request.get("title"),
            "summary": approval_request.get("summary"),
        },
    }


def _should_materialize_per_action_approvals(job: Job) -> bool:
    """Only trusted live-eval jobs need per-action rows before operator action."""
    from app.evaluation.live.context import snapshot_from_job_input

    snapshot = snapshot_from_job_input(job.input_data)
    return snapshot is not None and bool(snapshot.trusted)


def _materialize_per_action_approvals(db: Session, job: Job) -> Job:
    """Run action dispatch once to queue per-action approvals before job-level fallback."""
    if not _should_materialize_per_action_approvals(job):
        return job
    if action_dispatch_pending_approval_count(job) > 0:
        return job

    from app.workflows.pipeline_run_context import PipelineRunSource, create_trace_session
    from app.workflows.processors.action_dispatch_processor import process_action_dispatch_job

    trace = create_trace_session(job, source=PipelineRunSource.INTAKE, db=db)
    materialized = process_action_dispatch_job(job, db=db, trace=trace)
    updated = JobRepository.update_job(db, materialized)
    _cancel_superseded_job_level_approvals(db, updated)
    return updated


def _has_authoritative_per_action_approvals(
    db: Session,
    *,
    tenant_id: str,
    job_id: str,
) -> bool:
    rows = ApprovalRequestRepository.list_for_job(
        db=db,
        tenant_id=tenant_id,
        job_id=job_id,
    )
    return any(
        row.next_on_approve in ("action_execute", "email_send")
        for row in rows
    )


def _cancel_superseded_job_level_approvals(db: Session, job: Job) -> None:
    """Reject legacy job-level pending rows when per-action approvals are authoritative."""
    rows = ApprovalRequestRepository.list_for_job(
        db=db,
        tenant_id=job.tenant_id,
        job_id=job.job_id,
    )
    has_per_action = any(
        row.next_on_approve in ("action_execute", "email_send")
        for row in rows
    )
    if not has_per_action:
        return

    now = _utcnow()
    changed = False
    for row in rows:
        if row.state != "pending":
            continue
        if row.next_on_approve != "action_dispatch":
            continue
        ApprovalRequestRepository.transition_state_if_pending(
            db,
            tenant_id=job.tenant_id,
            approval_id=row.approval_id,
            new_state="rejected",
            resolved_at=now,
            resolved_by="system",
            resolution_note="superseded_by_per_action_approval",
        )
        changed = True
    if changed:
        db.commit()


def dispatch_approval_request(db: Session | None, job: Job) -> Job:
    approval_request = get_pending_approval(job)
    if approval_request is None:
        return job

    payload = (job.result or {}).get("payload") or {}
    if payload.get("approval_delivery"):
        return job

    delivery = _build_delivery_payload(job, approval_request)

    result = {
        "status": "completed",
        "summary": f"Approval dispatched via {delivery['channel']}.",
        "requires_human_review": False,
        "payload": {
            "processor_name": PROCESSOR_NAME,
            "approval_request": approval_request,
            "approval_delivery": delivery,
        },
    }

    updated_job = append_processor_result(job, PROCESSOR_NAME, result)
    updated_job.updated_at = _utcnow()

    if db:
        updated_job = JobRepository.update_job(db, updated_job)
        if action_dispatch_pending_approval_count(updated_job) == 0:
            updated_job = _materialize_per_action_approvals(db, updated_job)
        else:
            _cancel_superseded_job_level_approvals(db, updated_job)
        # Per-action approvals from action_dispatch_processor are authoritative in DB.
        # Do not create a competing job-level row (next_on_approve=action_dispatch) that
        # would shadow the per-action approval (action_execute) for operators.
        if (
            action_dispatch_pending_approval_count(updated_job) == 0
            and not _has_authoritative_per_action_approvals(
                db,
                tenant_id=updated_job.tenant_id,
                job_id=updated_job.job_id,
            )
        ):
            ApprovalRequestRepository.upsert_from_payload(
                db=db,
                tenant_id=updated_job.tenant_id,
                job_id=updated_job.job_id,
                job_type=updated_job.job_type.value if hasattr(updated_job.job_type, "value") else str(updated_job.job_type),
                approval_request=approval_request,
                delivery_payload=delivery,
            )

    create_audit_event(
        db=db,
        tenant_id=updated_job.tenant_id,
        category="workflow",
        action="approval_dispatched",
        status="success",
        details={
            "job_id": updated_job.job_id,
            "approval_id": approval_request.get("approval_id"),
            "channel": delivery["channel"],
        },
    )

    return updated_job