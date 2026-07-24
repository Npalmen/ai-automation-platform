"""Eval-specific LLM client with reservation, telemetry, and strict provenance."""

from __future__ import annotations

import json
import time
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.ai.exceptions import (
    LLMClientError,
    LLMConfigurationError,
    LLMRequestError,
    LLMResponseError,
)
from app.evaluation.fixture_ai import _active_prompt_name
from app.evaluation.live.config import LiveEvalConfig, get_live_eval_config
from app.evaluation.live.constants import (
    EVENT_OUTCOME_FAILED,
    EVENT_OUTCOME_SUCCEEDED,
    LLM_OPERATION_OUTCOME_UNKNOWN,
)
from app.evaluation.live.context import get_current_live_eval_snapshot, get_pipeline_db
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.llm_operations import (
    record_live_llm_operation_result,
    reserve_live_llm_operation,
)
from app.evaluation.live.llm_provider import PROMPT_RESPONSE_MODELS
from app.evaluation.live.model_identity import validate_returned_model_identity
from app.evaluation.live.provider_redaction import sanitize_provider_error_message
from app.evaluation.live.schemas import TrustedLiveEvalSnapshot

_OUTCOME_UNKNOWN_REASONS = frozenset(
    {"timeout", "outcome_unknown", "connection_reset", "transport_error"}
)


def classify_finish_reason_failure(finish_reason: str | None) -> str | None:
    normalized = (finish_reason or "").strip().lower()
    if normalized == "stop":
        return None
    if not normalized:
        return "incomplete_finish_reason"
    if normalized == "content_filter":
        return "safety_refusal"
    if normalized in {"length", "tool_calls", "function_call"}:
        return "incomplete_finish_reason"
    return "incomplete_finish_reason"


def classify_llm_provider_error(exc: Exception) -> str:
    message = sanitize_provider_error_message(exc).lower()
    if isinstance(exc, TimeoutError) or "timeout" in message:
        return "timeout"
    if isinstance(exc, LLMConfigurationError):
        return "authentication"
    if isinstance(exc, LLMRequestError):
        if "429" in message or "rate" in message:
            return "rate_limit"
        if "401" in message or "403" in message or "unauthorized" in message:
            return "authentication"
        if "timeout" in message:
            return "timeout"
        return "provider_error"
    if isinstance(exc, LLMResponseError):
        if "too large" in message or "length" in message:
            return "response_too_large"
        if "json" in message or "content" in message:
            return "malformed_json"
        return "provider_error"
    if isinstance(exc, ValidationError):
        return "schema_validation"
    if isinstance(exc, LiveEvalSafetyError):
        return "safety_refusal"
    if isinstance(exc, LLMClientError):
        return "provider_error"
    return "outcome_unknown"


class EvalLLMClient:
    """Wraps production LLM client with persistent reservation and telemetry."""

    def __init__(
        self,
        delegate,
        *,
        snapshot: TrustedLiveEvalSnapshot,
        config: LiveEvalConfig | None = None,
        db: Session | None = None,
    ):
        self._delegate = delegate
        self._snapshot = snapshot
        self._config = config or get_live_eval_config()
        self._db = db

    def _resolve_db(self) -> Session:
        db = self._db or get_pipeline_db()
        if db is None:
            raise LiveEvalSafetyError("live_llm requires database session")
        return db

    def _resolve_prompt_name(self, prompt: str) -> str:
        prompt_name = _active_prompt_name.get()
        if not prompt_name:
            for candidate in (
                "classification_v1",
                "entity_extraction_v1",
                "lead_scoring_v1",
                "decisioning_v1",
            ):
                if candidate in prompt:
                    prompt_name = candidate
                    break
        if not prompt_name:
            raise LiveEvalSafetyError("live_llm missing active prompt_name")
        return prompt_name

    def _record_failed_operation(
        self,
        db: Session,
        *,
        operation_key: str,
        prompt_name: str,
        requested_model: str,
        latency_ms: int,
        failure_reason: str,
        returned_model: str | None = None,
        usage: dict[str, int] | None = None,
        finish_reason: str | None = None,
    ) -> None:
        record_live_llm_operation_result(
            db,
            operation_key=operation_key,
            snapshot=self._snapshot,
            prompt_name=prompt_name,
            outcome=EVENT_OUTCOME_FAILED,
            requested_model=requested_model,
            returned_model=returned_model,
            latency_ms=latency_ms,
            usage=usage,
            finish_reason=finish_reason,
            failure_reason=failure_reason,
            schema_validation_status="failed",
        )

    def _validate_schema_output(
        self,
        *,
        prompt_name: str,
        output: dict[str, Any],
    ) -> dict[str, Any]:
        response_model = PROMPT_RESPONSE_MODELS.get(prompt_name)
        if response_model is None:
            raise LLMResponseError(f"live_llm missing schema mapping for {prompt_name!r}")
        validated = response_model.model_validate(output)
        return json.loads(validated.model_dump_json())

    def generate_json(self, prompt: str) -> dict[str, Any]:
        db = self._resolve_db()
        prompt_name = self._resolve_prompt_name(prompt)
        requested_provider = self._snapshot.llm_provider
        requested_model = self._snapshot.llm_requested_model
        if not requested_model:
            raise LiveEvalSafetyError("live_llm missing pinned model in trusted snapshot")

        operation_key = reserve_live_llm_operation(
            db,
            snapshot=self._snapshot,
            prompt_name=prompt_name,
            requested_provider=requested_provider,
            requested_model=requested_model,
        )

        started = time.perf_counter()
        try:
            detailed = self._delegate.generate_json_detailed(
                prompt,
                model=requested_model,
                timeout=self._config.llm_timeout,
                max_tokens=self._config.llm_max_tokens,
                temperature=0.0,
                retry_attempts=0,
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            failure_reason = classify_llm_provider_error(exc)
            outcome = (
                LLM_OPERATION_OUTCOME_UNKNOWN
                if failure_reason in _OUTCOME_UNKNOWN_REASONS
                else EVENT_OUTCOME_FAILED
            )
            self._record_failed_operation(
                db,
                operation_key=operation_key,
                prompt_name=prompt_name,
                requested_model=requested_model,
                latency_ms=latency_ms,
                failure_reason=failure_reason,
            )
            if outcome == LLM_OPERATION_OUTCOME_UNKNOWN:
                from app.evaluation.live.registry import complete_live_eval_run

                try:
                    complete_live_eval_run(
                        db,
                        self._snapshot.evaluation_run_id,
                        tenant_id=self._snapshot.tenant_id,
                        status="aborted",
                    )
                except Exception:
                    db.rollback()
                raise LiveEvalSafetyError("LLM outcome_unknown aborted run") from exc
            if isinstance(exc, ValidationError):
                raise
            raise LLMResponseError(sanitize_provider_error_message(exc)) from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        usage = detailed.usage or {}
        returned_model_raw = detailed.returned_model
        try:
            returned_model = validate_returned_model_identity(
                requested_model=requested_model,
                returned_model=returned_model_raw,
            )
        except LiveEvalSafetyError as exc:
            self._record_failed_operation(
                db,
                operation_key=operation_key,
                prompt_name=prompt_name,
                requested_model=requested_model,
                latency_ms=latency_ms,
                returned_model=(returned_model_raw or "").strip() or None,
                failure_reason="model_mismatch",
            )
            raise LLMResponseError(sanitize_provider_error_message(exc)) from exc

        if not usage or not any(
            usage.get(key) is not None for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        ):
            self._record_failed_operation(
                db,
                operation_key=operation_key,
                prompt_name=prompt_name,
                requested_model=requested_model,
                returned_model=returned_model,
                latency_ms=latency_ms,
                failure_reason="missing_usage",
            )
            raise LLMResponseError("live_llm provider missing token usage")

        finish_reason_failure = classify_finish_reason_failure(detailed.finish_reason)
        if finish_reason_failure is not None:
            self._record_failed_operation(
                db,
                operation_key=operation_key,
                prompt_name=prompt_name,
                requested_model=requested_model,
                returned_model=returned_model,
                latency_ms=latency_ms,
                usage=usage,
                finish_reason=detailed.finish_reason,
                failure_reason=finish_reason_failure,
            )
            raise LLMResponseError(f"live_llm finish_reason {detailed.finish_reason!r} is not allowed")

        output = detailed.output
        if not isinstance(output, dict):
            self._record_failed_operation(
                db,
                operation_key=operation_key,
                prompt_name=prompt_name,
                requested_model=requested_model,
                returned_model=returned_model,
                latency_ms=latency_ms,
                usage=usage,
                finish_reason=detailed.finish_reason,
                failure_reason="malformed_json",
            )
            raise LLMResponseError("live_llm output must be a JSON object")

        try:
            validated_output = self._validate_schema_output(
                prompt_name=prompt_name,
                output=output,
            )
        except ValidationError:
            self._record_failed_operation(
                db,
                operation_key=operation_key,
                prompt_name=prompt_name,
                requested_model=requested_model,
                returned_model=returned_model,
                latency_ms=latency_ms,
                usage=usage,
                finish_reason=detailed.finish_reason,
                failure_reason="schema_validation",
            )
            raise

        record_live_llm_operation_result(
            db,
            operation_key=operation_key,
            snapshot=self._snapshot,
            prompt_name=prompt_name,
            outcome=EVENT_OUTCOME_SUCCEEDED,
            requested_model=requested_model,
            returned_model=returned_model,
            latency_ms=latency_ms,
            usage=usage,
            finish_reason=detailed.finish_reason,
            schema_validation_status="passed",
            validated_output=validated_output,
        )
        return validated_output


def build_eval_llm_client(
    *,
    snapshot: TrustedLiveEvalSnapshot | None = None,
    db: Session | None = None,
) -> EvalLLMClient:
    from app.ai.llm.client import get_llm_client

    snap = snapshot or get_current_live_eval_snapshot()
    if snap is None:
        raise LiveEvalSafetyError("live_llm missing trusted snapshot")
    return EvalLLMClient(get_llm_client(), snapshot=snap, db=db)
