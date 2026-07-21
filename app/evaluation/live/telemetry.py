"""Persistent idempotent external event telemetry for live evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.evaluation.live.constants import EVENT_OUTCOME_SUCCEEDED
from app.evaluation.live.context import get_current_live_eval_snapshot
from app.evaluation.live.schemas import TrustedLiveEvalSnapshot
from app.evaluation.live.redaction import redact_sensitive
from app.repositories.postgres.live_eval_models import LiveEvalExternalEventRow
from app.repositories.postgres.live_eval_repository import LiveEvalExternalEventRepository

_REDACT_MAX_STRING_LEN = 256


def _redact_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    redacted = redact_sensitive(metadata)
    if not isinstance(redacted, dict):
        return {}
    out: dict[str, Any] = {}
    for key, value in redacted.items():
        if isinstance(value, str) and len(value) > _REDACT_MAX_STRING_LEN:
            out[key] = value[:_REDACT_MAX_STRING_LEN] + "…"
        else:
            out[key] = value
    return out


def _resolve_snapshot(
    snapshot: TrustedLiveEvalSnapshot | None,
    *,
    job_input_data: dict | None = None,
) -> TrustedLiveEvalSnapshot | None:
    if snapshot is not None:
        return snapshot
    if isinstance(job_input_data, dict):
        raw = job_input_data.get("live_eval")
        if isinstance(raw, dict) and raw.get("trusted"):
            return TrustedLiveEvalSnapshot.model_validate(raw)
    return get_current_live_eval_snapshot()


def snapshot_from_job(job) -> TrustedLiveEvalSnapshot | None:
    input_data = getattr(job, "input_data", None)
    return _resolve_snapshot(None, job_input_data=input_data)


def build_operation_key(
    *,
    evaluation_run_id: str,
    category: str,
    operation: str,
    action_operation_id: str | None = None,
) -> str:
    suffix = action_operation_id or "unknown"
    return f"{evaluation_run_id}:{category}:{operation}:{suffix}"


def build_event_key(*, operation_key: str, outcome: str, attempt: int = 1) -> str:
    if outcome == EVENT_OUTCOME_SUCCEEDED:
        return f"{operation_key}:succeeded"
    return f"{operation_key}:{outcome}:{attempt}"


def operation_already_succeeded(db: Session, operation_key: str) -> bool:
    return LiveEvalExternalEventRepository.has_succeeded_operation(db, operation_key)


def record_live_eval_external_event(
    db: Session,
    *,
    operation_key: str,
    outcome: str,
    category: str,
    operation: str,
    integration_type: str,
    target: str | None = None,
    job_id: str | None = None,
    pipeline_run_id: str | None = None,
    action_operation_id: str | None = None,
    snapshot: TrustedLiveEvalSnapshot | None = None,
    job_input_data: dict | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
    attempt: int | None = None,
) -> bool:
    snap = _resolve_snapshot(snapshot, job_input_data=job_input_data)
    if snap is None:
        return False

    if attempt is None:
        if outcome == "failed":
            attempt = (
                LiveEvalExternalEventRepository.count_failed_attempts(db, operation_key) + 1
            )
        else:
            attempt = 1

    event_key = build_event_key(
        operation_key=operation_key, outcome=outcome, attempt=attempt
    )
    event = LiveEvalExternalEventRow(
        event_key=event_key,
        operation_key=operation_key,
        evaluation_run_id=snap.evaluation_run_id,
        tenant_id=snap.tenant_id,
        job_id=job_id,
        pipeline_run_id=pipeline_run_id,
        action_operation_id=action_operation_id,
        integration_type=integration_type,
        category=category,
        operation=operation,
        target=target,
        outcome=outcome,
        started_at=started_at or datetime.now(timezone.utc),
        completed_at=completed_at,
        redacted_metadata=_redact_metadata(metadata),
    )
    return LiveEvalExternalEventRepository.record_event(db, event)
