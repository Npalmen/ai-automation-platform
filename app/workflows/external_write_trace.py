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

_STUB_PROVIDERS = frozenset({"internal_stub", "internal", "none"})


def is_real_provider_execution_result(result: dict[str, Any]) -> bool:
    """True only when adapter result represents a real external provider attempt/success."""
    if not isinstance(result, dict):
        return False
    if str(result.get("status") or "").strip().lower() == "skipped":
        return False

    integration = result.get("integration_result")
    if isinstance(integration, dict):
        if integration.get("skipped"):
            return False
        provider = str(integration.get("provider") or "").strip().lower()
        if provider in _STUB_PROVIDERS:
            return False
        if str(integration.get("status") or "").strip().lower() == "stubbed":
            return False

    top_provider = str(result.get("provider") or "").strip().lower()
    if top_provider in _STUB_PROVIDERS:
        return False
    return True


def _adapter_outcome_metadata(result: dict[str, Any], *, action: dict[str, Any] | None = None) -> dict[str, Any]:
    """Normalize adapter/Gmail metadata for DecisionRecord and live-eval telemetry."""
    metadata: dict[str, Any] = {"adapter_status": str(result.get("status"))}

    integration = result.get("integration_result")
    integration_payload: dict[str, Any] = {}
    if isinstance(integration, dict):
        raw_integration_payload = integration.get("payload")
        if isinstance(raw_integration_payload, dict):
            integration_payload = raw_integration_payload

    top_payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}

    provider_message_id = integration_payload.get("google_message_id")
    if not provider_message_id and isinstance(integration, dict):
        provider_message_id = integration.get("external_id")
    if not provider_message_id:
        provider_message_id = top_payload.get("google_message_id")
    if not provider_message_id:
        provider_message_id = result.get("external_id")
    if provider_message_id:
        metadata["provider_message_id"] = str(provider_message_id)

    provider_rfc_message_id = integration_payload.get("rfc_message_id") or integration_payload.get(
        "internet_message_id"
    )
    if not provider_rfc_message_id:
        provider_rfc_message_id = top_payload.get("rfc_message_id") or top_payload.get(
            "internet_message_id"
        )
    if provider_rfc_message_id:
        metadata["provider_rfc_message_id"] = str(provider_rfc_message_id)

    provider_thread_id = integration_payload.get("thread_id")
    if provider_thread_id:
        metadata["provider_thread_id"] = str(provider_thread_id)

    if isinstance(integration, dict) and integration.get("status"):
        metadata["provider_status"] = str(integration.get("status"))

    provider_name = None
    if isinstance(integration, dict) and integration.get("provider"):
        provider_name = str(integration.get("provider"))
    elif result.get("provider"):
        provider_name = str(result.get("provider"))
    if provider_name:
        metadata["adapter_provider"] = provider_name[:80]

    if action is not None:
        recipient = str(action.get("to") or "").strip().lower()
        if recipient:
            metadata["adapter_recipient"] = recipient[:120]
        sender = str(action.get("from_email") or "").strip().lower()
        if sender:
            metadata["adapter_sender"] = sender[:120]

    return metadata


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


def _latest_outcome_metadata(
    db: Session,
    *,
    tenant_id: str,
    action_operation_id: str,
) -> dict[str, Any]:
    rows = DecisionRecordRepository.list_for_operation(
        db,
        tenant_id=tenant_id,
        action_operation_id=action_operation_id,
    )
    for row in reversed(rows):
        if row.record_type == "execution_outcome" and isinstance(row.metadata_json, dict):
            return dict(row.metadata_json)
    return {}


def _is_timeout_after_send_risk(exc: BaseException) -> bool:
    name = type(exc).__name__.lower()
    if isinstance(exc, TimeoutError):
        return True
    if "timeout" in name:
        return True
    try:
        import httpx

        if isinstance(exc, httpx.TimeoutException):
            return True
    except ImportError:
        pass
    return False


def _classify_adapter_result_status(
    result: dict[str, Any],
    *,
    action: dict[str, Any] | None = None,
) -> tuple[ExecutionStatus, dict[str, Any]]:
    """Map adapter result to execution status. Stub never SUCCEEDED; missing id → unknown."""
    meta = _adapter_outcome_metadata(result, action=action)
    if not is_real_provider_execution_result(result):
        meta.update(
            {
                "block_automatic_retry": True,
                "automatic_retry": False,
                "approved_reply_sent": False,
                "unknown_outcome": False,
                "failure_reason": "stub_or_skipped_provider_result",
                "provider_attempted": False,
            }
        )
        return ExecutionStatus.FAILED, meta

    if not meta.get("provider_message_id"):
        meta.update(
            {
                "block_automatic_retry": True,
                "automatic_retry": False,
                "reconciliation_required": True,
                "unknown_outcome": True,
                "failure_reason": "real_provider_missing_message_id",
                "provider_attempted": True,
            }
        )
        return ExecutionStatus.OUTCOME_UNKNOWN, meta

    meta.update(
        {
            "automatic_retry": False,
            "approved_reply_sent": True,
            "unknown_outcome": False,
            "provider_attempted": True,
        }
    )
    return ExecutionStatus.SUCCEEDED, meta


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

    if state == ExecutionStatus.FAILED.value:
        prior_meta = _latest_outcome_metadata(
            db, tenant_id=job.tenant_id, action_operation_id=operation_id
        )
        if prior_meta.get("block_automatic_retry"):
            raise ReconciliationRequired(
                f"action_operation_id {operation_id} blocks automatic adapter retry "
                f"(state={state}, block_automatic_retry=true)"
            )

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
        from app.evaluation.live.errors import LiveEvalSafetyError

        outcome_status = (
            ExecutionStatus.OUTCOME_UNKNOWN
            if _is_timeout_after_send_risk(exc)
            else ExecutionStatus.FAILED
        )
        outcome_meta: dict[str, Any] = {
            "error_class": type(exc).__name__,
            "automatic_retry": False,
        }
        if outcome_status == ExecutionStatus.OUTCOME_UNKNOWN:
            outcome_meta.update(
                {
                    "block_automatic_retry": True,
                    "reconciliation_required": True,
                    "unknown_outcome": True,
                    "failure_reason": "provider_timeout_after_send_risk",
                }
            )
        elif isinstance(exc, (LiveEvalSafetyError, ExternalWriteBlocked)):
            outcome_meta.update(
                {
                    "block_automatic_retry": True,
                    "unknown_outcome": False,
                    "provider_attempted": False,
                    "failure_reason": "reply_provider_blocked_before_write",
                }
            )
        if db is not None and live_eval_snap is not None and live_eval_operation_key:
            from app.evaluation.live.telemetry import record_live_eval_external_event

            record_live_eval_external_event(
                db,
                operation_key=live_eval_operation_key,
                outcome="failed" if outcome_status == ExecutionStatus.FAILED else "unknown",
                category=_live_eval_category_for_action(action_type),
                operation=str(action_type or "unknown"),
                integration_type=_live_eval_integration_type(action_type),
                job_id=getattr(job, "job_id", None),
                pipeline_run_id=trace.pipeline_run.pipeline_run_id if trace else None,
                action_operation_id=operation_id,
                snapshot=live_eval_snap,
                job_input_data=getattr(job, "input_data", None),
                metadata=outcome_meta,
            )
        record_execution_outcome(
            db,
            trace,
            job,
            action,
            operation_id=operation_id,
            fingerprint=fingerprint,
            key_version=key_version,
            status=outcome_status,
            metadata=outcome_meta,
        )
        if outcome_status == ExecutionStatus.OUTCOME_UNKNOWN:
            raise ReconciliationRequired(
                f"provider timeout after send risk for {operation_id} — reconciliation required"
            ) from exc
        raise

    outcome_status, outcome_meta = _classify_adapter_result_status(result, action=action)

    if outcome_status != ExecutionStatus.SUCCEEDED:
        if db is not None and live_eval_snap is not None and live_eval_operation_key:
            from app.evaluation.live.telemetry import record_live_eval_external_event

            record_live_eval_external_event(
                db,
                operation_key=live_eval_operation_key,
                outcome=(
                    "failed"
                    if outcome_status == ExecutionStatus.FAILED
                    else "unknown"
                ),
                category=_live_eval_category_for_action(action_type),
                operation=str(action_type or "unknown"),
                integration_type=_live_eval_integration_type(action_type),
                target=str(action.get("to") or "")[:120] or None,
                job_id=getattr(job, "job_id", None),
                pipeline_run_id=trace.pipeline_run.pipeline_run_id if trace else None,
                action_operation_id=operation_id,
                snapshot=live_eval_snap,
                job_input_data=getattr(job, "input_data", None),
                metadata=outcome_meta,
            )
        record_execution_outcome(
            db,
            trace,
            job,
            action,
            operation_id=operation_id,
            fingerprint=fingerprint,
            key_version=key_version,
            status=outcome_status,
            metadata=outcome_meta,
        )
        if outcome_status == ExecutionStatus.OUTCOME_UNKNOWN:
            raise ReconciliationRequired(
                f"real provider result missing provider_message_id for {operation_id}"
            )
        raise ExternalWriteBlocked(
            f"external write result is stub/skipped — not succeeded for {operation_id}"
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
            status=ExecutionStatus.SUCCEEDED,
            metadata=outcome_meta,
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
                metadata={
                    "reconciliation_required": True,
                    "block_automatic_retry": True,
                    "error_class": type(persist_exc).__name__,
                },
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
            metadata=outcome_meta,
        )

    result["action_operation_id"] = operation_id
    return result
