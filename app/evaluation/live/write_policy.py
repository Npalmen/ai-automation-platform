"""Dispatch-boundary write policy for live evaluation."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.evaluation.live.audit import emit_live_eval_audit
from app.evaluation.live.authorization import validate_trusted_live_eval_context
from app.evaluation.live.constants import EVENT_OUTCOME_BLOCKED
from app.evaluation.live.context import get_current_live_eval_snapshot
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.telemetry import (
    build_operation_key,
    record_live_eval_external_event,
    snapshot_from_job,
)
from app.integrations.enums import IntegrationType
from app.integrations.policies import is_external_write_enabled_for_integration

_ALLOWED_REPLY_ACTIONS = frozenset({"send_customer_auto_reply"})


def _normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def _recipient_matches_allowed(target: str, snapshot) -> bool:
    target_norm = _normalize_email(target)
    if not target_norm:
        return False
    expected = _normalize_email(snapshot.expected_sender)
    return target_norm == expected


def enforce_live_eval_write_policy(
    action: dict[str, Any],
    *,
    db: Session | None,
    job=None,
    job_id: str | None = None,
    pipeline_run_id: str | None = None,
    action_operation_id: str | None = None,
) -> None:
    snapshot = get_current_live_eval_snapshot()
    if snapshot is None and job is not None:
        snapshot = snapshot_from_job(job)
    if snapshot is None:
        return

    if db is None:
        raise LiveEvalSafetyError("live_eval write policy requires database session")

    snapshot = validate_trusted_live_eval_context(
        db,
        job=job,
        snapshot=snapshot,
        require_active=True,
    )
    if snapshot is None:
        return

    if (
        snapshot.transport_mode == "fixture_input"
        and snapshot.ai_mode == "live_llm"
    ):
        action_type = str(action.get("type") or "")
        target = action.get("to") or action.get("recipient") or action.get("email")
        reason = f"fixture_input live_llm blocked action {action_type!r}"
        emit_live_eval_audit(
            db,
            tenant_id=snapshot.tenant_id,
            action="safety_rejected",
            status="blocked",
            details={
                "evaluation_run_id": snapshot.evaluation_run_id,
                "action_type": action_type,
                "target": _normalize_email(str(target or ""))[:120],
            },
        )
        operation_key = build_operation_key(
            evaluation_run_id=snapshot.evaluation_run_id,
            category="app_external_write_blocked",
            operation=action_type,
            action_operation_id=action_operation_id,
        )
        record_live_eval_external_event(
            db,
            operation_key=operation_key,
            outcome=EVENT_OUTCOME_BLOCKED,
            category="app_external_write_blocked",
            operation=action_type,
            integration_type=IntegrationType.GOOGLE_MAIL.value,
            target=_normalize_email(str(target or ""))[:120] or None,
            job_id=job_id,
            pipeline_run_id=pipeline_run_id,
            action_operation_id=action_operation_id,
            snapshot=snapshot,
            job_input_data=getattr(job, "input_data", None) if job is not None else None,
            metadata={"reason": reason},
        )
        raise LiveEvalSafetyError(reason)

    if job_id is None and job is not None:
        job_id = getattr(job, "job_id", None)

    action_type = str(action.get("type") or "")
    target = action.get("to") or action.get("recipient") or action.get("email")

    gmail_write_enabled = is_external_write_enabled_for_integration(
        snapshot.tenant_id,
        IntegrationType.GOOGLE_MAIL,
        db=db,
    )

    allowed = (
        action_type in _ALLOWED_REPLY_ACTIONS
        and _recipient_matches_allowed(str(target or ""), snapshot)
        and gmail_write_enabled
    )

    if allowed:
        return

    reason = f"live_eval blocked action {action_type!r}"
    emit_live_eval_audit(
        db,
        tenant_id=snapshot.tenant_id,
        action="safety_rejected",
        status="blocked",
        details={
            "evaluation_run_id": snapshot.evaluation_run_id,
            "action_type": action_type,
            "target": _normalize_email(str(target or ""))[:120],
        },
    )
    operation_key = build_operation_key(
        evaluation_run_id=snapshot.evaluation_run_id,
        category="app_external_write_blocked",
        operation=action_type,
        action_operation_id=action_operation_id,
    )
    record_live_eval_external_event(
        db,
        operation_key=operation_key,
        outcome=EVENT_OUTCOME_BLOCKED,
        category="app_external_write_blocked",
        operation=action_type,
        integration_type=IntegrationType.GOOGLE_MAIL.value,
        target=_normalize_email(str(target or ""))[:120] or None,
        job_id=job_id,
        pipeline_run_id=pipeline_run_id,
        action_operation_id=action_operation_id,
        snapshot=snapshot,
        job_input_data=getattr(job, "input_data", None) if job is not None else None,
        metadata={"reason": reason},
    )
    raise LiveEvalSafetyError(reason)
