"""Redacted LLM eval report generation (schema 2f.3.llm)."""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.evaluation.live.constants import (
    LLM_OPERATION_IN_PROGRESS,
    LLM_OPERATION_OUTCOME_UNKNOWN,
    LLM_REPORT_SCHEMA_VERSION,
    TELEMETRY_APP_GMAIL_REPLY,
    TELEMETRY_APP_LIVE_LLM,
)
from app.evaluation.live.redaction import redact_sensitive
from app.evaluation.live.schemas import LiveEvalLlmReport

_TERMINAL_OPERATION_OUTCOMES = frozenset(
    {"succeeded", "failed", LLM_OPERATION_OUTCOME_UNKNOWN}
)


def _resolve_workflow_sha() -> str | None:
    sha = (os.environ.get("BUILD_GIT_SHA") or os.environ.get("GITHUB_SHA") or "").strip()
    if not sha or sha.lower() in {"abc123", "abc", "abc1234"}:
        return None
    return sha


def _event_metadata(event: dict[str, Any]) -> dict[str, Any]:
    metadata = event.get("redacted_metadata") or event.get("metadata") or {}
    return metadata if isinstance(metadata, dict) else {}


def _metadata_provider(metadata: dict[str, Any]) -> str | None:
    provider = metadata.get("llm_provider") or metadata.get("provider")
    return str(provider) if provider else None


def _metadata_requested_model(metadata: dict[str, Any]) -> str | None:
    requested = metadata.get("llm_requested_model") or metadata.get("requested_model")
    return str(requested) if requested else None


def _merge_operation_metadata(*metadata_blocks: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for block in metadata_blocks:
        for key, value in block.items():
            if value is not None:
                merged[key] = value
    return merged


def _operation_sort_key(operation: dict[str, Any]) -> tuple[int, str, str]:
    ordinal = operation.get("ordinal")
    ordinal_value = int(ordinal) if isinstance(ordinal, int) else 999
    return (
        ordinal_value,
        str(operation.get("prompt_name") or ""),
        str(operation.get("operation_key") or ""),
    )


def _resolve_operation_state(
  terminal_outcomes: set[str],
) -> tuple[str, str | None]:
    if len(terminal_outcomes) > 1:
        ordered = ",".join(sorted(terminal_outcomes))
        return (
            "conflict",
            f"conflicting_terminal_outcomes: {ordered}",
        )
    if len(terminal_outcomes) == 1:
        return next(iter(terminal_outcomes)), None
    return LLM_OPERATION_IN_PROGRESS, None


def _build_operation_export(
    *,
    operation_key: str,
    prompt_name: str | None,
    state: str,
    merged_metadata: dict[str, Any],
    failure_reason: str | None = None,
) -> dict[str, Any]:
    return {
        "operation_key": operation_key,
        "prompt_name": prompt_name or merged_metadata.get("prompt_name"),
        "ordinal": merged_metadata.get("ordinal"),
        "state": state,
        "outcome": state,
        "provider": _metadata_provider(merged_metadata),
        "requested_model": _metadata_requested_model(merged_metadata),
        "returned_model": merged_metadata.get("returned_model"),
        "finish_reason": merged_metadata.get("finish_reason"),
        "schema_validation_status": merged_metadata.get("schema_validation_status"),
        "input_tokens": merged_metadata.get("input_tokens"),
        "output_tokens": merged_metadata.get("output_tokens"),
        "total_tokens": merged_metadata.get("total_tokens"),
        "latency_ms": merged_metadata.get("latency_ms"),
        "output_hash": merged_metadata.get("output_hash"),
        "retry_count": merged_metadata.get("retry_count"),
        "used_fallback": merged_metadata.get("fallback_used"),
        "failure_reason": failure_reason or merged_metadata.get("failure_reason"),
    }


def _summarize_llm_events(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grouped_events: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if event.get("category") != TELEMETRY_APP_LIVE_LLM:
            continue
        outcome = str(event.get("outcome") or "")
        if outcome == "blocked":
            continue
        operation_key = event.get("operation_key")
        if not operation_key:
            continue
        grouped_events[str(operation_key)].append(event)

    operations: list[dict[str, Any]] = []
    totals = {
        "attempted": 0,
        "succeeded": 0,
        "failed": 0,
        "outcome_unknown": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "latency_ms": 0,
    }

    for operation_key in sorted(grouped_events):
        group = grouped_events[operation_key]
        reservation_events = [
            event
            for event in group
            if str(event.get("outcome") or "") == LLM_OPERATION_IN_PROGRESS
        ]
        terminal_events = [
            event
            for event in group
            if str(event.get("outcome") or "") in _TERMINAL_OPERATION_OUTCOMES
        ]
        terminal_outcomes = {
            str(event.get("outcome") or "")
            for event in terminal_events
        }

        reservation_metadata = _merge_operation_metadata(
            *(_event_metadata(event) for event in reservation_events)
        )
        terminal_metadata = _merge_operation_metadata(
            *(_event_metadata(event) for event in terminal_events)
        )
        merged_metadata = _merge_operation_metadata(
            reservation_metadata,
            terminal_metadata,
        )

        prompt_name = next(
            (
                event.get("operation")
                for event in group
                if event.get("operation")
            ),
            None,
        )
        state, conflict_reason = _resolve_operation_state(terminal_outcomes)
        operation = _build_operation_export(
            operation_key=operation_key,
            prompt_name=str(prompt_name) if prompt_name else None,
            state=state,
            merged_metadata=merged_metadata,
            failure_reason=conflict_reason,
        )
        operations.append(operation)

        totals["attempted"] += 1
        if state == "succeeded":
            totals["succeeded"] += 1
        elif state == "failed" or state == "conflict":
            totals["failed"] += 1
        elif state == LLM_OPERATION_OUTCOME_UNKNOWN:
            totals["outcome_unknown"] += 1

        if terminal_metadata:
            totals["input_tokens"] += int(terminal_metadata.get("input_tokens") or 0)
            totals["output_tokens"] += int(terminal_metadata.get("output_tokens") or 0)
            totals["total_tokens"] += int(terminal_metadata.get("total_tokens") or 0)
            totals["latency_ms"] += int(terminal_metadata.get("latency_ms") or 0)

    operations.sort(key=_operation_sort_key)
    return operations, totals


def _count_external_writes(events: list[dict[str, Any]]) -> dict[str, int]:
    from app.evaluation.live.constants import INTERNAL_LIVE_EVAL_TELEMETRY_CATEGORIES

    external = 0
    gmail_sends = 0
    gmail_mutations = 0
    app_replies = 0
    for event in events:
        if event.get("outcome") != "succeeded":
            continue
        category = str(event.get("category") or "")
        if category in INTERNAL_LIVE_EVAL_TELEMETRY_CATEGORIES:
            continue
        if category.startswith("testbot_"):
            continue
        if category.endswith("_blocked"):
            continue
        integration = str(event.get("integration_type") or "")
        if integration:
            external += 1
        if "send" in category and "gmail" in category:
            gmail_sends += 1
        if category == TELEMETRY_APP_GMAIL_REPLY:
            app_replies += 1
        if integration == "google_mail" and category not in INTERNAL_LIVE_EVAL_TELEMETRY_CATEGORIES:
            gmail_mutations += 1
    return {
        "external_action_writes": external,
        "gmail_sends": gmail_sends,
        "gmail_mutations": gmail_mutations,
        "app_replies": app_replies,
    }


def build_live_eval_llm_report(
    *,
    evaluation_run_id: str,
    run: dict[str, Any],
    observation: dict[str, Any] | None = None,
    semantic_assertions: list[str] | None = None,
    result: str = "dry_run",
    failure_category: str | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    scenario_content_hash: str | None = None,
) -> LiveEvalLlmReport:
    observation = observation or {}
    events = observation.get("events") or []
    job = observation.get("job") or {}
    operations, token_usage = _summarize_llm_events(events)
    write_counts = _count_external_writes(events)

    return LiveEvalLlmReport(
        report_schema_version=LLM_REPORT_SCHEMA_VERSION,
        evaluation_run_id=evaluation_run_id,
        scenario_id=run.get("scenario_id"),
        scenario_version=run.get("scenario_version") or 1,
        scenario_content_hash=scenario_content_hash,
        dataset_version=run.get("dataset_version") or "k2e-v1",
        workflow_sha=_resolve_workflow_sha(),
        config_hash=run.get("config_hash"),
        transport_mode=run.get("transport_mode"),
        ai_mode=run.get("ai_mode"),
        llm_provider=run.get("llm_provider"),
        llm_requested_model=run.get("llm_requested_model"),
        result=result,  # type: ignore[arg-type]
        failure_category=failure_category,
        started_at=started_at,
        completed_at=completed_at or datetime.now(timezone.utc),
        operations=operations,
        token_usage=token_usage,
        semantic_assertions=semantic_assertions or [],
        job_id=job.get("job_id"),
        job_status=job.get("job_status"),
        pending_approval_count=job.get("pending_approval_count"),
        external_action_writes=write_counts["external_action_writes"],
        gmail_sends=write_counts["gmail_sends"],
        gmail_mutations=write_counts["gmail_mutations"],
        app_replies=write_counts["app_replies"],
        run_status=run.get("status"),
        issues=semantic_assertions or [],
        redacted_diagnostics=redact_sensitive(
            {
                "classification": job.get("classification"),
                "policy": job.get("policy"),
                "service_profile": job.get("service_profile"),
            }
        ),
    )


def write_llm_report_atomic(evaluation_run_id: str, report: LiveEvalLlmReport):
    from app.evaluation.live.journal import ensure_run_directory
    import json
    import tempfile

    directory = ensure_run_directory(evaluation_run_id)
    target = directory / "llm_report.json"
    payload = redact_sensitive(report.model_dump(mode="json"))
    fd, tmp_name = tempfile.mkstemp(dir=directory, prefix=".llm_report.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
        os.chmod(target, 0o640)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return target


LLM_FAILURE_REPORT_SCHEMA_VERSION = "2f.3.llm-failure"


def build_live_eval_llm_failure_report(
    *,
    evaluation_run_id: str | None,
    scenario_id: str,
    failure_stage: str,
    failure_category: str | None = None,
    result: str = "failed",
    error: str | BaseException | None = None,
    workflow_sha: str | None = None,
    observation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.evaluation.live.provider_redaction import sanitize_provider_error_message

    events = (observation or {}).get("events") or []
    operations, token_usage = _summarize_llm_events(events)
    write_counts = _count_external_writes(events)
    payload = {
        "report_schema_version": LLM_FAILURE_REPORT_SCHEMA_VERSION,
        "evaluation_run_id": evaluation_run_id,
        "scenario_id": scenario_id,
        "workflow_sha": workflow_sha or _resolve_workflow_sha(),
        "result": result,
        "failure_stage": failure_stage,
        "failure_category": failure_category,
        "redacted_error": sanitize_provider_error_message(error) or None,
        "operations": operations,
        "token_usage": token_usage,
        "external_action_writes": write_counts["external_action_writes"],
        "gmail_sends": write_counts["gmail_sends"],
        "gmail_mutations": write_counts["gmail_mutations"],
        "app_replies": write_counts["app_replies"],
        "live_llm_calls": token_usage.get("attempted", 0),
        "llm_operations": token_usage.get("attempted", 0),
        "external_writes": write_counts["external_action_writes"],
    }
    return redact_sensitive(payload)


def write_llm_failure_report_atomic(
    path: str | os.PathLike[str],
    payload: dict[str, Any],
) -> Path:
    import json
    import tempfile

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=target.parent, prefix=".llm_failure.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(redact_sensitive(payload), handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, target)
        os.chmod(target, 0o640)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return target
