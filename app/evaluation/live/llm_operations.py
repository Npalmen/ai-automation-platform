"""Persistent LLM operation reservation and call budget for live LLM eval."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.evaluation.live.constants import (
    EVENT_OUTCOME_BLOCKED,
    EVENT_OUTCOME_FAILED,
    EVENT_OUTCOME_SUCCEEDED,
    LLM_OPERATION_IN_PROGRESS,
    LLM_OPERATION_OUTCOME_UNKNOWN,
    S01_LLM_MAX_CALLS,
    S01_LLM_PROMPT_ORDER,
    TELEMETRY_APP_LIVE_LLM,
)
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.schemas import TrustedLiveEvalSnapshot
from app.evaluation.live.telemetry import record_live_eval_external_event
from app.repositories.postgres.live_eval_models import LiveEvalLlmOperationRow
from app.repositories.postgres.live_eval_repository import (
    LiveEvalLlmOperationConflictError,
    LiveEvalLlmOperationRepository,
)

_INTEGRATION_TYPE_LLM = "live_llm"
_TERMINAL_OPERATION_STATUSES = frozenset(
    {EVENT_OUTCOME_SUCCEEDED, EVENT_OUTCOME_FAILED, LLM_OPERATION_OUTCOME_UNKNOWN}
)
_PROMPT_TO_ORDINAL = {prompt: index + 1 for index, prompt in enumerate(S01_LLM_PROMPT_ORDER)}
_ORDINAL_TO_PROMPT = {index + 1: prompt for index, prompt in enumerate(S01_LLM_PROMPT_ORDER)}


def prompt_ordinal(prompt_name: str) -> int:
    ordinal = _PROMPT_TO_ORDINAL.get(prompt_name)
    if ordinal is None:
        raise LiveEvalSafetyError(f"prompt {prompt_name!r} is not in S01 LLM order")
    return ordinal


def ordinal_prompt_name(ordinal: int) -> str:
    prompt_name = _ORDINAL_TO_PROMPT.get(ordinal)
    if prompt_name is None:
        raise LiveEvalSafetyError(f"LLM ordinal {ordinal} is outside S01 range 1-4")
    return prompt_name


def build_llm_operation_key(
    *,
    evaluation_run_id: str,
    prompt_name: str,
    ordinal: int,
) -> str:
    return f"{evaluation_run_id}:{TELEMETRY_APP_LIVE_LLM}:{prompt_name}:{ordinal}"


def _hash_validated_output(output: dict[str, Any]) -> str:
    encoded = json.dumps(output, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _snapshot_call_budget(snapshot: TrustedLiveEvalSnapshot) -> int:
    budget = snapshot.llm_max_calls
    if budget is None:
        raise LiveEvalSafetyError("live_llm missing pinned call budget in trusted snapshot")
    if snapshot.scenario_id == "S01_lead_laddbox_quality" and budget != S01_LLM_MAX_CALLS:
        raise LiveEvalSafetyError(
            f"live_llm call budget must be {S01_LLM_MAX_CALLS} for S01, got {budget}"
        )
    return budget


def _validate_provider_contract(
    snapshot: TrustedLiveEvalSnapshot,
    *,
    requested_provider: str | None,
    requested_model: str | None,
) -> tuple[str, str]:
    pinned_provider = (snapshot.llm_provider or "").strip()
    pinned_model = (snapshot.llm_requested_model or "").strip()
    if not pinned_provider or not pinned_model:
        raise LiveEvalSafetyError("live_llm missing pinned provider/model in trusted snapshot")
    if requested_provider and requested_provider.strip() != pinned_provider:
        raise LiveEvalSafetyError("live_llm provider mismatch before provider call")
    if requested_model and requested_model.strip() != pinned_model:
        raise LiveEvalSafetyError("live_llm model mismatch before provider call")
    return pinned_provider, pinned_model


def _validate_prompt_contract(prompt_name: str, ordinal: int) -> None:
    expected = prompt_ordinal(prompt_name)
    if expected != ordinal:
        raise LiveEvalSafetyError(
            f"prompt {prompt_name!r} cannot use ordinal {ordinal}; expected {expected}"
        )


def has_outcome_unknown_for_run(db: Session, evaluation_run_id: str) -> bool:
    return LiveEvalLlmOperationRepository.has_status_for_run(
        db,
        evaluation_run_id,
        status=LLM_OPERATION_OUTCOME_UNKNOWN,
    )


def count_provider_attempts(db: Session, evaluation_run_id: str) -> int:
    return LiveEvalLlmOperationRepository.count_terminal_operations(db, evaluation_run_id)


def count_succeeded_llm_operations(db: Session, evaluation_run_id: str) -> int:
    return LiveEvalLlmOperationRepository.count_by_status(
        db,
        evaluation_run_id,
        status=EVENT_OUTCOME_SUCCEEDED,
    )


def count_llm_operations_for_run(db: Session, evaluation_run_id: str) -> int:
    return len(LiveEvalLlmOperationRepository.list_for_run(db, evaluation_run_id))


def _record_blocked_telemetry(
    db: Session,
    *,
    snapshot: TrustedLiveEvalSnapshot,
    operation_key: str,
    prompt_name: str,
    reason: str,
    ordinal: int,
    job_id: str | None = None,
    pipeline_run_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    payload = {
        "reason": reason,
        "ordinal": ordinal,
        "llm_provider": snapshot.llm_provider,
        "llm_requested_model": snapshot.llm_requested_model,
    }
    if metadata:
        payload.update(metadata)
    record_live_eval_external_event(
        db,
        operation_key=operation_key,
        outcome=EVENT_OUTCOME_BLOCKED,
        category=TELEMETRY_APP_LIVE_LLM,
        operation=prompt_name,
        integration_type=_INTEGRATION_TYPE_LLM,
        job_id=job_id,
        pipeline_run_id=pipeline_run_id,
        snapshot=snapshot,
        metadata=payload,
    )
    db.commit()


def _prior_operation_blocks_next(
    db: Session,
    *,
    evaluation_run_id: str,
    ordinal: int,
) -> LiveEvalLlmOperationRow | None:
    if ordinal <= 1:
        return None
    prior = LiveEvalLlmOperationRepository.get_by_run_and_prompt(
        db,
        evaluation_run_id=evaluation_run_id,
        prompt_name=ordinal_prompt_name(ordinal - 1),
    )
    if prior is None:
        return None
    if prior.status != EVENT_OUTCOME_SUCCEEDED:
        return prior
    return None


def reserve_live_llm_operation(
    db: Session,
    *,
    snapshot: TrustedLiveEvalSnapshot,
    prompt_name: str,
    requested_provider: str | None = None,
    requested_model: str | None = None,
    job_id: str | None = None,
    pipeline_run_id: str | None = None,
) -> str:
    """Atomically reserve one permanent in_progress LLM operation before provider call."""
    if snapshot.scenario_id != "S01_lead_laddbox_quality":
        raise LiveEvalSafetyError(
            f"LLM operation reservation not defined for {snapshot.scenario_id!r}"
        )

    call_budget = _snapshot_call_budget(snapshot)
    pinned_provider, pinned_model = _validate_provider_contract(
        snapshot,
        requested_provider=requested_provider,
        requested_model=requested_model,
    )
    ordinal = prompt_ordinal(prompt_name)
    _validate_prompt_contract(prompt_name, ordinal)
    operation_key = build_llm_operation_key(
        evaluation_run_id=snapshot.evaluation_run_id,
        prompt_name=prompt_name,
        ordinal=ordinal,
    )

    if has_outcome_unknown_for_run(db, snapshot.evaluation_run_id):
        raise LiveEvalSafetyError("LLM outcome_unknown blocks further operations")

    existing = LiveEvalLlmOperationRepository.get_by_operation_key(db, operation_key)
    if existing is not None and existing.status == LLM_OPERATION_IN_PROGRESS:
        raise LiveEvalSafetyError(f"LLM operation already in progress for {prompt_name!r}")

    succeeded = count_succeeded_llm_operations(db, snapshot.evaluation_run_id)
    if succeeded >= call_budget:
        _record_blocked_telemetry(
            db,
            snapshot=snapshot,
            operation_key=operation_key,
            prompt_name=prompt_name,
            reason="budget_exhausted",
            ordinal=ordinal,
            job_id=job_id,
            pipeline_run_id=pipeline_run_id,
        )
        raise LiveEvalSafetyError("LLM call budget exhausted")

    if existing is not None and existing.status in _TERMINAL_OPERATION_STATUSES:
        raise LiveEvalSafetyError(f"retry blocked for LLM operation {prompt_name!r}")

    for other in LiveEvalLlmOperationRepository.list_for_run(db, snapshot.evaluation_run_id):
        if other.status == LLM_OPERATION_IN_PROGRESS and other.request_ordinal != ordinal:
            raise LiveEvalSafetyError(
                f"LLM ordinal {ordinal} blocked while ordinal {other.request_ordinal} is in progress"
            )

    prior_blocker = _prior_operation_blocks_next(
        db,
        evaluation_run_id=snapshot.evaluation_run_id,
        ordinal=ordinal,
    )
    if prior_blocker is not None:
        raise LiveEvalSafetyError(
            f"LLM ordinal {ordinal} blocked while prior step is {prior_blocker.status!r}"
        )

    if ordinal != succeeded + 1:
        _record_blocked_telemetry(
            db,
            snapshot=snapshot,
            operation_key=operation_key,
            prompt_name=prompt_name,
            reason="prompt_order_violation",
            ordinal=ordinal,
            job_id=job_id,
            pipeline_run_id=pipeline_run_id,
            metadata={"expected_ordinal": succeeded + 1},
        )
        raise LiveEvalSafetyError(
            f"LLM prompt order violation: expected ordinal {succeeded + 1}, got {ordinal}"
        )

    started_at = datetime.now(timezone.utc)
    row = LiveEvalLlmOperationRow(
        tenant_id=snapshot.tenant_id,
        evaluation_run_id=snapshot.evaluation_run_id,
        scenario_id=snapshot.scenario_id,
        prompt_name=prompt_name,
        request_ordinal=ordinal,
        operation_key=operation_key,
        prompt_version=prompt_name,
        llm_provider=pinned_provider,
        requested_model=pinned_model,
        status=LLM_OPERATION_IN_PROGRESS,
        provider_started_at=started_at,
        created_at=started_at,
        updated_at=started_at,
    )
    try:
        LiveEvalLlmOperationRepository.reserve_operation(db, row)
    except LiveEvalLlmOperationConflictError as exc:
        raise LiveEvalSafetyError(
            f"concurrent LLM reservation blocked for {prompt_name!r}"
        ) from exc

    record_live_eval_external_event(
        db,
        operation_key=operation_key,
        outcome=LLM_OPERATION_IN_PROGRESS,
        category=TELEMETRY_APP_LIVE_LLM,
        operation=prompt_name,
        integration_type=_INTEGRATION_TYPE_LLM,
        job_id=job_id,
        pipeline_run_id=pipeline_run_id,
        snapshot=snapshot,
        metadata={
            "ordinal": ordinal,
            "llm_provider": pinned_provider,
            "llm_requested_model": pinned_model,
        },
    )
    db.commit()
    return operation_key


def record_live_llm_operation_result(
    db: Session,
    *,
    operation_key: str,
    snapshot: TrustedLiveEvalSnapshot,
    prompt_name: str,
    outcome: str,
    requested_model: str,
    returned_model: str | None = None,
    job_id: str | None = None,
    pipeline_run_id: str | None = None,
    latency_ms: int | None = None,
    usage: dict[str, int] | None = None,
    finish_reason: str | None = None,
    schema_validation_status: str | None = None,
    failure_reason: str | None = None,
    validated_output: dict[str, Any] | None = None,
    retry_count: int = 0,
) -> bool:
    if outcome not in _TERMINAL_OPERATION_STATUSES:
        raise LiveEvalSafetyError(f"invalid terminal LLM operation outcome {outcome!r}")

    completed_at = datetime.now(timezone.utc)
    updates: dict[str, Any] = {
        "completed_at": completed_at,
        "returned_model": returned_model,
        "latency_ms": latency_ms,
        "finish_reason": finish_reason,
        "schema_validation_status": schema_validation_status,
        "failure_reason": failure_reason,
    }
    if usage:
        updates["input_tokens"] = usage.get("prompt_tokens", 0)
        updates["output_tokens"] = usage.get("completion_tokens", 0)
        updates["total_tokens"] = usage.get("total_tokens", 0)
    if validated_output is not None:
        updates["output_hash"] = _hash_validated_output(validated_output)

    transitioned = LiveEvalLlmOperationRepository.transition_status(
        db,
        operation_key=operation_key,
        from_status=LLM_OPERATION_IN_PROGRESS,
        to_status=outcome,
        updates=updates,
    )
    if not transitioned:
        existing = LiveEvalLlmOperationRepository.get_by_operation_key(db, operation_key)
        if existing is not None and existing.status in _TERMINAL_OPERATION_STATUSES:
            return False
        raise LiveEvalSafetyError(
            f"LLM operation {operation_key!r} is not in_progress for result recording"
        )

    metadata: dict[str, Any] = {
        "ordinal": prompt_ordinal(prompt_name),
        "prompt_name": prompt_name,
        "llm_provider": snapshot.llm_provider,
        "llm_requested_model": requested_model,
        "returned_model": returned_model,
        "latency_ms": latency_ms,
        "retry_count": retry_count,
        "fallback_used": False,
        "schema_validation_status": schema_validation_status,
        "failure_reason": failure_reason,
        "finish_reason": finish_reason,
    }
    if usage:
        metadata["input_tokens"] = usage.get("prompt_tokens", 0)
        metadata["output_tokens"] = usage.get("completion_tokens", 0)
        metadata["total_tokens"] = usage.get("total_tokens", 0)
    if validated_output is not None:
        metadata["output_hash"] = updates.get("output_hash")

    record_live_eval_external_event(
        db,
        operation_key=operation_key,
        outcome=outcome,
        category=TELEMETRY_APP_LIVE_LLM,
        operation=prompt_name,
        integration_type=_INTEGRATION_TYPE_LLM,
        job_id=job_id,
        pipeline_run_id=pipeline_run_id,
        snapshot=snapshot,
        started_at=completed_at,
        completed_at=completed_at,
        metadata=metadata,
    )
    db.commit()
    return True
