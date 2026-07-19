"""Gmail manual-review operator handoff — keep human-required items visible.

Stores handoff state on job.result.manual_review_handoff (no new DB columns).
Uses audit events for resolve/reconcile actions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.audit_service import create_audit_event
from app.domain.workflows.models import Job
from app.domain.workflows.statuses import JobStatus
from app.integrations.factory import get_integration_adapter
from app.integrations.service import get_integration_connection_config
from app.integrations.enums import IntegrationType
from app.repositories.postgres.job_repository import JobRepository
from app.workflows.processors.ai_processor_utils import get_latest_processor_payload

MANUAL_REVIEW_GMAIL_LABEL = "krowolf-manual-review"
HANDOFF_RESULT_KEY = "manual_review_handoff"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def extract_gmail_message_id(job: Job) -> str | None:
    """Return Gmail message_id linked to this job, or None."""
    input_data = job.input_data or {}
    source = input_data.get("source")
    if isinstance(source, dict) and source.get("system") == "gmail":
        message_id = source.get("message_id")
        if message_id and str(message_id).strip():
            return str(message_id).strip()

    conversation = input_data.get("conversation_messages") or []
    for entry in reversed(conversation):
        if not isinstance(entry, dict):
            continue
        if entry.get("source") not in (None, "gmail") and entry.get("source") != "gmail":
            continue
        message_id = entry.get("message_id")
        if message_id and str(message_id).strip():
            return str(message_id).strip()
    return None


def is_gmail_originated(job: Job) -> bool:
    return extract_gmail_message_id(job) is not None


def get_handoff_state(job: Job) -> dict[str, Any]:
    return dict((job.result or {}).get(HANDOFF_RESULT_KEY) or {})


def build_manual_review_reason(job: Job) -> tuple[str, list[str]]:
    handoff_payload = get_latest_processor_payload(job, "human_handoff_processor")
    policy_payload = get_latest_processor_payload(job, "policy_processor")

    reason_codes: list[str] = list(handoff_payload.get("reason_codes") or [])
    if not reason_codes:
        reason_codes = list(policy_payload.get("reasons") or [])

    status_val = job.status.value if hasattr(job.status, "value") else str(job.status)
    if status_val == JobStatus.FAILED.value and not reason_codes:
        reason_codes = ["pipeline_failure"]

    human_summary = handoff_payload.get("human_summary")
    if human_summary:
        reason = str(human_summary)
    elif reason_codes:
        reason = ", ".join(str(c) for c in reason_codes)
    else:
        reason = "manual_review_required"

    return reason, reason_codes


def job_needs_manual_review_handoff(job: Job) -> bool:
    status_val = job.status.value if hasattr(job.status, "value") else str(job.status)
    if status_val == JobStatus.MANUAL_REVIEW.value:
        return True
    if status_val == JobStatus.FAILED.value:
        return bool((job.result or {}).get("requires_human_review"))
    return False


def is_unresolved_manual_review(job: Job) -> bool:
    status_val = job.status.value if hasattr(job.status, "value") else str(job.status)
    if status_val != JobStatus.MANUAL_REVIEW.value:
        return False
    handoff = get_handoff_state(job)
    return not handoff.get("resolved_at")


def _merge_handoff_state(job: Job, updates: dict[str, Any]) -> Job:
    result = dict(job.result or {})
    handoff = dict(result.get(HANDOFF_RESULT_KEY) or {})
    handoff.update(updates)
    result[HANDOFF_RESULT_KEY] = handoff
    job.result = result
    job.updated_at = _utcnow()
    return job


def _get_gmail_adapter(tenant_id: str, db: Session | None = None):
    connection_config = get_integration_connection_config(
        tenant_id=tenant_id,
        integration_type=IntegrationType.GOOGLE_MAIL,
        db=db,
    )
    return get_integration_adapter(
        integration_type=IntegrationType.GOOGLE_MAIL,
        connection_config=connection_config,
    )


def _apply_gmail_labels(adapter, message_id: str) -> dict[str, Any]:
    label_id = adapter.client.ensure_label(MANUAL_REVIEW_GMAIL_LABEL)
    adapter.client.modify_message_labels(
        message_id,
        add_label_ids=["UNREAD", label_id],
    )
    return {
        "gmail_label": MANUAL_REVIEW_GMAIL_LABEL,
        "gmail_label_id": label_id,
        "gmail_marked_unread": True,
        "gmail_label_applied": True,
    }


def _remove_gmail_manual_review_label(adapter, message_id: str, *, mark_read: bool) -> dict[str, Any]:
    label_id = adapter.client.find_label_id(MANUAL_REVIEW_GMAIL_LABEL)
    if label_id:
        adapter.client.modify_message_labels(message_id, remove_label_ids=[label_id])
    if mark_read:
        adapter.client.mark_as_read(message_id)
    return {
        "gmail_label_removed": bool(label_id),
        "gmail_marked_read": mark_read,
    }


def apply_manual_review_handoff(
    db: Session,
    job: Job,
    *,
    adapter=None,
    notify: bool = True,
) -> dict[str, Any]:
    """Apply Gmail visibility handoff for a manual-review job. Idempotent."""
    if not job_needs_manual_review_handoff(job):
        return {"applied": False, "skipped": True, "reason": "not_manual_review"}

    message_id = extract_gmail_message_id(job)
    if not message_id:
        return {
            "applied": False,
            "fail_closed": True,
            "error": "missing_gmail_message_id",
        }

    handoff = get_handoff_state(job)
    if handoff.get("resolved_at"):
        return {"applied": False, "skipped": True, "reason": "already_resolved"}

    reason, reason_codes = build_manual_review_reason(job)
    now = _isoformat(_utcnow())
    already_complete = (
        handoff.get("gmail_message_id") == message_id
        and handoff.get("gmail_handoff_complete") is True
    )

    gmail_error = None
    gmail_updates: dict[str, Any] = {}
    if not already_complete:
        try:
            mail_adapter = adapter or _get_gmail_adapter(job.tenant_id, db=db)
            gmail_updates = _apply_gmail_labels(mail_adapter, message_id)
        except Exception as exc:
            gmail_error = str(exc)
            gmail_updates = {
                "gmail_handoff_complete": False,
                "gmail_error": gmail_error,
            }
    else:
        gmail_updates = {
            "gmail_handoff_complete": True,
            "gmail_label": handoff.get("gmail_label", MANUAL_REVIEW_GMAIL_LABEL),
            "gmail_label_applied": handoff.get("gmail_label_applied", True),
            "gmail_marked_unread": handoff.get("gmail_marked_unread", True),
        }

    notification_sent = bool(handoff.get("notification_sent"))
    if notify and not notification_sent and not gmail_error:
        try:
            from app.workflows.action_executor import execute_action

            input_data = job.input_data or {}
            subject = input_data.get("subject") or input_data.get("latest_subject") or "(no subject)"
            execute_action(
                {
                    "type": "notify_slack",
                    "tenant_id": job.tenant_id,
                    "channel": "#inbox",
                    "message": (
                        f"Manual review required (Gmail handoff).\n\n"
                        f"Subject: {subject}\n"
                        f"Reason:  {reason}\n"
                        f"Job ID:  {job.job_id}\n"
                        f"Tenant:  {job.tenant_id}\n"
                        f"Gmail:   label:{MANUAL_REVIEW_GMAIL_LABEL} + UNREAD"
                    ),
                },
                db=db,
            )
            notification_sent = True
        except Exception:
            pass

    updates = {
        "manual_review_required": True,
        "manual_review_reason": reason,
        "manual_review_reason_codes": reason_codes,
        "gmail_message_id": message_id,
        "gmail_handoff_complete": gmail_error is None,
        "handoff_applied_at": handoff.get("handoff_applied_at") or now,
        "notification_sent": notification_sent,
        **gmail_updates,
    }
    if gmail_error:
        updates["gmail_error"] = gmail_error

    updated = _merge_handoff_state(job, updates)
    persisted = JobRepository.update_job(db, updated)

    if not already_complete and gmail_error is None:
        create_audit_event(
            db=db,
            tenant_id=job.tenant_id,
            category="manual_review",
            action="gmail_handoff_applied",
            status="success",
            details={
                "job_id": job.job_id,
                "gmail_message_id": message_id,
                "reason_codes": reason_codes,
                "gmail_label": MANUAL_REVIEW_GMAIL_LABEL,
            },
        )

    return {
        "applied": gmail_error is None,
        "job": persisted,
        "gmail_message_id": message_id,
        "gmail_error": gmail_error,
        "idempotent": already_complete,
    }


def resolve_manual_review_job(
    db: Session,
    job: Job,
    *,
    actor: str = "operator",
    note: str | None = None,
    mark_gmail_read: bool = False,
    adapter=None,
) -> dict[str, Any]:
    """Mark a manual-review job resolved; optionally clear Gmail manual-review label."""
    handoff = get_handoff_state(job)
    if handoff.get("resolved_at"):
        return {
            "status": "already_resolved",
            "job": job,
            "resolved_at": handoff.get("resolved_at"),
        }

    if not is_unresolved_manual_review(job):
        return {"status": "not_manual_review", "job": job}

    message_id = extract_gmail_message_id(job)
    gmail_result: dict[str, Any] = {}
    gmail_error = None

    if message_id and handoff.get("gmail_handoff_complete"):
        try:
            mail_adapter = adapter or _get_gmail_adapter(job.tenant_id, db=db)
            gmail_result = _remove_gmail_manual_review_label(
                mail_adapter,
                message_id,
                mark_read=mark_gmail_read,
            )
        except Exception as exc:
            gmail_error = str(exc)

    now = _isoformat(_utcnow())
    updates = {
        "manual_review_resolved_at": now,
        "resolved_at": now,
        "resolved_by": actor,
        "resolution_note": note,
        **gmail_result,
    }
    if gmail_error:
        updates["gmail_resolve_error"] = gmail_error

    updated = _merge_handoff_state(job, updates)
    updated.status = JobStatus.COMPLETED
    persisted = JobRepository.update_job(db, updated)

    create_audit_event(
        db=db,
        tenant_id=job.tenant_id,
        category="manual_review",
        action="manual_review_resolved",
        status="success" if gmail_error is None else "partial",
        details={
            "job_id": job.job_id,
            "actor": actor,
            "note": note,
            "mark_gmail_read": mark_gmail_read,
            "gmail_message_id": message_id,
            "gmail_error": gmail_error,
        },
    )

    return {
        "status": "resolved",
        "job": persisted,
        "gmail_error": gmail_error,
    }


def maybe_apply_gmail_manual_review_handoff(db: Session | None, job: Job) -> Job | None:
    """Non-gmail-sync entry point (orchestrator). Idempotent."""
    if db is None or not is_gmail_originated(job):
        return None
    if not job_needs_manual_review_handoff(job):
        return None
    result = apply_manual_review_handoff(db, job, notify=True)
    return result.get("job") or job


def post_pipeline_gmail_message_outcome(
    db: Session,
    tenant_id: str,
    processed_job: Job,
    message_id: str,
    adapter,
) -> dict[str, Any]:
    """After Gmail pipeline: manual-review handoff OR mark-as-read."""
    if job_needs_manual_review_handoff(processed_job):
        handoff_result = apply_manual_review_handoff(
            db,
            processed_job,
            adapter=adapter,
            notify=True,
        )
        updated_job = handoff_result.get("job") or processed_job
        entry = {
            "marked_handled": False,
            "manual_review_handoff": True,
            "manual_review_reason": get_handoff_state(updated_job).get("manual_review_reason"),
        }
        if handoff_result.get("gmail_error"):
            entry["mark_warning"] = handoff_result["gmail_error"]
        if handoff_result.get("fail_closed"):
            entry["handoff_error"] = handoff_result.get("error")
        return entry

    marked_handled = False
    mark_warning = None
    try:
        adapter.execute_action(action="mark_as_read", payload={"message_id": message_id})
        marked_handled = True
    except Exception as exc:
        mark_warning = str(exc)

    outcome = {"marked_handled": marked_handled}
    if mark_warning:
        outcome["mark_warning"] = mark_warning
    return outcome


def build_manual_review_job_summary(job: Job) -> dict[str, Any]:
    handoff = get_handoff_state(job)
    input_data = job.input_data or {}
    sender = input_data.get("sender") or {}
    return {
        "job_id": job.job_id,
        "tenant_id": job.tenant_id,
        "job_type": job.job_type.value if hasattr(job.job_type, "value") else str(job.job_type),
        "status": job.status.value if hasattr(job.status, "value") else str(job.status),
        "subject": input_data.get("subject") or input_data.get("latest_subject"),
        "sender_name": sender.get("name"),
        "sender_email": sender.get("email"),
        "manual_review_reason": handoff.get("manual_review_reason"),
        "manual_review_reason_codes": handoff.get("manual_review_reason_codes") or [],
        "gmail_message_id": handoff.get("gmail_message_id") or extract_gmail_message_id(job),
        "gmail_label": handoff.get("gmail_label"),
        "gmail_handoff_complete": handoff.get("gmail_handoff_complete"),
        "handoff_applied_at": handoff.get("handoff_applied_at"),
        "resolved_at": handoff.get("resolved_at"),
        "unresolved": is_unresolved_manual_review(job),
    }


def list_unresolved_manual_review_jobs(
    db: Session,
    tenant_id: str,
    *,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    records = JobRepository.list_jobs_for_tenant(
        db,
        tenant_id=tenant_id,
        limit=500,
        offset=0,
        status=JobStatus.MANUAL_REVIEW.value,
    )
    items = [
        build_manual_review_job_summary(JobRepository._to_domain(record))
        for record in records
        if is_unresolved_manual_review(JobRepository._to_domain(record))
    ]
    total = len(items)
    return items[offset : offset + limit], total
