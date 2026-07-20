"""Per-action approval resolution with atomic pre-adapter trace commit (Kapitel 2D.1)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.repositories.postgres.approval_repository import ApprovalRequestRepository
from app.repositories.postgres.decision_record_repository import DecisionRecordRepository
from app.repositories.postgres.job_repository import JobRepository
from app.workflows.action_authorization import ActionEffect, classify_action
from app.workflows.action_fingerprint import compute_action_fingerprint
from app.workflows.decision_record import ExecutionStatus
from app.workflows.decision_record_service import (
    record_action_approval_resolution,
    record_execution_intent,
    record_pipeline_run_started,
)
from app.workflows.decision_trace_errors import ContractConflict, ReconciliationRequired
from app.workflows.email_approval_resolution import finalize_email_approval_resolution
from app.workflows.pipeline_run_context import PipelineRunSource, create_trace_session

logger = logging.getLogger(__name__)

_UNRESOLVED = frozenset({
    ExecutionStatus.PENDING.value,
    ExecutionStatus.OUTCOME_UNKNOWN.value,
    ExecutionStatus.RECONCILIATION_REQUIRED.value,
})


@dataclass
class ActionApprovalResolutionResult:
    approval_id: str
    job_id: str
    approval_state: str
    execution_state: str | None = None
    reconciliation_required: bool = False
    automatic_retry_allowed: bool = False
    action_operation_id: str | None = None
    send_result: dict[str, Any] | None = None
    send_error: str | None = None
    idempotent: bool = False
    contract_conflict: str | None = None

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "job_id": self.job_id,
            "status": self.approval_state,
            "approval_state": self.approval_state,
            "execution_state": self.execution_state,
            "reconciliation_required": self.reconciliation_required,
            "automatic_retry_allowed": self.automatic_retry_allowed,
            "action_operation_id": self.action_operation_id,
            "send_result": self.send_result,
            "send_error": self.send_error,
            "idempotent": self.idempotent,
            "contract_conflict": self.contract_conflict,
        }


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _load_job(db: Session, approval) -> Job:
    try:
        job_type = JobType(approval.job_type or "customer_inquiry")
    except ValueError:
        job_type = JobType.CUSTOMER_INQUIRY
    job = Job(
        job_id=approval.job_id,
        tenant_id=approval.tenant_id,
        job_type=job_type,
        input_data={},
    )
    loaded = JobRepository.get_job_by_id(db, approval.tenant_id, approval.job_id)
    if loaded is not None and isinstance(loaded.job_id, str):
        return loaded
    return job


def _verify_action_authorization(
    db: Session,
    *,
    approval,
    delivery: dict[str, Any],
) -> tuple[Any, str, str | None, int | None]:
    request_payload = approval.request_payload or {}
    operation_id = request_payload.get("action_operation_id")
    if not operation_id:
        raise ContractConflict("missing action_operation_id in approval metadata")

    auth_row = DecisionRecordRepository.get_action_authorization(
        db,
        tenant_id=approval.tenant_id,
        action_operation_id=str(operation_id),
    )
    if auth_row is None:
        raise ContractConflict(f"no action_authorization for operation {operation_id}")
    if auth_row.tenant_id != approval.tenant_id:
        raise ContractConflict("action_authorization tenant_id mismatch")
    if auth_row.job_id != approval.job_id:
        raise ContractConflict("action_authorization job_id mismatch")
    if auth_row.action_authorization != "approval_required":
        raise ContractConflict(
            f"action_authorization must be approval_required, got {auth_row.action_authorization}"
        )

    action_type = str(delivery.get("type") or "")
    if auth_row.action_type and action_type and auth_row.action_type != action_type:
        raise ContractConflict("action_type mismatch between delivery and action_authorization")

    fingerprint, key_version = compute_action_fingerprint(
        {**delivery, "tenant_id": approval.tenant_id}
    )
    stored_fp = auth_row.action_fingerprint
    if stored_fp and fingerprint and stored_fp != fingerprint:
        raise ContractConflict("action_fingerprint mismatch between delivery and action_authorization")
    if not fingerprint:
        fingerprint = stored_fp
    if key_version is None:
        key_version = auth_row.fingerprint_key_version

    return auth_row, str(operation_id), fingerprint, key_version


def _execution_snapshot(
    db: Session,
    *,
    tenant_id: str,
    operation_id: str,
) -> tuple[str | None, bool, bool]:
    state = DecisionRecordRepository.latest_operation_state(
        db,
        tenant_id=tenant_id,
        action_operation_id=operation_id,
    )
    reconciliation_required = state in (
        ExecutionStatus.OUTCOME_UNKNOWN.value,
        ExecutionStatus.RECONCILIATION_REQUIRED.value,
    )
    automatic_retry_allowed = state not in _UNRESOLVED and state != ExecutionStatus.SUCCEEDED.value
    return state, reconciliation_required, automatic_retry_allowed


def _idempotent_result(db: Session, approval, *, operation_id: str | None) -> ActionApprovalResolutionResult:
    execution_state: str | None = None
    reconciliation_required = False
    automatic_retry_allowed = False
    if operation_id:
        execution_state, reconciliation_required, automatic_retry_allowed = _execution_snapshot(
            db,
            tenant_id=approval.tenant_id,
            operation_id=operation_id,
        )
    if approval.state == "rejected":
        execution_state = execution_state or "not_executed"
    return ActionApprovalResolutionResult(
        approval_id=approval.approval_id,
        job_id=approval.job_id,
        approval_state=approval.state,
        execution_state=execution_state,
        reconciliation_required=reconciliation_required,
        automatic_retry_allowed=automatic_retry_allowed,
        action_operation_id=operation_id,
        idempotent=True,
    )


def _commit_pre_adapter_phase(
    db: Session,
    *,
    approval,
    job: Job,
    delivery: dict[str, Any],
    operation_id: str,
    fingerprint: str | None,
    key_version: int | None,
    parent_pipeline_run_id: str,
    actor: str | None,
    note: str | None,
) -> DecisionTraceSession:
    now = _utcnow()
    transitioned, won = ApprovalRequestRepository.transition_state_if_pending(
        db,
        tenant_id=approval.tenant_id,
        approval_id=approval.approval_id,
        new_state="approved",
        resolved_at=now,
        resolved_by=actor or "operator",
        resolution_note=note,
    )
    if transitioned is None:
        raise ContractConflict("approval record not found")
    if not won:
        raise ContractConflict("approval already resolved")
    if transitioned.state != "approved":
        raise ContractConflict(f"approval transition failed, state={transitioned.state}")

    trace = create_trace_session(
        job,
        source=PipelineRunSource.APPROVAL_RESUME,
        db=db,
        parent_pipeline_run_id=parent_pipeline_run_id,
    )
    record_pipeline_run_started(db, trace, job)
    record_action_approval_resolution(
        db,
        trace,
        job,
        approval_id=approval.approval_id,
        operation_id=operation_id,
        action_type=str(delivery.get("type") or ""),
        approved=True,
        fingerprint=fingerprint,
        key_version=key_version,
    )
    record_execution_intent(
        db,
        trace,
        job,
        delivery,
        operation_id=operation_id,
        fingerprint=fingerprint,
        key_version=key_version,
    )
    db.commit()
    return trace


def _commit_reject_phase(
    db: Session,
    *,
    approval,
    job: Job,
    operation_id: str,
    action_type: str,
    fingerprint: str | None,
    key_version: int | None,
    parent_pipeline_run_id: str,
    actor: str | None,
    note: str | None,
) -> None:
    now = _utcnow()
    transitioned, won = ApprovalRequestRepository.transition_state_if_pending(
        db,
        tenant_id=approval.tenant_id,
        approval_id=approval.approval_id,
        new_state="rejected",
        resolved_at=now,
        resolved_by=actor or "operator",
        resolution_note=note,
    )
    if transitioned is None:
        raise ContractConflict("approval record not found")
    if not won:
        raise ContractConflict("approval already resolved")
    if transitioned.state != "rejected":
        raise ContractConflict(f"approval reject transition failed, state={transitioned.state}")

    trace = create_trace_session(
        job,
        source=PipelineRunSource.APPROVAL_RESUME,
        db=db,
        parent_pipeline_run_id=parent_pipeline_run_id,
    )
    record_pipeline_run_started(db, trace, job)
    record_action_approval_resolution(
        db,
        trace,
        job,
        approval_id=approval.approval_id,
        operation_id=operation_id,
        action_type=action_type,
        approved=False,
        fingerprint=fingerprint,
        key_version=key_version,
    )
    db.commit()


def resolve_per_action_approval(
    db: Session,
    approval,
    *,
    approved: bool,
    actor: str | None = None,
    note: str | None = None,
) -> ActionApprovalResolutionResult:
    """Resolve a per-action / email approval with full decision trace on external writes."""
    request_payload = approval.request_payload or {}
    operation_id = request_payload.get("action_operation_id")

    if approval.state in ("approved", "rejected"):
        return _idempotent_result(db, approval, operation_id=operation_id)

    delivery = dict(approval.delivery_payload or {})
    job = _load_job(db, approval)

    if not approved:
        if not delivery:
            now = _utcnow()
            ApprovalRequestRepository.transition_state_if_pending(
                db,
                tenant_id=approval.tenant_id,
                approval_id=approval.approval_id,
                new_state="rejected",
                resolved_at=now,
                resolved_by=actor or "operator",
                resolution_note=note,
            )[0]
            db.commit()
            finalize_email_approval_resolution(
                db, approval, approved=False, actor=actor, note=note,
                send_result=None, send_error=None,
            )
            return ActionApprovalResolutionResult(
                approval_id=approval.approval_id,
                job_id=approval.job_id,
                approval_state="rejected",
                execution_state="not_executed",
                action_operation_id=operation_id,
            )
        try:
            auth_row, operation_id, fingerprint, key_version = _verify_action_authorization(
                db, approval=approval, delivery=delivery,
            )
        except ContractConflict as exc:
            return ActionApprovalResolutionResult(
                approval_id=approval.approval_id,
                job_id=approval.job_id,
                approval_state="pending",
                execution_state="blocked",
                contract_conflict=str(exc),
            )
        try:
            _commit_reject_phase(
                db,
                approval=approval,
                job=job,
                operation_id=operation_id,
                action_type=str(delivery.get("type") or ""),
                fingerprint=fingerprint,
                key_version=key_version,
                parent_pipeline_run_id=auth_row.pipeline_run_id,
                actor=actor,
                note=note,
            )
        except Exception:
            db.rollback()
            raise
        approval.state = "rejected"
        finalize_email_approval_resolution(
            db, approval, approved=False, actor=actor, note=note,
            send_result=None, send_error=None,
        )
        return ActionApprovalResolutionResult(
            approval_id=approval.approval_id,
            job_id=approval.job_id,
            approval_state="rejected",
            execution_state="not_executed",
            action_operation_id=operation_id,
        )

    if not delivery:
        return ActionApprovalResolutionResult(
            approval_id=approval.approval_id,
            job_id=approval.job_id,
            approval_state="pending",
            execution_state="not_executed",
            contract_conflict="empty delivery_payload",
        )

    try:
        auth_row, operation_id, fingerprint, key_version = _verify_action_authorization(
            db, approval=approval, delivery=delivery,
        )
    except ContractConflict as exc:
        return ActionApprovalResolutionResult(
            approval_id=approval.approval_id,
            job_id=approval.job_id,
            approval_state="pending",
            execution_state="blocked",
            contract_conflict=str(exc),
        )

    spec = classify_action(str(delivery.get("type") or ""))
    is_external = spec is not None and spec.effect == ActionEffect.EXTERNAL_WRITE

    trace = None
    if is_external:
        try:
            trace = _commit_pre_adapter_phase(
                db,
                approval=approval,
                job=job,
                delivery=delivery,
                operation_id=operation_id,
                fingerprint=fingerprint,
                key_version=key_version,
                parent_pipeline_run_id=auth_row.pipeline_run_id,
                actor=actor,
                note=note,
            )
        except ContractConflict as exc:
            if str(exc) == "approval already resolved":
                db.rollback()
                refreshed = ApprovalRequestRepository.get_by_approval_id(
                    db,
                    tenant_id=approval.tenant_id,
                    approval_id=approval.approval_id,
                )
                if refreshed is not None:
                    approval.state = refreshed.state
                return _idempotent_result(db, approval, operation_id=operation_id)
            db.rollback()
            raise
        except Exception:
            db.rollback()
            raise
        approval.state = "approved"

    send_result = None
    send_error = None
    execution_state: str | None = None
    reconciliation_required = False
    automatic_retry_allowed = False

    if delivery:
        prepared = dict(delivery)
        prepared["_action_operation_id"] = operation_id
        if fingerprint:
            prepared["_action_fingerprint"] = fingerprint
        prepared["_authorization"] = "execution_allowed"
        prepared["_execute_after_intent_commit"] = bool(trace and is_external)
        try:
            from app.workflows.action_executor import execute_action

            send_result = execute_action(prepared, db=db, job=job, trace=trace)
            execution_state = ExecutionStatus.SUCCEEDED.value
        except ReconciliationRequired as exc:
            send_error = str(exc)
            execution_state = ExecutionStatus.OUTCOME_UNKNOWN.value
            reconciliation_required = True
            logger.error(
                "Approval execution reconciliation required for %s: %s",
                approval.approval_id,
                exc,
            )
        except Exception as exc:
            send_error = str(exc)
            execution_state = ExecutionStatus.FAILED.value
            logger.error(
                "Approval execution failed for %s: %s",
                approval.approval_id,
                exc,
            )

    if not is_external:
        now = _utcnow()
        transitioned, won = ApprovalRequestRepository.transition_state_if_pending(
            db,
            tenant_id=approval.tenant_id,
            approval_id=approval.approval_id,
            new_state="approved",
            resolved_at=now,
            resolved_by=actor or "operator",
            resolution_note=note,
        )
        if transitioned is not None and won:
            db.commit()
            approval.state = "approved"
        execution_state = execution_state or (
            ExecutionStatus.SUCCEEDED.value if send_result else "not_executed"
        )

    execution_state, reconciliation_required, automatic_retry_allowed = _execution_snapshot(
        db,
        tenant_id=approval.tenant_id,
        operation_id=operation_id,
    )
    if execution_state is None:
        execution_state = ExecutionStatus.SUCCEEDED.value if send_result else ExecutionStatus.FAILED.value

    finalize_email_approval_resolution(
        db,
        approval,
        approved=True,
        actor=actor,
        note=note,
        send_result=send_result,
        send_error=send_error,
    )

    return ActionApprovalResolutionResult(
        approval_id=approval.approval_id,
        job_id=approval.job_id,
        approval_state="approved",
        execution_state=execution_state,
        reconciliation_required=reconciliation_required,
        automatic_retry_allowed=automatic_retry_allowed,
        action_operation_id=operation_id,
        send_result=send_result,
        send_error=send_error,
    )
