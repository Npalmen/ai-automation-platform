"""Authoritative live_eval_runs registry service."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.evaluation.live.audit import emit_live_eval_audit
from app.evaluation.live.constants import (
    RUN_STATUS_ABORTED,
    RUN_STATUS_COMPLETED,
    S01_LLM_MAX_CALLS,
)
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.fixture_bundle import resolve_fixture_bundle_id
from app.evaluation.live.safety import validate_registration_request
from app.evaluation.live.schemas import (
    LiveEvalRunRegisterRequest,
    LiveEvalRunResponse,
    TrustedLiveEvalSnapshot,
)
from app.domain.workflows.models import Job
from app.repositories.postgres.live_eval_models import LiveEvalRunRow
from app.repositories.postgres.live_eval_repository import (
    LiveEvalRunConflictError,
    LiveEvalRunNotFoundError,
    LiveEvalRunRepository,
)
from app.repositories.postgres.job_repository import JobRepository


def _compute_config_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def register_live_eval_run(
    db: Session,
    request: LiveEvalRunRegisterRequest,
    *,
    created_by: str,
) -> LiveEvalRunResponse:
    validate_registration_request(
        tenant_id=request.tenant_id,
        transport_mode=request.transport_mode,
        ai_mode=request.ai_mode,
        scenario_id=request.scenario_id,
        expected_sender=request.expected_sender,
        expected_recipient=request.expected_recipient,
        llm_provider=request.llm_provider,
        llm_requested_model=request.llm_requested_model,
    )
    from app.evaluation.live.safety import validate_live_gmail_registration

    validate_live_gmail_registration(
        transport_mode=request.transport_mode,
        scenario_id=request.scenario_id,
        ai_mode=request.ai_mode,
    )
    fixture_bundle_id = resolve_fixture_bundle_id(
        scenario_id=request.scenario_id,
        ai_mode=request.ai_mode,
    )
    expected_sender: str | None = None
    expected_recipient: str | None = None
    llm_provider: str | None = None
    llm_requested_model: str | None = None
    llm_max_calls: int | None = None
    if request.transport_mode == "live_gmail":
        expected_sender = request.expected_sender.strip().lower()
        expected_recipient = request.expected_recipient.strip().lower()
    elif request.transport_mode == "fixture_input" and request.ai_mode == "live_llm":
        llm_provider = (request.llm_provider or "").strip()
        llm_requested_model = (request.llm_requested_model or "").strip()
        llm_max_calls = S01_LLM_MAX_CALLS
    expires_at = request.expires_at or (datetime.now(timezone.utc) + timedelta(hours=2))
    config_payload = {
        "evaluation_run_id": request.evaluation_run_id,
        "tenant_id": request.tenant_id,
        "scenario_id": request.scenario_id,
        "attempt_id": request.attempt_id,
        "transport_mode": request.transport_mode,
        "ai_mode": request.ai_mode,
        "fixture_bundle_id": fixture_bundle_id,
        "expected_sender": expected_sender,
        "expected_recipient": expected_recipient,
        "llm_provider": llm_provider,
        "llm_requested_model": llm_requested_model,
        "llm_max_calls": llm_max_calls,
        "expires_at": expires_at.isoformat(),
    }
    row = LiveEvalRunRow(
        evaluation_run_id=request.evaluation_run_id,
        tenant_id=request.tenant_id,
        scenario_id=request.scenario_id,
        attempt_id=request.attempt_id,
        transport_mode=request.transport_mode,
        ai_mode=request.ai_mode,
        fixture_bundle_id=fixture_bundle_id,
        expected_sender=expected_sender,
        expected_recipient=expected_recipient,
        llm_provider=llm_provider,
        llm_requested_model=llm_requested_model,
        llm_max_calls=llm_max_calls,
        status="registered",
        created_by=created_by,
        expires_at=expires_at,
        config_hash=_compute_config_hash(config_payload),
    )
    try:
        LiveEvalRunRepository.register_run(db, row)
    except LiveEvalRunConflictError as exc:
        raise LiveEvalSafetyError(str(exc)) from exc
    emit_live_eval_audit(
        db,
        tenant_id=request.tenant_id,
        action="run_registered",
        status="success",
        details={
            "evaluation_run_id": request.evaluation_run_id,
            "scenario_id": request.scenario_id,
            "attempt_id": request.attempt_id,
            "ai_mode": request.ai_mode,
            "fixture_bundle_id": fixture_bundle_id,
            "llm_provider": llm_provider,
            "llm_requested_model": llm_requested_model,
            "llm_max_calls": llm_max_calls,
        },
    )
    db.commit()
    return _row_to_response(row)


def _row_to_response(row: LiveEvalRunRow) -> LiveEvalRunResponse:
    payload = {
        "evaluation_run_id": row.evaluation_run_id,
        "tenant_id": row.tenant_id,
        "scenario_id": row.scenario_id,
        "attempt_id": row.attempt_id,
        "transport_mode": row.transport_mode,
        "ai_mode": row.ai_mode,
        "fixture_bundle_id": row.fixture_bundle_id,
        "expected_sender": row.expected_sender,
        "expected_recipient": row.expected_recipient,
        "llm_provider": row.llm_provider,
        "llm_requested_model": row.llm_requested_model,
        "llm_max_calls": row.llm_max_calls,
        "status": row.status,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "expires_at": row.expires_at,
        "config_hash": row.config_hash,
    }
    return LiveEvalRunResponse.model_validate(payload)


def create_and_claim_fixture_root_job(
    db: Session,
    *,
    job: Job,
    evaluation_run_id: str,
    tenant_id: str,
) -> Job:
    """Atomically persist fixture-input root job and claim the registered run."""
    try:
        saved_job = JobRepository.create_job(db, job, commit=False)
        claim_fixture_root_job(
            db,
            evaluation_run_id=evaluation_run_id,
            tenant_id=tenant_id,
            root_job_id=saved_job.job_id,
            commit=False,
        )
        db.commit()
        return saved_job
    except Exception:
        db.rollback()
        raise


def claim_fixture_root_job(
    db: Session,
    *,
    evaluation_run_id: str,
    tenant_id: str,
    root_job_id: str,
    commit: bool = True,
) -> LiveEvalRunResponse:
    try:
        row = LiveEvalRunRepository.claim_fixture_root_job(
            db,
            evaluation_run_id=evaluation_run_id,
            tenant_id=tenant_id,
            root_job_id=root_job_id,
        )
    except LiveEvalRunConflictError as exc:
        raise LiveEvalSafetyError(str(exc)) from exc
    except LiveEvalRunNotFoundError as exc:
        raise LiveEvalSafetyError(str(exc)) from exc
    emit_live_eval_audit(
        db,
        tenant_id=tenant_id,
        action="activated",
        status="success",
        details={
            "evaluation_run_id": evaluation_run_id,
            "root_job_id": root_job_id,
            "transport_mode": "fixture_input",
        },
        commit=commit,
    )
    if commit:
        db.commit()
    return _row_to_response(row)


def claim_live_eval_root_job(
    db: Session,
    *,
    evaluation_run_id: str,
    tenant_id: str,
    root_gmail_message_id: str,
    root_job_id: str,
    commit: bool = True,
) -> LiveEvalRunResponse:
    try:
        row = LiveEvalRunRepository.claim_root_job(
            db,
            evaluation_run_id=evaluation_run_id,
            tenant_id=tenant_id,
            root_gmail_message_id=root_gmail_message_id,
            root_job_id=root_job_id,
        )
    except LiveEvalRunConflictError as exc:
        raise LiveEvalSafetyError(str(exc)) from exc
    except LiveEvalRunNotFoundError as exc:
        raise LiveEvalSafetyError(str(exc)) from exc
    emit_live_eval_audit(
        db,
        tenant_id=tenant_id,
        action="activated",
        status="success",
        details={
            "evaluation_run_id": evaluation_run_id,
            "root_gmail_message_id": root_gmail_message_id,
            "root_job_id": root_job_id,
        },
        commit=commit,
    )
    if commit:
        db.commit()
    return _row_to_response(row)


def create_and_claim_live_eval_root_job(
    db: Session,
    *,
    job: Job,
    evaluation_run_id: str,
    tenant_id: str,
    root_gmail_message_id: str,
) -> Job:
    """Atomically persist root job and claim the registered live-eval run."""
    try:
        saved_job = JobRepository.create_job(db, job, commit=False)
        claim_live_eval_root_job(
            db,
            evaluation_run_id=evaluation_run_id,
            tenant_id=tenant_id,
            root_gmail_message_id=root_gmail_message_id,
            root_job_id=saved_job.job_id,
            commit=False,
        )
        db.commit()
        return saved_job
    except Exception:
        db.rollback()
        raise


def complete_live_eval_run(
    db: Session,
    evaluation_run_id: str,
    *,
    tenant_id: str,
    status: str,
) -> LiveEvalRunResponse:
    if status not in (RUN_STATUS_COMPLETED, RUN_STATUS_ABORTED):
        raise LiveEvalSafetyError(f"Invalid terminal status {status!r}")
    try:
        row = LiveEvalRunRepository.transition_status(
            db,
            evaluation_run_id,
            tenant_id=tenant_id,
            to_status=status,
        )
    except LiveEvalRunNotFoundError as exc:
        raise LiveEvalSafetyError(str(exc)) from exc
    emit_live_eval_audit(
        db,
        tenant_id=tenant_id,
        action=status,
        status="success",
        details={"evaluation_run_id": evaluation_run_id},
    )
    db.commit()
    return _row_to_response(row)


def trusted_snapshot_from_row(row: LiveEvalRunRow) -> TrustedLiveEvalSnapshot:
    return TrustedLiveEvalSnapshot(
        evaluation_run_id=row.evaluation_run_id,
        tenant_id=row.tenant_id,
        scenario_id=row.scenario_id,
        attempt_id=row.attempt_id,
        transport_mode=row.transport_mode,
        ai_mode=row.ai_mode,
        fixture_bundle_id=row.fixture_bundle_id,
        expected_sender=row.expected_sender,
        expected_recipient=row.expected_recipient,
        llm_provider=row.llm_provider,
        llm_requested_model=row.llm_requested_model,
        llm_max_calls=row.llm_max_calls,
        config_hash=row.config_hash,
        trusted=True,
    )


def new_evaluation_run_id() -> str:
    return str(uuid4())
