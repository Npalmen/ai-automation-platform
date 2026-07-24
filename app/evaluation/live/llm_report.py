"""Redacted LLM eval report generation (schema 2f.3.llm)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.evaluation.live.constants import (
    LLM_REPORT_SCHEMA_VERSION,
    TELEMETRY_APP_GMAIL_REPLY,
    TELEMETRY_APP_LIVE_LLM,
)
from app.evaluation.live.redaction import redact_sensitive
from app.evaluation.live.schemas import LiveEvalLlmReport


def _resolve_workflow_sha() -> str | None:
    sha = (os.environ.get("BUILD_GIT_SHA") or os.environ.get("GITHUB_SHA") or "").strip()
    if not sha or sha.lower() in {"abc123", "abc", "abc1234"}:
        return None
    return sha


def _summarize_llm_events(events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
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
    for event in events:
        if event.get("category") != TELEMETRY_APP_LIVE_LLM:
            continue
        outcome = str(event.get("outcome") or "")
        if outcome == "blocked":
            continue
        totals["attempted"] += 1
        if outcome == "succeeded":
            totals["succeeded"] += 1
        elif outcome == "failed":
            totals["failed"] += 1
        elif outcome == "outcome_unknown":
            totals["outcome_unknown"] += 1
        metadata = event.get("redacted_metadata") or event.get("metadata") or {}
        totals["input_tokens"] += int(metadata.get("input_tokens") or 0)
        totals["output_tokens"] += int(metadata.get("output_tokens") or 0)
        totals["total_tokens"] += int(metadata.get("total_tokens") or 0)
        totals["latency_ms"] += int(metadata.get("latency_ms") or 0)
        operations.append(
            {
                "operation_key": event.get("operation_key"),
                "prompt_name": event.get("operation"),
                "outcome": outcome,
                "requested_model": metadata.get("requested_model"),
                "returned_model": metadata.get("returned_model"),
                "latency_ms": metadata.get("latency_ms"),
                "input_tokens": metadata.get("input_tokens"),
                "output_tokens": metadata.get("output_tokens"),
                "total_tokens": metadata.get("total_tokens"),
                "schema_validation_status": metadata.get("schema_validation_status"),
                "failure_reason": metadata.get("failure_reason"),
                "output_hash": metadata.get("output_hash"),
            }
        )
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
