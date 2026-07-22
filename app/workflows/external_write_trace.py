"""Two-phase external write trace and anti-auto-retry guard."""

from __future__ import annotations

import logging
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.settings import resolve_decision_record_enforce_writes
from app.repositories.postgres.decision_record_repository import DecisionRecordRepository
from app.workflows.action_authorization import ActionEffect, classify_action
from app.workflows.action_fingerprint import compute_action_fingerprint
from app.workflows.decision_record import ExecutionStatus
from app.workflows.decision_record_service import (
    record_action_authorization,
    record_execution_intent,
    record_execution_outcome,
)
from app.workflows.decision_trace_errors import ExternalWriteBlocked, ReconciliationRequired
from app.workflows.pipeline_run_context import DecisionTraceSession

logger = logging.getLogger(__name__)

_UNRESOLVED_STATUSES = frozenset({
    ExecutionStatus.PENDING.value,
    ExecutionStatus.OUTCOME_UNKNOWN.value,
    ExecutionStatus.RECONCILIATION_REQUIRED.value,
})


def _is_external_write(action_type: str | None) -> bool:
    spec = classify_action(action_type)
    return spec is not None and spec.effect == ActionEffect.EXTERNAL_WRITE


def _operation_state(db: Session, tenant_id: str, operation_id: str) -> str | None:
    return DecisionRecordRepository.latest_operation_state(
        db,
        tenant_id=tenant_id,
        action_operation_id=operation_id,
    )


def _live_eval_category_for_action(action_type: str | None) -> str:
    if action_type in ("send_customer_auto_reply", "send_email", "send_internal_handoff"):
        return "app_gmail_reply"
    if action_type == "create_monday_item":
        return "app_monday"
    return "app_other_external"


def _live_eval_integration_type(action_type: str | None) -> str:
    if action_type in ("send_customer_auto_reply", "send_email", "send_internal_handoff"):
        return "google_mail"
    if action_type == "create_monday_item":
        return "monday"
    return "other"


def execute_external_write_with_trace(
    *,
    db: Session | None,
    trace: DecisionTraceSession | None,
    job,
    action: dict[str, Any],
    adapter_fn: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Persist intent before adapter; block automatic retry when outcome is unresolved."""
    action_type = action.get("type")
    if not _is_external_write(action_type):
        return adapter_fn()

    enforce = resolve_decision_record_enforce_writes()
    operation_id = action.get("_action_operation_id")
    fingerprint, key_version = compute_action_fingerprint(action)
    if fingerprint:
        action["_action_fingerprint"] = fingerprint

    if db is None:
        if enforce:
            raise ExternalWriteBlocked("database session required for external write trace")
        return adapter_fn()

    if not operation_id and trace is not None:
        auth = str(action.get("_authorization") or "execution_allowed")
        operation_id = record_action_authorization(db, trace, job, action, authorization=auth)

    if not operation_id:
        if enforce:
            raise ExternalWriteBlocked("missing action_operation_id for external write")
        return adapter_fn()

    state = _operation_state(db, job.tenant_id, operation_id)
    if state == ExecutionStatus.SUCCEEDED.value:
        return {
            "type": action_type,
            "status": "executed",
            "idempotent": True,
            "action_operation_id": operation_id,
        }

    live_eval_snap = None
    live_eval_operation_key = None
    if db is not None and job is not None:
        from app.evaluation.live.telemetry import (
            build_operation_key,
            operation_already_succeeded,
            record_live_eval_external_event,
            snapshot_from_job,
        )

        live_eval_snap = snapshot_from_job(job)
        if live_eval_snap is not None:
            category = _live_eval_category_for_action(action_type)
            live_eval_operation_key = build_operation_key(
                evaluation_run_id=live_eval_snap.evaluation_run_id,
                category=category,
                operation=str(action_type or "unknown"),
                action_operation_id=operation_id,
            )
            if operation_already_succeeded(db, live_eval_operation_key):
                return {
                    "type": action_type,
                    "status": "executed",
                    "idempotent": True,
                    "action_operation_id": operation_id,
                    "live_eval_telemetry": True,
                }

    if state in _UNRESOLVED_STATUSES:
        if state == ExecutionStatus.PENDING.value and action.get("_execute_after_intent_commit"):
            pass
        else:
            raise ReconciliationRequired(
                f"action_operation_id {operation_id} blocks automatic adapter retry (state={state})"
            )

    if state != ExecutionStatus.PENDING.value:
        record_execution_intent(
            db,
            trace,
            job,
            action,
            operation_id=operation_id,
            fingerprint=fingerprint,
            key_version=key_version,
        )

    try:
        result = adapter_fn()
    except Exception as exc:
        if db is not None and live_eval_snap is not None and live_eval_operation_key:
            from app.evaluation.live.telemetry import record_live_eval_external_event

            record_live_eval_external_event(
                db,
                operation_key=live_eval_operation_key,
                outcome="failed",
                category=_live_eval_category_for_action(action_type),
                operation=str(action_type or "unknown"),
                integration_type=_live_eval_integration_type(action_type),
                job_id=getattr(job, "job_id", None),
                pipeline_run_id=trace.pipeline_run.pipeline_run_id if trace else None,
                action_operation_id=operation_id,
                snapshot=live_eval_snap,
                job_input_data=getattr(job, "input_data", None),
                metadata={"error_class": type(exc).__name__},
            )
        record_execution_outcome(
            db,
            trace,
            job,
            action,
            operation_id=operation_id,
            fingerprint=fingerprint,
            key_version=key_version,
            status=ExecutionStatus.FAILED,
            metadata={"error_class": type(exc).__name__},
        )
        raise

    try:
        record_execution_outcome(
            db,
            trace,
            job,
            action,
            operation_id=operation_id,
            fingerprint=fingerprint,
            key_version=key_version,
            status=ExecutionStatus.SUCCEEDED,
            metadata={"adapter_status": str(result.get("status"))},
        )
    except Exception as persist_exc:
        logger.error(
            "execution outcome persist failed for operation %s: %s",
            operation_id,
            persist_exc,
            exc_info=True,
        )
        try:
            record_execution_outcome(
                db,
                trace,
                job,
                action,
                operation_id=operation_id,
                fingerprint=fingerprint,
                key_version=key_version,
                status=ExecutionStatus.OUTCOME_UNKNOWN,
                metadata={"reconciliation_required": True, "error_class": type(persist_exc).__name__},
            )
        except Exception:
            pass
        raise ReconciliationRequired(
            f"adapter may have succeeded but outcome not persisted for {operation_id}"
        ) from persist_exc

    if db is not None and live_eval_snap is not None and live_eval_operation_key:
        from app.evaluation.live.constants import EVENT_OUTCOME_SUCCEEDED
        from app.evaluation.live.telemetry import record_live_eval_external_event

        record_live_eval_external_event(
            db,
            operation_key=live_eval_operation_key,
            outcome=EVENT_OUTCOME_SUCCEEDED,
            category=_live_eval_category_for_action(action_type),
            operation=str(action_type or "unknown"),
            integration_type=_live_eval_integration_type(action_type),
            target=str(action.get("to") or "")[:120] or None,
            job_id=getattr(job, "job_id", None),
            pipeline_run_id=trace.pipeline_run.pipeline_run_id if trace else None,
            action_operation_id=operation_id,
            snapshot=live_eval_snap,
            job_input_data=getattr(job, "input_data", None),
            metadata={"adapter_status": str(result.get("status"))},
        )

    result["action_operation_id"] = operation_id
    return result
