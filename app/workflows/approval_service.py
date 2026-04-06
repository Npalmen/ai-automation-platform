from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.audit_service import create_audit_event
from app.domain.workflows.models import Job
from app.domain.workflows.statuses import JobStatus
from app.repositories.postgres.approval_repository import ApprovalRequestRepository
from app.repositories.postgres.job_repository import JobRepository
from app.workflows.processors.ai_processor_utils import append_processor_result, get_latest_processor_payload

APPROVAL_ENGINE_PROCESSOR = "approval_engine"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _select_channel(job: Job) -> str:
    input_data = job.input_data or {}
    requested_channel = input_data.get("approval_channel")

    if requested_channel in {"dashboard", "email", "slack", "teams"}:
        return requested_channel

    return "dashboard"


def _build_title(job: Job, detected_job_type: str) -> str:
    input_data = job.input_data or {}
    subject = input_data.get("subject")
    if subject:
        return f"Approval required: {subject}"
    return f"Approval required for {detected_job_type}"


def _build_summary(
    *,
    job: Job,
    detected_job_type: str,
    policy_payload: dict[str, Any],
    previous_payload: dict[str, Any],
) -> str:
    reasons = policy_payload.get("reasons") or []
    summary_parts: list[str] = [f"Job type: {detected_job_type}."]

    if reasons:
        summary_parts.append("Reasons: " + ", ".join(str(item) for item in reasons))

    recommendation = policy_payload.get("recommended_next_step")
    if recommendation:
        summary_parts.append(f"Recommended next step: {recommendation}.")

    confidence = previous_payload.get("confidence")
    if confidence is not None:
        summary_parts.append(f"Confidence: {confidence}.")

    return " ".join(summary_parts)


def build_approval_request(job: Job) -> dict[str, Any]:
    policy_payload = get_latest_processor_payload(job, "policy_processor")
    previous_payload = get_latest_processor_payload(job, "decisioning_processor") or get_latest_processor_payload(job, "invoice_processor")
    classification_payload = get_latest_processor_payload(job, "classification_processor")

    detected_job_type = classification_payload.get("detected_job_type", job.job_type.value)
    now = _utcnow()

    return {
        "approval_id": str(uuid4()),
        "job_id": job.job_id,
        "tenant_id": job.tenant_id,
        "job_type": detected_job_type,
        "state": "pending",
        "channel": _select_channel(job),
        "title": _build_title(job, detected_job_type),
        "summary": _build_summary(
            job=job,
            detected_job_type=detected_job_type,
            policy_payload=policy_payload,
            previous_payload=previous_payload,
        ),
        "requested_by": "system",
        "requested_at": _isoformat(now),
        "expires_at": _isoformat(now + timedelta(days=7)),
        "decision_context": {
            "job_id": job.job_id,
            "tenant_id": job.tenant_id,
            "detected_job_type": detected_job_type,
            "policy_decision": policy_payload.get("decision"),
            "approval_route": policy_payload.get("approval_route"),
            "recommended_next_step": policy_payload.get("recommended_next_step"),
            "reasons": policy_payload.get("reasons", []),
        },
        "allowed_actions": ["approve", "reject"],
        "next_on_approve": "action_dispatch",
        "next_on_reject": "manual_review",
    }


def get_pending_approval(job: Job) -> dict[str, Any] | None:
    payload = (job.result or {}).get("payload") or {}
    approval_request = payload.get("approval_request")

    if not isinstance(approval_request, dict):
        return None

    if approval_request.get("state") != "pending":
        return None

    return approval_request


def has_pending_approval(job: Job) -> bool:
    return get_pending_approval(job) is not None


def _build_resolution_result(
    *,
    approval_request: dict[str, Any],
    approved: bool,
    actor: str,
    channel: str,
    note: str | None,
) -> dict[str, Any]:
    resolved_at = _isoformat(_utcnow())
    resolved_approval = {
        **approval_request,
        "state": "approved" if approved else "rejected",
        "resolved_at": resolved_at,
        "resolved_by": actor,
        "resolved_via": channel,
        "resolution_note": note,
    }

    return {
        "status": "completed",
        "summary": "Approval granted." if approved else "Approval rejected.",
        "requires_human_review": not approved,
        "payload": {
            "processor_name": APPROVAL_ENGINE_PROCESSOR,
            "approval_decision": "approved" if approved else "rejected",
            "approval_request": resolved_approval,
            "recommended_next_step": (
                approval_request.get("next_on_approve", "action_dispatch")
                if approved
                else approval_request.get("next_on_reject", "manual_review")
            ),
        },
    }


def resolve_approval(
    *,
    db: Session,
    tenant_id: str,
    job_id: str,
    approved: bool,
    actor: str,
    channel: str,
    note: str | None,
) -> Job:
    from app.workflows.orchestrator import WorkflowOrchestrator

    job = JobRepository.get_job_by_id(db, tenant_id, job_id)
    if job is None:
        raise ValueError(f"Job '{job_id}' not found for tenant '{tenant_id}'.")

    approval_request = get_pending_approval(job)
    if approval_request is None:
        raise ValueError(f"Job '{job_id}' has no pending approval.")

    result = _build_resolution_result(
        approval_request=approval_request,
        approved=approved,
        actor=actor,
        channel=channel,
        note=note,
    )

    current_payload = (job.result or {}).get("payload") or {}
    approval_delivery = current_payload.get("approval_delivery")

    if isinstance(approval_delivery, dict):
        result["payload"]["approval_delivery"] = {
            **approval_delivery,
            "decision_recorded_at": _isoformat(_utcnow()),
        }

    job = append_processor_result(job, APPROVAL_ENGINE_PROCESSOR, result)
    job.updated_at = _utcnow()

    if approved:
        job.status = JobStatus.PROCESSING
        job = JobRepository.update_job(db, job)

        ApprovalRequestRepository.upsert_from_payload(
            db=db,
            tenant_id=job.tenant_id,
            job_id=job.job_id,
            job_type=job.job_type.value if hasattr(job.job_type, "value") else str(job.job_type),
            approval_request=result["payload"]["approval_request"],
            delivery_payload=result["payload"].get("approval_delivery"),
        )

        orchestrator = WorkflowOrchestrator(db)
        job = orchestrator.resume_after_approval(job)
    else:
        job.status = JobStatus.MANUAL_REVIEW
        job = JobRepository.update_job(db, job)

        ApprovalRequestRepository.upsert_from_payload(
            db=db,
            tenant_id=job.tenant_id,
            job_id=job.job_id,
            job_type=job.job_type.value if hasattr(job.job_type, "value") else str(job.job_type),
            approval_request=result["payload"]["approval_request"],
            delivery_payload=result["payload"].get("approval_delivery"),
        )

    create_audit_event(
        db=db,
        tenant_id=tenant_id,
        category="workflow",
        action="approval_resolved",
        status="success",
        details={
            "job_id": job.job_id,
            "approval_id": approval_request.get("approval_id"),
            "decision": "approved" if approved else "rejected",
            "actor": actor,
            "channel": channel,
        },
    )

    return job


def get_approval_status(job: Job) -> dict[str, Any]:
    payload = (job.result or {}).get("payload") or {}
    approval_request = payload.get("approval_request")
    approval_delivery = payload.get("approval_delivery")

    return {
        "job_id": job.job_id,
        "tenant_id": job.tenant_id,
        "status": job.status,
        "approval": approval_request,
        "delivery": approval_delivery,
    }