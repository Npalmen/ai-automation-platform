"""
Admin recovery actions for failed/stuck workflow jobs.

All actions:
  - Require caller to verify admin auth before calling (endpoints handle this).
  - Verify the job belongs to the stated tenant_id (tenant isolation).
  - Emit an audit event with category="recovery" for every action taken.
  - Return a consistent {status, action, job_id, tenant_id, message, details} shape.
  - Never expose raw exception text in the "message" field (log server-side).

Supported actions
-----------------
retry_job               – reset failed job state and rerun the full pipeline
replay_dispatch         – replay controlled dispatch only (idempotency protects against duplication)
reclassify              – overwrite the classification processor history entry, rerun from classification
re_extract              – overwrite entity_extraction processor history entry, rerun that step alone
resend_approval         – clear stale approval delivery metadata so it is re-dispatched
reprocess_gmail_source  – force-continue an existing job from its stored Gmail source message
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.audit_service import create_audit_event
from app.core.config import get_tenant_config
from app.core.settings import get_settings
from app.integrations.google.adapter import GoogleMailAdapter
from app.integrations.service import get_integration_connection_config
from app.repositories.postgres.approval_repository import ApprovalRequestRepository
from app.repositories.postgres.job_repository import JobRepository
from app.repositories.postgres.job_models import JobRecord
from app.domain.workflows.enums import JobType
from app.domain.workflows.statuses import JobStatus
from app.domain.workflows.models import Job
from app.workflows.approval_dispatcher import dispatch_approval_request
from app.workflows.dispatchers.engine import ControlledDispatchEngine
from app.workflows.pipeline_runner import run_pipeline
from app.workflows.pipeline_run_context import PipelineRunSource, create_trace_session
from app.repositories.postgres.decision_record_repository import DecisionRecordRepository
from app.workflows.decision_record_service import record_operator_recovery

logger = logging.getLogger(__name__)

_ACTION_CATEGORY = "recovery"


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------

def _ok(action: str, job_id: str, tenant_id: str, message: str, details: dict | None = None) -> dict:
    return {
        "status": "success",
        "action": action,
        "job_id": job_id,
        "tenant_id": tenant_id,
        "message": message,
        "details": details or {},
    }


def _fail(action: str, job_id: str, tenant_id: str, message: str, details: dict | None = None) -> dict:
    return {
        "status": "failed",
        "action": action,
        "job_id": job_id,
        "tenant_id": tenant_id,
        "message": message,
        "details": details or {},
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_job(db: Session, tenant_id: str, job_id: str) -> Job | None:
    return JobRepository.get_job_by_id(db, tenant_id, job_id)


def _latest_pipeline_run_id(db: Session, tenant_id: str, job_id: str) -> str | None:
    rows = DecisionRecordRepository.list_for_job(db, tenant_id=tenant_id, job_id=job_id)
    if not rows:
        return None
    return rows[-1].pipeline_run_id


class RecoveryAuditError(Exception):
    """Raised when recovery audit write fails (fail-closed)."""


def _audit(db: Session, tenant_id: str, action: str, status: str, details: dict) -> None:
    try:
        create_audit_event(
            db=db,
            tenant_id=tenant_id,
            category=_ACTION_CATEGORY,
            action=action,
            status=status,
            details=details,
        )
    except Exception as exc:
        logger.exception("Failed to write recovery audit event for %s/%s", tenant_id, action)
        raise RecoveryAuditError("recovery audit write failed") from exc


def _strip_processor_history_entry(job: Job, processor_name: str) -> Job:
    """Remove the most recent history entry for the given processor."""
    new_history = [
        entry for entry in job.processor_history
        if entry.get("processor") != processor_name
    ]
    updated = job.model_copy(deep=True)
    updated.processor_history = new_history
    return updated


# ---------------------------------------------------------------------------
# Action 1: Retry failed job — full pipeline rerun
# ---------------------------------------------------------------------------

def retry_job(db: Session, tenant_id: str, job_id: str, actor: str = "admin") -> dict[str, Any]:
    """
    Reset a failed job's state and rerun it through the complete pipeline.

    Preserves tenant context, input_data, and existing audit history.
    Adds a recovery audit event before re-running.
    """
    action_name = "retry_job"

    job = _load_job(db, tenant_id, job_id)
    if job is None:
        return _fail(action_name, job_id, tenant_id, "Job not found or does not belong to this tenant.")

    if job.status not in (JobStatus.FAILED, JobStatus.MANUAL_REVIEW):
        return _fail(
            action_name, job_id, tenant_id,
            f"Job status is '{job.status}' — only failed or manual_review jobs can be retried.",
            {"current_status": str(job.status)},
        )

    _audit(db, tenant_id, action_name, "initiated", {
        "job_id": job_id,
        "actor": actor,
        "previous_status": str(job.status),
    })

    parent_run_id = _latest_pipeline_run_id(db, tenant_id, job_id)
    recovery_trace = create_trace_session(
        job,
        source=PipelineRunSource.RETRY,
        db=db,
        parent_pipeline_run_id=parent_run_id,
    )
    record_operator_recovery(
        db,
        recovery_trace,
        job,
        operator_action=action_name,
        operator_actor=actor,
    )

    # Clear failure state so the pipeline runs fresh; preserve input_data and audit trail.
    job.status = JobStatus.PENDING
    job.result = None
    job.processor_history = []
    job.updated_at = _utcnow()

    try:
        updated_job = run_pipeline(
            job,
            db,
            run_source=PipelineRunSource.RETRY,
            parent_pipeline_run_id=parent_run_id,
        )
    except Exception as exc:
        logger.exception("retry_job pipeline error for job %s", job_id)
        _audit(db, tenant_id, action_name, "failed", {"job_id": job_id, "error": "pipeline_error"})
        return _fail(action_name, job_id, tenant_id, "Pipeline rerun failed. See server logs for details.")

    _audit(db, tenant_id, action_name, "success", {
        "job_id": job_id,
        "actor": actor,
        "new_status": str(updated_job.status),
    })

    return _ok(action_name, job_id, tenant_id, "Job re-queued and pipeline rerun successfully.", {
        "new_status": str(updated_job.status),
    })


# ---------------------------------------------------------------------------
# Action 2: Replay dispatch — controlled dispatch only
# ---------------------------------------------------------------------------

def replay_dispatch(db: Session, tenant_id: str, job_id: str, actor: str = "admin") -> dict[str, Any]:
    """
    Replay only the controlled dispatch step for a job.

    The dispatch engine's idempotency guard prevents re-sending to the same
    external target when a successful dispatch already exists.
    """
    action_name = "replay_dispatch"

    job = _load_job(db, tenant_id, job_id)
    if job is None:
        return _fail(action_name, job_id, tenant_id, "Job not found or does not belong to this tenant.")

    _audit(db, tenant_id, action_name, "initiated", {"job_id": job_id, "actor": actor})

    try:
        app_settings = get_settings()
        tenant_config = get_tenant_config(tenant_id, db)
        s = tenant_config.get("settings") or {}
        memory = s.get("memory") or {}

        engine = ControlledDispatchEngine(db, tenant_id, app_settings)

        # Use the record version of the job so the engine can read job_type as string
        record = (
            db.query(JobRecord)
            .filter(JobRecord.tenant_id == tenant_id, JobRecord.job_id == job_id)
            .first()
        )
        if record is None:
            return _fail(action_name, job_id, tenant_id, "Job record not found.")

        result = engine.run(record, memory, dry_run=False, dispatch_mode="admin_replay", tenant_settings=s)
    except Exception as exc:
        logger.exception("replay_dispatch error for job %s", job_id)
        _audit(db, tenant_id, action_name, "failed", {"job_id": job_id, "error": "dispatch_error"})
        return _fail(action_name, job_id, tenant_id, "Dispatch replay failed. See server logs.")

    _audit(db, tenant_id, action_name, result.status, {
        "job_id": job_id,
        "actor": actor,
        "dispatch_status": result.status,
        "message": result.message,
    })

    if result.status == "failed":
        return _fail(action_name, job_id, tenant_id, result.message or "Dispatch failed.", {
            "dispatch_status": result.status,
        })

    return _ok(action_name, job_id, tenant_id, result.message or "Dispatch replayed.", {
        "dispatch_status": result.status,
        "system": result.system,
        "external_id": result.external_id,
    })


# ---------------------------------------------------------------------------
# Action 3: Re-run classification
# ---------------------------------------------------------------------------

def reclassify(db: Session, tenant_id: str, job_id: str, actor: str = "admin") -> dict[str, Any]:
    """
    Overwrite the prior classification result and re-run the full pipeline from classification.

    Overwrites derived state; writes an audit event with actor annotation.
    """
    action_name = "reclassify"

    job = _load_job(db, tenant_id, job_id)
    if job is None:
        return _fail(action_name, job_id, tenant_id, "Job not found or does not belong to this tenant.")

    _audit(db, tenant_id, action_name, "initiated", {
        "job_id": job_id,
        "actor": actor,
        "note": "Overwriting prior classification state",
    })

    parent_run_id = _latest_pipeline_run_id(db, tenant_id, job_id)
    recovery_trace = create_trace_session(
        job,
        source=PipelineRunSource.RECLASSIFY,
        db=db,
        parent_pipeline_run_id=parent_run_id,
    )
    record_operator_recovery(
        db,
        recovery_trace,
        job,
        operator_action=action_name,
        operator_actor=actor,
    )

    # Strip all derived state — rerun from intake/classification
    job.status = JobStatus.PENDING
    job.result = None
    job.processor_history = []
    job.updated_at = _utcnow()

    try:
        updated_job = run_pipeline(
            job,
            db,
            run_source=PipelineRunSource.RECLASSIFY,
            parent_pipeline_run_id=parent_run_id,
        )
    except Exception:
        logger.exception("reclassify pipeline error for job %s", job_id)
        _audit(db, tenant_id, action_name, "failed", {"job_id": job_id, "error": "pipeline_error"})
        return _fail(action_name, job_id, tenant_id, "Reclassification pipeline failed. See server logs.")

    _audit(db, tenant_id, action_name, "success", {
        "job_id": job_id,
        "actor": actor,
        "new_status": str(updated_job.status),
    })

    # Extract the new detected type from processor history
    detected_type = "unknown"
    for entry in reversed(updated_job.processor_history):
        if entry.get("processor") == "classification_processor":
            payload = (entry.get("result") or {}).get("payload") or {}
            detected_type = payload.get("detected_job_type", "unknown")
            break

    return _ok(action_name, job_id, tenant_id, "Classification re-run and pipeline restarted.", {
        "new_status": str(updated_job.status),
        "detected_job_type": detected_type,
    })


# ---------------------------------------------------------------------------
# Action 4: Re-run entity extraction
# ---------------------------------------------------------------------------

def re_extract(db: Session, tenant_id: str, job_id: str, actor: str = "admin") -> dict[str, Any]:
    """
    Remove the prior entity_extraction_processor result and re-run from that step.

    Classification result is preserved; only extraction state is cleared and re-run.
    """
    action_name = "re_extract"

    job = _load_job(db, tenant_id, job_id)
    if job is None:
        return _fail(action_name, job_id, tenant_id, "Job not found or does not belong to this tenant.")

    # Check that classification has already run
    has_classification = any(
        e.get("processor") == "classification_processor"
        for e in job.processor_history
    )
    if not has_classification:
        return _fail(
            action_name, job_id, tenant_id,
            "Cannot re-run extraction: classification has not run yet. Try retry_job instead.",
        )

    _audit(db, tenant_id, action_name, "initiated", {
        "job_id": job_id,
        "actor": actor,
        "note": "Overwriting entity_extraction state only",
    })

    # Strip extraction and all downstream steps; keep intake + classification
    keep_processors = {"intake_processor", "classification_processor"}
    updated_job = job.model_copy(deep=True)
    updated_job.processor_history = [
        e for e in updated_job.processor_history
        if e.get("processor") in keep_processors
    ]
    updated_job.result = None
    updated_job.status = JobStatus.PENDING
    updated_job.updated_at = _utcnow()

    try:
        final_job = run_pipeline(updated_job, db)
    except Exception:
        logger.exception("re_extract pipeline error for job %s", job_id)
        _audit(db, tenant_id, action_name, "failed", {"job_id": job_id, "error": "pipeline_error"})
        return _fail(action_name, job_id, tenant_id, "Entity extraction rerun failed. See server logs.")

    _audit(db, tenant_id, action_name, "success", {
        "job_id": job_id,
        "actor": actor,
        "new_status": str(final_job.status),
    })

    return _ok(action_name, job_id, tenant_id, "Entity extraction re-run completed.", {
        "new_status": str(final_job.status),
    })


# ---------------------------------------------------------------------------
# Action 5: Resend approval notification
# ---------------------------------------------------------------------------

def resend_approval(db: Session, tenant_id: str, job_id: str, actor: str = "admin") -> dict[str, Any]:
    """
    Clear the stale approval_delivery metadata on the latest pending approval so it
    is re-dispatched via dispatch_approval_request without creating duplicate approval records.
    """
    action_name = "resend_approval"

    job = _load_job(db, tenant_id, job_id)
    if job is None:
        return _fail(action_name, job_id, tenant_id, "Job not found or does not belong to this tenant.")

    # Find the latest pending approval for this job
    pending = ApprovalRequestRepository.get_latest_for_job(db, tenant_id, job_id)
    if pending is None or pending.state != "pending":
        return _fail(
            action_name, job_id, tenant_id,
            "No pending approval found for this job. Nothing to resend.",
        )

    _audit(db, tenant_id, action_name, "initiated", {
        "job_id": job_id,
        "actor": actor,
        "approval_id": pending.approval_id,
    })

    # Clear delivery metadata from the approval dispatcher's processor history entry
    # so dispatch_approval_request will re-deliver
    updated_history = []
    for entry in job.processor_history:
        if entry.get("processor") == "approval_dispatcher":
            modified = dict(entry)
            result = dict(modified.get("result") or {})
            payload = dict(result.get("payload") or {})
            payload.pop("approval_delivery", None)
            result["payload"] = payload
            modified["result"] = result
            updated_history.append(modified)
        else:
            updated_history.append(entry)

    job.processor_history = updated_history
    job.updated_at = _utcnow()
    updated_job = JobRepository.update_job(db, job)

    # Re-dispatch the approval notification
    try:
        final_job = dispatch_approval_request(db, updated_job)
    except Exception:
        logger.exception("resend_approval dispatch error for job %s", job_id)
        _audit(db, tenant_id, action_name, "failed", {
            "job_id": job_id,
            "approval_id": pending.approval_id,
            "error": "dispatch_error",
        })
        return _fail(action_name, job_id, tenant_id, "Approval resend failed. See server logs.")

    _audit(db, tenant_id, action_name, "success", {
        "job_id": job_id,
        "actor": actor,
        "approval_id": pending.approval_id,
    })

    return _ok(action_name, job_id, tenant_id, "Approval notification resent.", {
        "approval_id": pending.approval_id,
    })


# ---------------------------------------------------------------------------
# Action 6: Reprocess Gmail source message
# ---------------------------------------------------------------------------

def reprocess_gmail_source(
    db: Session,
    tenant_id: str,
    job_id: str,
    actor: str = "admin",
    force: bool = False,
) -> dict[str, Any]:
    """
    Re-ingest the original Gmail message attached to this job.

    Uses the thread continuation path to update the existing job instead of
    creating a duplicate case.  Requires `input_data.source.system == "gmail"`
    and `input_data.source.message_id` to be present.

    When force=True the dedup check is bypassed so the message is always re-fetched.
    """
    action_name = "reprocess_gmail_source"

    job = _load_job(db, tenant_id, job_id)
    if job is None:
        return _fail(action_name, job_id, tenant_id, "Job not found or does not belong to this tenant.")

    source = (job.input_data or {}).get("source") or {}
    if source.get("system") != "gmail":
        return _fail(
            action_name, job_id, tenant_id,
            "Job was not sourced from Gmail — cannot reprocess Gmail source.",
            {"source_system": source.get("system")},
        )

    message_id = source.get("message_id")
    if not message_id:
        return _fail(
            action_name, job_id, tenant_id,
            "No Gmail message_id found in job source metadata.",
        )

    _audit(db, tenant_id, action_name, "initiated", {
        "job_id": job_id,
        "actor": actor,
        "message_id": message_id,
        "force": force,
    })

    # Fetch the original message from Gmail
    try:
        app_settings = get_settings()
        connection_config = get_integration_connection_config("google_mail", app_settings)
        if connection_config is None:
            return _fail(action_name, job_id, tenant_id, "Gmail integration not configured for this server.")

        adapter = GoogleMailAdapter(connection_config)
        msg_result = adapter.execute_action("get_message", {"message_id": message_id})
    except Exception:
        logger.exception("reprocess_gmail_source: failed to fetch message %s", message_id)
        _audit(db, tenant_id, action_name, "failed", {"job_id": job_id, "error": "gmail_fetch_error"})
        return _fail(action_name, job_id, tenant_id, "Failed to fetch message from Gmail. See server logs.")

    # Build continuation update — append new message and re-run pipeline
    conversation_messages = list(job.input_data.get("conversation_messages") or [])
    new_message = {
        "from": msg_result.get("from"),
        "subject": msg_result.get("subject"),
        "body": msg_result.get("body_text", ""),
        "received_at": msg_result.get("received_at"),
        "source": "gmail_reprocess",
        "reprocessed_by": actor,
    }
    conversation_messages.append(new_message)

    updated_input = dict(job.input_data or {})
    updated_input["conversation_messages"] = conversation_messages
    updated_input["latest_message_text"] = msg_result.get("body_text", "")

    job.input_data = updated_input
    job.processor_history = []
    job.result = None
    job.status = JobStatus.PENDING
    job.updated_at = _utcnow()

    try:
        final_job = run_pipeline(job, db)
    except Exception:
        logger.exception("reprocess_gmail_source pipeline error for job %s", job_id)
        _audit(db, tenant_id, action_name, "failed", {"job_id": job_id, "error": "pipeline_error"})
        return _fail(action_name, job_id, tenant_id, "Pipeline rerun after Gmail reprocess failed. See server logs.")

    _audit(db, tenant_id, action_name, "success", {
        "job_id": job_id,
        "actor": actor,
        "message_id": message_id,
        "new_status": str(final_job.status),
    })

    return _ok(action_name, job_id, tenant_id, "Gmail source message reprocessed and pipeline re-run.", {
        "message_id": message_id,
        "new_status": str(final_job.status),
    })
