"""Single write entrypoint for append-only decision records."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.repositories.postgres.decision_record_repository import DecisionRecordRepository
from app.workflows.action_fingerprint import compute_action_fingerprint
from app.workflows.decision_record import (
    DecisionRecordType,
    ExecutionPhase,
    ExecutionStatus,
    validate_metadata,
)
from app.workflows.decision_trace_errors import OperationConflict
from app.workflows.pipeline_run_context import DecisionTraceSession

logger = logging.getLogger(__name__)


def _job_status(job) -> str:
    status = getattr(job, "status", None)
    return status.value if hasattr(status, "value") else str(status or "unknown")


def _base_record(
    trace: DecisionTraceSession,
    job,
    *,
    record_type: DecisionRecordType,
    idempotency_key: str,
    stage_sequence: int | None = None,
) -> dict[str, Any]:
    run = trace.pipeline_run
    return {
        "decision_id": DecisionRecordRepository.new_decision_id(),
        "tenant_id": run.tenant_id,
        "job_id": run.job_id,
        "pipeline_run_id": run.pipeline_run_id,
        "parent_pipeline_run_id": run.parent_pipeline_run_id,
        "stage_sequence": stage_sequence if stage_sequence is not None else trace.next_stage(),
        "record_type": record_type.value,
        "source": run.source.value,
        "tenant_config_version": run.tenant_config_version,
        "code_version": run.code_version,
        "idempotency_key": idempotency_key,
        "job_status_at_record": _job_status(job),
        "metadata": {},
    }


def append_record(
    db: Session | None,
    trace: DecisionTraceSession | None,
    job,
    *,
    record_type: DecisionRecordType,
    idempotency_key: str,
    stage_sequence: int | None = None,
    metadata: dict[str, Any] | None = None,
    **fields: Any,
) -> str | None:
    if db is None or trace is None:
        return None
    record = _base_record(
        trace,
        job,
        record_type=record_type,
        idempotency_key=idempotency_key,
        stage_sequence=stage_sequence,
    )
    record["metadata"] = validate_metadata(metadata)
    record.update(fields)
    try:
        row = DecisionRecordRepository.append_if_absent(db, record)
        return row.decision_id
    except Exception as exc:
        logger.error("DecisionRecord append failed: %s", exc, exc_info=True)
        from app.core.audit_service import create_audit_event

        create_audit_event(
            db=db,
            tenant_id=job.tenant_id,
            category="workflow",
            action="decision_record_degraded",
            status="failed",
            details={"job_id": job.job_id, "record_type": record_type.value, "error_class": type(exc).__name__},
        )
        return None


def record_pipeline_run_started(db: Session | None, trace: DecisionTraceSession | None, job) -> str | None:
    if trace is None:
        return None
    return append_record(
        db,
        trace,
        job,
        record_type=DecisionRecordType.PIPELINE_RUN_STARTED,
        idempotency_key=f"run_started:{trace.pipeline_run.pipeline_run_id}",
        stage_sequence=0,
    )


def record_processor_decision(
    db: Session | None,
    trace: DecisionTraceSession | None,
    job,
    *,
    record_type: DecisionRecordType,
    processor_name: str,
    payload: dict[str, Any],
) -> str | None:
    if trace is None:
        return None
    return append_record(
        db,
        trace,
        job,
        record_type=record_type,
        idempotency_key=f"{record_type.value}:{trace.pipeline_run.pipeline_run_id}",
        processor_name=processor_name,
        recommendation=payload.get("decision") or payload.get("decisioning_recommendation"),
        policy_authorization=payload.get("policy_authorization"),
        policy_decision=payload.get("decision") if record_type == DecisionRecordType.POLICY_AUTHORIZATION else None,
        confidence=payload.get("confidence"),
        reason_codes=payload.get("reasons") or [],
        prompt_name=payload.get("prompt_name"),
        metadata={
            "prompt_name": payload.get("prompt_name"),
            "used_fallback": payload.get("used_fallback"),
            "duration_ms": payload.get("duration_ms"),
        },
    )


def allocate_action_operation_id(
    db: Session | None,
    *,
    tenant_id: str,
    job_id: str,
    action: dict[str, Any],
    existing_operation_id: str | None = None,
) -> tuple[str, str | None, int | None]:
    fingerprint, key_version = compute_action_fingerprint(action)
    if existing_operation_id:
        if fingerprint and db is not None:
            rows = DecisionRecordRepository.list_for_operation(db, tenant_id=tenant_id, action_operation_id=existing_operation_id)
            for row in rows:
                if row.action_fingerprint and row.action_fingerprint != fingerprint:
                    raise OperationConflict(
                        f"action_operation_id {existing_operation_id} fingerprint mismatch"
                    )
        return existing_operation_id, fingerprint, key_version

    if fingerprint and db is not None:
        for row in DecisionRecordRepository.list_for_job(db, tenant_id=tenant_id, job_id=job_id):
            if row.action_fingerprint == fingerprint and row.action_operation_id:
                return row.action_operation_id, fingerprint, key_version

    return str(uuid.uuid4()), fingerprint, key_version


def record_action_authorization(
    db: Session | None,
    trace: DecisionTraceSession | None,
    job,
    action: dict[str, Any],
    *,
    authorization: str,
) -> str | None:
    if trace is None or db is None:
        return None

    existing_id = action.get("_action_operation_id")
    operation_id, fingerprint, key_version = allocate_action_operation_id(
        db,
        tenant_id=job.tenant_id,
        job_id=job.job_id,
        action=action,
        existing_operation_id=existing_id,
    )
    action["_action_operation_id"] = operation_id
    if fingerprint:
        action["_action_fingerprint"] = fingerprint

    append_record(
        db,
        trace,
        job,
        record_type=DecisionRecordType.ACTION_AUTHORIZATION,
        idempotency_key=f"action_auth:{operation_id}",
        action_type=str(action.get("type") or ""),
        action_operation_id=operation_id,
        action_fingerprint=fingerprint,
        fingerprint_key_version=key_version,
        action_authorization=authorization,
        execution_phase=ExecutionPhase.AUTHORIZATION.value,
        metadata={
            "action_operation_id": operation_id,
            "action_fingerprint": fingerprint,
        },
    )
    return operation_id


def record_execution_intent(
    db: Session,
    trace: DecisionTraceSession | None,
    job,
    action: dict[str, Any],
    *,
    operation_id: str,
    fingerprint: str | None,
    key_version: int | None,
) -> str | None:
    return append_record(
        db,
        trace,
        job,
        record_type=DecisionRecordType.EXECUTION_INTENT,
        idempotency_key=f"exec_intent:{operation_id}",
        action_type=str(action.get("type") or ""),
        action_operation_id=operation_id,
        action_fingerprint=fingerprint,
        fingerprint_key_version=key_version,
        execution_phase=ExecutionPhase.INTENT.value,
        execution_status=ExecutionStatus.PENDING.value,
        metadata={"action_operation_id": operation_id},
    )


def record_execution_outcome(
    db: Session,
    trace: DecisionTraceSession | None,
    job,
    action: dict[str, Any],
    *,
    operation_id: str,
    fingerprint: str | None,
    key_version: int | None,
    status: ExecutionStatus,
    metadata: dict[str, Any] | None = None,
) -> str | None:
    meta = {"action_operation_id": operation_id, **(metadata or {})}
    if status == ExecutionStatus.OUTCOME_UNKNOWN:
        meta["reconciliation_required"] = True
    return append_record(
        db,
        trace,
        job,
        record_type=DecisionRecordType.EXECUTION_OUTCOME,
        idempotency_key=f"exec_outcome:{operation_id}:{status.value}",
        action_type=str(action.get("type") or ""),
        action_operation_id=operation_id,
        action_fingerprint=fingerprint,
        fingerprint_key_version=key_version,
        execution_phase=ExecutionPhase.OUTCOME.value,
        execution_status=status.value,
        metadata=meta,
    )


def record_operator_recovery(
    db: Session | None,
    trace: DecisionTraceSession | None,
    job,
    *,
    operator_action: str,
    operator_actor: str,
    audit_event_id: str | None = None,
    supersedes_decision_id: str | None = None,
) -> str | None:
    return append_record(
        db,
        trace,
        job,
        record_type=DecisionRecordType.OPERATOR_RECOVERY,
        idempotency_key=f"recovery:{audit_event_id or trace.pipeline_run.pipeline_run_id if trace else 'unknown'}",
        metadata={
            "operator_action": operator_action,
            "operator_actor": operator_actor,
            "audit_event_id": audit_event_id,
            "supersedes_decision_id": supersedes_decision_id,
        },
        supersedes_decision_id=supersedes_decision_id,
    )
