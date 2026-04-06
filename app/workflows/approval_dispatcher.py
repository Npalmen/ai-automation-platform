from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.audit_service import create_audit_event
from app.domain.workflows.models import Job
from app.repositories.postgres.job_repository import JobRepository
from app.workflows.approval_service import get_pending_approval
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

        create_audit_event(
            db=db,
            tenant_id=updated_job.tenant_id,
            category="workflow",
            action="approval_dispatched",
            status="success",
            details={
                "job_id": updated_job.job_id,
                "channel": delivery["channel"],
            },
        )

    return updated_job