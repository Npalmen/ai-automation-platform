"""Pipeline polling helpers for live-eval observers."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from app.evaluation.live.errors import LiveEvalPipelinePollError

_PIPELINE_SUCCESS_STATUS = "awaiting_approval"
_DEFAULT_SUCCESS_STATUSES = frozenset({_PIPELINE_SUCCESS_STATUS})
_UNEXPECTED_TERMINAL_STATUSES = frozenset(
    {"completed", "manual_review", "cancelled", "rejected"}
)
_FAIL_FAST_REASONS = frozenset(
    {
        "pipeline_not_started",
        "observer_consistency_failure",
        "unexpected_terminal_status",
        "pipeline_failed",
    }
)


@dataclass(frozen=True)
class PipelinePollResult:
    observation: dict[str, Any]
    poll_attempts: int
    poll_duration_seconds: float


def build_redacted_job_snapshot(observation: dict[str, Any]) -> dict[str, Any]:
    """Redacted job snapshot for timeout artifacts — no bodies, tokens, or prompts."""
    run = observation.get("run") or {}
    job = observation.get("job") or {}
    policy = job.get("policy") or {}
    classification = job.get("classification") or {}
    records = job.get("decision_records") or []
    type_counts: dict[str, int] = {}
    processor_names: list[str] = []
    for row in records:
        record_type = str(row.get("record_type") or "unknown")
        type_counts[record_type] = type_counts.get(record_type, 0) + 1
        processor_name = row.get("processor_name")
        if processor_name:
            processor_names.append(str(processor_name))
    return {
        "job_id": job.get("job_id"),
        "tenant_id": run.get("tenant_id"),
        "observed_status": job.get("job_status"),
        "pipeline_run_id": job.get("pipeline_run_id"),
        "processor_names": processor_names[-5:],
        "approval_count": job.get("pending_approval_count"),
        "policy_authorization": policy.get("policy_authorization"),
        "policy_decision": policy.get("decision"),
        "recommended_next_step": policy.get("recommended_next_step"),
        "detected_job_type": classification.get("detected_job_type"),
        "decision_record_type_counts": type_counts,
        "root_job_bound": bool(run.get("root_job_id")),
        "root_gmail_message_id_present": bool(run.get("root_gmail_message_id")),
    }


def classify_poll_outcome(
    observation: dict[str, Any],
    *,
    poll_attempts: int,
    previous_status: str | None,
    success_statuses: frozenset[str] | None = None,
) -> str | None:
    """Return a typed timeout/failure reason, or None when polling should continue."""
    run = observation.get("run") or {}
    job = observation.get("job") or {}
    status = job.get("job_status")
    allowed_success = success_statuses or _DEFAULT_SUCCESS_STATUSES

    if not run.get("root_job_id"):
        return "pipeline_not_started"

    if not job:
        return "observer_consistency_failure"

    if status in allowed_success:
        return None

    if status == "failed":
        return "pipeline_failed"

    unexpected = set(_UNEXPECTED_TERMINAL_STATUSES)
    unexpected -= allowed_success
    if status in unexpected:
        return "unexpected_terminal_status"

    if status == "processing" and poll_attempts > 1 and status == previous_status:
        return "pipeline_stalled"

    if status in (None, "", "pending", "processing"):
        return None

    return "job_timeout_unknown"


def poll_until_decision_record(
    fetch: Callable[[], dict[str, Any]],
    *,
    record_type: str,
    timeout_seconds: float,
    on_poll: Callable[[dict[str, Any]], None] | None = None,
) -> PipelinePollResult:
    """Poll until a decision record type appears in job observation or timeout."""
    started = time.monotonic()
    deadline = started + timeout_seconds
    delay = 2.0
    poll_attempts = 0
    last: dict[str, Any] = {}

    while time.monotonic() < deadline:
        poll_attempts += 1
        last = fetch()
        if on_poll:
            on_poll(last)
        job = last.get("job") or {}
        records = job.get("decision_records") or []
        if any(str(row.get("record_type") or "") == record_type for row in records):
            return PipelinePollResult(
                observation=last,
                poll_attempts=poll_attempts,
                poll_duration_seconds=time.monotonic() - started,
            )
        time.sleep(delay)
        delay = min(delay * 1.5, 30.0)

    raise _raise_poll_error("decision_record_timeout", last, poll_attempts, started)


def poll_until_provider_execution_outcome(
    fetch: Callable[[], dict[str, Any]],
    *,
    timeout_seconds: float,
    on_poll: Callable[[dict[str, Any]], None] | None = None,
) -> PipelinePollResult:
    """Poll until execution_outcome carries provider_message_id (not approval alone)."""
    from app.evaluation.live.provider_recipient_verification import (
        provider_execution_outcome_ready,
    )

    started = time.monotonic()
    deadline = started + timeout_seconds
    delay = 2.0
    poll_attempts = 0
    last: dict[str, Any] = {}

    while time.monotonic() < deadline:
        poll_attempts += 1
        last = fetch()
        if on_poll:
            on_poll(last)
        if provider_execution_outcome_ready(last):
            return PipelinePollResult(
                observation=last,
                poll_attempts=poll_attempts,
                poll_duration_seconds=time.monotonic() - started,
            )
        time.sleep(delay)
        delay = min(delay * 1.5, 30.0)

    raise _raise_poll_error("provider_execution_outcome_timeout", last, poll_attempts, started)


def poll_pipeline_observation(
    fetch: Callable[[], dict[str, Any]],
    *,
    timeout_seconds: float,
    on_poll: Callable[[dict[str, Any]], None] | None = None,
    success_statuses: frozenset[str] | None = None,
) -> PipelinePollResult:
    """Poll until a success terminal status, a typed terminal failure, or timeout."""
    started = time.monotonic()
    deadline = started + timeout_seconds
    delay = 2.0
    poll_attempts = 0
    previous_status: str | None = None
    last: dict[str, Any] = {}
    allowed_success = success_statuses or _DEFAULT_SUCCESS_STATUSES

    while time.monotonic() < deadline:
        poll_attempts += 1
        last = fetch()
        if on_poll:
            on_poll(last)

        job = last.get("job") or {}
        status = job.get("job_status")
        if status in allowed_success:
            return PipelinePollResult(
                observation=last,
                poll_attempts=poll_attempts,
                poll_duration_seconds=time.monotonic() - started,
            )

        reason = classify_poll_outcome(
            last,
            poll_attempts=poll_attempts,
            previous_status=previous_status,
            success_statuses=allowed_success,
        )
        if reason in _FAIL_FAST_REASONS:
            raise _raise_poll_error(reason, last, poll_attempts, started)

        previous_status = status if isinstance(status, str) else previous_status
        time.sleep(delay)
        delay = min(delay * 1.5, 30.0)

    raise _raise_poll_error("pipeline_stalled", last, poll_attempts, started)


def _raise_poll_error(
    reason: str,
    observation: dict[str, Any],
    poll_attempts: int,
    started: float,
) -> LiveEvalPipelinePollError:
    return LiveEvalPipelinePollError(
        timeout_reason=reason,
        job_snapshot=build_redacted_job_snapshot(observation),
        poll_attempts=poll_attempts,
        poll_duration_seconds=time.monotonic() - started,
    )
