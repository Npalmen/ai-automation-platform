"""Exact-message Gmail intake for live eval and shared inbox processing."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.evaluation.live.constants import (
    TELEMETRY_APP_INTAKE_FAILED,
    TELEMETRY_APP_INTAKE_STARTED,
    TELEMETRY_APP_INTAKE_SUCCEEDED,
)
from app.evaluation.live.config import get_live_eval_config
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.intake import resolve_trusted_live_eval_from_message
from app.evaluation.live.recipient_identity import resolve_canonical_recipient_email
from app.evaluation.live.subject_parser import parse_subject_token
from app.evaluation.live.telemetry import build_operation_key, record_live_eval_external_event
from app.integrations.enums import IntegrationType
from app.integrations.factory import get_integration_adapter
from app.integrations.service import get_integration_connection_config
from app.repositories.postgres.job_repository import JobRepository
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from app.workflows.action_executor import execute_action as dispatch_action
from app.workflows.intake_enforcement import evaluate_intake_gate
from app.workflows.manual_review_handoff import post_pipeline_gmail_message_outcome
from app.workflows.pipeline_runner import run_pipeline
from app.workflows.processors.classification_processor import classify_email_type
from app.core.config import get_tenant_config

_INFERRED_TYPE_TO_JOB_TYPE = {
    "lead": JobType.LEAD,
    "customer_inquiry": JobType.CUSTOMER_INQUIRY,
    "invoice": JobType.INVOICE,
}


def _parse_from_header(from_header: str) -> tuple[str, str]:
    from email.utils import parseaddr

    name, email = parseaddr((from_header or "").strip())
    name = name.strip().strip('"').strip()
    email = email.strip().lower()
    if name and name.lower() == email:
        name = ""
    return name, email


def _clean_gmail_subject(subject: str) -> str:
    import re

    _GMAIL_UI_NOISE_RE = re.compile(
        r"(?:klicka|kilcka)\s+för\s+att\s+informera\s+gmail\s+om\s+att\s+den\s+här\s+konversationen\s+är\s+viktig",
        re.IGNORECASE,
    )
    cleaned = (subject or "").strip()
    if not cleaned:
        return cleaned
    cleaned = _GMAIL_UI_NOISE_RE.sub("", cleaned).strip()
    return cleaned


def process_gmail_message_by_id(
    db: Session,
    tenant_id: str,
    message_id: str,
    *,
    dry_run: bool = False,
    intake_query: str | None = None,
    live_eval_run_id: str | None = None,
    skip_slack_notify: bool = False,
) -> dict[str, Any]:
    """
    Process exactly one Gmail message by ID through the standard intake chain.
    Used by live-eval process-delivery and may be called from inbox sync.
    """
    query_used = intake_query or f"label:krowolf-live-eval"

    connection_config = get_integration_connection_config(
        tenant_id=tenant_id,
        integration_type=IntegrationType.GOOGLE_MAIL,
        db=db,
    )
    config = get_live_eval_config()
    canonical_recipient, identity_error = resolve_canonical_recipient_email(
        connection_config,
        metadata=connection_config.get("metadata_json") or {},
        allowlist=config.recipient_emails,
    )
    if identity_error:
        return {
            "status": "failed",
            "message_id": message_id,
            "reason": identity_error,
            "safety_reason": identity_error,
        }
    adapter = get_integration_adapter(
        integration_type=IntegrationType.GOOGLE_MAIL,
        connection_config=connection_config,
    )

    existing_by_msg = JobRepository.get_by_gmail_message_id(db, tenant_id, message_id)
    if existing_by_msg is not None:
        return {
            "status": "skipped",
            "message_id": message_id,
            "reason": "duplicate",
            "job_id": existing_by_msg.job_id,
        }

    try:
        detail_result = adapter.execute_action(
            action="get_message",
            payload={"message_id": message_id},
        )
    except (ValueError, RuntimeError) as exc:
        return {"status": "failed", "message_id": message_id, "reason": str(exc)}

    msg = detail_result.get("message") or {}
    tenant_row = (
        db.query(TenantConfigRecord)
        .filter(TenantConfigRecord.tenant_id == tenant_id)
        .first()
    )
    lifecycle_status = getattr(tenant_row, "lifecycle_status", None) or "active"
    intake_settings = (tenant_row.settings or {}).get("intake") if tenant_row else {}
    internal_date = msg.get("internal_date_ms") or msg.get("internal_date")
    intake_gate = evaluate_intake_gate(
        tenant_id=tenant_id,
        lifecycle_status=lifecycle_status,
        intake_settings=intake_settings,
        message_internal_date_ms=internal_date,
    )
    if not intake_gate.get("allowed"):
        return {
            "status": "skipped",
            "message_id": message_id,
            "reason": intake_gate.get("reason"),
        }

    sender_name, sender_email = _parse_from_header(msg.get("from", ""))
    subject = _clean_gmail_subject(msg.get("subject") or "(no subject)")
    body_text = msg.get("body_text") or ""
    thread_id = msg.get("thread_id") or ""

    tenant_config = get_tenant_config(tenant_id, db=db)
    enabled_job_types = set(tenant_config.get("enabled_job_types") or [])

    inferred_type = classify_email_type(subject, body_text)
    if inferred_type not in enabled_job_types:
        return {
            "status": "skipped",
            "message_id": message_id,
            "reason": f"{inferred_type}_disabled",
        }

    job_type = _INFERRED_TYPE_TO_JOB_TYPE[inferred_type]
    sender_dict = {"name": sender_name, "email": sender_email}

    input_data = {
        "subject": subject,
        "message_text": body_text,
        "sender": sender_dict,
        "source": {
            "system": "gmail",
            "message_id": message_id,
            "thread_id": thread_id,
            "internet_message_id": msg.get("internet_message_id") or "",
        },
        "received_at": msg.get("received_at") or None,
    }

    snapshot_for_telemetry = None
    if parse_subject_token(subject) is not None:
        try:
            live_eval_snapshot = resolve_trusted_live_eval_from_message(
                db,
                tenant_id=tenant_id,
                subject=subject,
                sender_email=sender_email,
                recipient_email=canonical_recipient or "",
                query=query_used,
            )
            if live_eval_snapshot is not None:
                input_data["live_eval"] = live_eval_snapshot.model_dump(mode="json")
                snapshot_for_telemetry = live_eval_snapshot
                if live_eval_run_id and live_eval_snapshot.evaluation_run_id != live_eval_run_id:
                    raise LiveEvalSafetyError("live_eval_run_id mismatch")
        except LiveEvalSafetyError as exc:
            _record_intake_telemetry(
                db,
                snapshot=snapshot_for_telemetry,
                outcome="failed",
                job_id=None,
                message_id=message_id,
            )
            return {
                "status": "failed",
                "message_id": message_id,
                "reason": f"live_eval_safety:{exc}",
            }

    if dry_run:
        return {
            "status": "dry_run",
            "message_id": message_id,
            "inferred_type": inferred_type,
        }

    _record_intake_telemetry(
        db,
        snapshot=snapshot_for_telemetry,
        outcome="started",
        job_id=None,
        message_id=message_id,
    )

    job = Job(tenant_id=tenant_id, job_type=job_type, input_data=input_data)

    try:
        if isinstance(input_data.get("live_eval"), dict):
            from app.evaluation.live.registry import create_and_claim_live_eval_root_job

            saved_job = create_and_claim_live_eval_root_job(
                db,
                job=job,
                evaluation_run_id=input_data["live_eval"]["evaluation_run_id"],
                tenant_id=tenant_id,
                root_gmail_message_id=message_id,
            )
        else:
            saved_job = JobRepository.create_job(db, job)
        processed_job = run_pipeline(saved_job, db)
    except Exception as exc:
        _record_intake_telemetry(
            db,
            snapshot=snapshot_for_telemetry,
            outcome="failed",
            job_id=None,
            message_id=message_id,
        )
        return {"status": "failed", "message_id": message_id, "reason": str(exc)}

    outcome = post_pipeline_gmail_message_outcome(
        db, tenant_id, processed_job, message_id, adapter
    )

    notified = False
    if not skip_slack_notify:
        try:
            dispatch_action({
                "type": "notify_slack",
                "tenant_id": tenant_id,
                "channel": "#inbox",
                "message": f"New {inferred_type} job {processed_job.job_id} from Gmail",
            })
            notified = True
        except Exception:
            notified = False

    pipeline_run_id = _extract_pipeline_run_id(processed_job)
    _record_intake_telemetry(
        db,
        snapshot=snapshot_for_telemetry,
        outcome="succeeded",
        job_id=processed_job.job_id,
        message_id=message_id,
        pipeline_run_id=pipeline_run_id,
    )

    return {
        "status": "created",
        "message_id": message_id,
        "job_id": processed_job.job_id,
        "inferred_type": inferred_type,
        "job_status": (
            processed_job.status.value
            if hasattr(processed_job.status, "value")
            else str(processed_job.status)
        ),
        "pipeline_run_id": pipeline_run_id,
        "marked_handled": outcome.get("marked_handled", False),
        "notified": notified,
    }


def _extract_pipeline_run_id(job) -> str | None:
    from app.workflows.processors.ai_processor_utils import get_latest_processor_payload

    for processor in ("policy_processor", "classification_processor"):
        payload = get_latest_processor_payload(job, processor) or {}
        if payload.get("pipeline_run_id"):
            return str(payload["pipeline_run_id"])
    records = (job.result or {}).get("processor_history") or []
    for entry in records:
        payload = (entry or {}).get("payload") or {}
        if payload.get("pipeline_run_id"):
            return str(payload["pipeline_run_id"])
    return None


def _record_intake_telemetry(
    db: Session,
    *,
    snapshot,
    outcome: str,
    job_id: str | None,
    message_id: str,
    pipeline_run_id: str | None = None,
) -> None:
    if snapshot is None:
        return
    category = {
        "started": TELEMETRY_APP_INTAKE_STARTED,
        "succeeded": TELEMETRY_APP_INTAKE_SUCCEEDED,
        "failed": TELEMETRY_APP_INTAKE_FAILED,
    }.get(outcome)
    if category is None:
        return
    event_outcome = "succeeded" if outcome == "succeeded" else (
        "failed" if outcome == "failed" else "blocked"
    )
    operation_key = build_operation_key(
        evaluation_run_id=snapshot.evaluation_run_id,
        category=category,
        operation=message_id,
    )
    record_live_eval_external_event(
        db,
        operation_key=operation_key,
        outcome=event_outcome,
        category=category,
        operation=message_id,
        integration_type=IntegrationType.GOOGLE_MAIL.value,
        job_id=job_id,
        pipeline_run_id=pipeline_run_id,
        snapshot=snapshot,
        metadata={"message_id": message_id},
    )
    if outcome in ("started", "succeeded", "failed"):
        db.commit()
