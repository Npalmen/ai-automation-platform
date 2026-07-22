"""Build redacted observation payloads for live eval admin routes."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.evaluation.live.delivery import mask_email
from app.evaluation.live.redaction import redact_sensitive
from app.repositories.postgres.decision_record_repository import DecisionRecordRepository
from app.repositories.postgres.live_eval_repository import (
    LiveEvalExternalEventRepository,
    LiveEvalRunRepository,
)
from app.repositories.postgres.job_repository import JobRepository
from app.workflows.approval_service import has_pending_approval
from app.workflows.processors.ai_processor_utils import get_latest_processor_payload

_MAX_EVENTS = 100
_MAX_DECISION_RECORDS = 50
_METADATA_MAX = 256


def _truncate(value: Any, limit: int = _METADATA_MAX) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[: limit - 1] + "…"
    return value


def get_run_summary(db: Session, evaluation_run_id: str, tenant_id: str) -> dict[str, Any]:
    row = LiveEvalRunRepository.get_run(db, evaluation_run_id, tenant_id=tenant_id)
    if row is None:
        return {}
    return {
        "evaluation_run_id": row.evaluation_run_id,
        "tenant_id": row.tenant_id,
        "scenario_id": row.scenario_id,
        "attempt_id": row.attempt_id,
        "transport_mode": row.transport_mode,
        "ai_mode": row.ai_mode,
        "fixture_bundle_id": row.fixture_bundle_id,
        "status": row.status,
        "expected_sender": mask_email(row.expected_sender),
        "expected_recipient": mask_email(row.expected_recipient),
        "root_job_id": row.root_job_id,
        "root_gmail_message_id": row.root_gmail_message_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "config_hash": (row.config_hash or "")[:16],
    }


def list_run_events(
    db: Session,
    evaluation_run_id: str,
    tenant_id: str,
    *,
    limit: int = 50,
) -> list[dict[str, Any]]:
    limit = min(max(1, limit), _MAX_EVENTS)
    rows = LiveEvalExternalEventRepository.list_for_run(
        db,
        evaluation_run_id=evaluation_run_id,
        tenant_id=tenant_id,
    )[:limit]
    return [
        {
            "category": row.category,
            "operation": row.operation,
            "outcome": row.outcome,
            "operation_key": row.operation_key,
            "event_key": row.event_key,
            "integration_type": row.integration_type,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "metadata": {
                k: _truncate(v)
                for k, v in (row.redacted_metadata or {}).items()
            },
        }
        for row in rows
    ]


def build_telemetry_summary(events: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for event in events:
        category = str(event.get("category") or "unknown")
        outcome = str(event.get("outcome") or "")
        key = f"{category}:{outcome}" if outcome else category
        summary[key] = summary.get(key, 0) + 1
    return summary


def build_job_observation(db: Session, tenant_id: str, job_id: str) -> dict[str, Any]:
    job = JobRepository.get_job_by_id(db, tenant_id, job_id)
    if job is None:
        return {}

    classification = get_latest_processor_payload(job, "classification_processor") or {}
    policy = get_latest_processor_payload(job, "policy_processor") or {}

    records = DecisionRecordRepository.list_for_job(db, tenant_id=tenant_id, job_id=job_id)
    decision_rows = []
    for r in records[:_MAX_DECISION_RECORDS]:
        raw_metadata = r.metadata_json or {}
        redacted_metadata = redact_sensitive(raw_metadata)
        if not isinstance(redacted_metadata, dict):
            redacted_metadata = {}
        decision_rows.append(
            {
                "record_type": r.record_type,
                "event_sequence": r.event_sequence,
                "policy_authorization": r.policy_authorization,
                "action_authorization": r.action_authorization,
                "pipeline_run_id": r.pipeline_run_id,
                "metadata": {
                    k: _truncate(v)
                    for k, v in redacted_metadata.items()
                },
            }
        )

    pipeline_run_id = None
    for row in decision_rows:
        if row.get("pipeline_run_id"):
            pipeline_run_id = row["pipeline_run_id"]
            break

    pending = has_pending_approval(job)
    return {
        "job_id": job.job_id,
        "job_type": job.job_type.value if hasattr(job.job_type, "value") else str(job.job_type),
        "job_status": job.status.value if hasattr(job.status, "value") else str(job.status),
        "classification": {
            "detected_job_type": classification.get("detected_job_type"),
            "confidence": classification.get("confidence"),
        },
        "policy": {
            "policy_authorization": policy.get("policy_authorization"),
            "decision": policy.get("decision"),
            "recommended_next_step": policy.get("recommended_next_step"),
        },
        "has_pending_approvals": pending,
        "pending_approval_count": 1 if pending else 0,
        "pipeline_run_id": pipeline_run_id,
        "decision_records": decision_rows,
        "live_eval": _redact_live_eval(job.input_data.get("live_eval") if job.input_data else None),
    }


def _redact_live_eval(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    return {
        "evaluation_run_id": raw.get("evaluation_run_id"),
        "scenario_id": raw.get("scenario_id"),
        "attempt_id": raw.get("attempt_id"),
        "ai_mode": raw.get("ai_mode"),
        "fixture_bundle_id": raw.get("fixture_bundle_id"),
        "trusted": raw.get("trusted"),
        "config_hash": str(raw.get("config_hash") or "")[:16],
    }


def build_full_observation(db: Session, evaluation_run_id: str, tenant_id: str) -> dict[str, Any]:
    run = get_run_summary(db, evaluation_run_id, tenant_id)
    events = list_run_events(db, evaluation_run_id, tenant_id)
    observation: dict[str, Any] = {
        "run": run,
        "telemetry_summary": build_telemetry_summary(events),
        "events": events,
    }
    job_id = run.get("root_job_id")
    if job_id:
        observation["job"] = build_job_observation(db, tenant_id, job_id)
    return observation
