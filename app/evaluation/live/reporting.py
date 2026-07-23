"""Redacted run failure summaries for CI and operators."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.evaluation.live.exit_codes import (
    EXIT_CLEANUP,
    EXIT_INFRASTRUCTURE,
    EXIT_SUCCESS,
    SAFETY_PRIORITY_EXITS,
)
from app.evaluation.live.redaction import redact_sensitive

_FAILURE_SUMMARY_SCHEMA = "2f.2-recovery"
_MAX_ERROR_LEN = 512
_GMAIL_RESPONSE_RE = re.compile(r"Response:\s*\{.*", re.DOTALL)


def _truncate_error(message: str) -> str:
    text = (message or "").strip()
    text = _GMAIL_RESPONSE_RE.sub("Response: <redacted>", text)
    if len(text) > _MAX_ERROR_LEN:
        return text[:_MAX_ERROR_LEN] + "…"
    return text


def compute_final_exit_code(
    *,
    primary_exit_code: int | None,
    cleanup_exit_code: int | None,
    artifact_status: str,
) -> int:
    """Preserve primary scenario failure over cleanup/artifact secondary failures."""
    if primary_exit_code in SAFETY_PRIORITY_EXITS:
        return primary_exit_code
    if primary_exit_code is not None and primary_exit_code != EXIT_SUCCESS:
        return primary_exit_code
    if cleanup_exit_code == EXIT_CLEANUP:
        return EXIT_CLEANUP
    if artifact_status == "missing":
        return EXIT_INFRASTRUCTURE
    return primary_exit_code if primary_exit_code is not None else EXIT_SUCCESS


@dataclass(frozen=True)
class FailureSummary:
    evaluation_run_id: str
    scenario_id: str
    attempt_id: int
    failure_category: str | None
    failed_stage: str
    primary_exit_code: int | None
    cleanup_exit_code: int | None
    artifact_status: str
    final_exit_code: int
    send_state: str
    send_attempted: bool
    send_confirmed: bool
    reconciliation_result: str
    recipient_delivery_observed: bool
    root_job_bound: bool
    cleanup_state: str
    gmail_mutations: int
    scenario_cleanup_mutations: int = 0
    workflow_cleanup_mutations: int = 0
    total_gmail_mutations: int = 0
    cleanup_adapter_called: bool = False
    cleanup_adapter_result: str | None = None
    redacted_error: str | None = None
    intake_skip_reason: str | None = None
    safety_reason: str | None = None
    workflow_sha: str | None = None
    timeout_reason: str | None = None
    timeout_job_snapshot: dict[str, Any] | None = None
    poll_attempts: int | None = None
    poll_duration_seconds: float | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
                "summary_schema_version": _FAILURE_SUMMARY_SCHEMA,
                "evaluation_run_id": self.evaluation_run_id,
                "scenario_id": self.scenario_id,
                "attempt_id": self.attempt_id,
                "failure_category": self.failure_category,
                "failed_stage": self.failed_stage,
                "primary_exit_code": self.primary_exit_code,
                "cleanup_exit_code": self.cleanup_exit_code,
                "artifact_status": self.artifact_status,
                "final_exit_code": self.final_exit_code,
                "send_state": self.send_state,
                "send_attempted": self.send_attempted,
                "send_confirmed": self.send_confirmed,
                "reconciliation_result": self.reconciliation_result,
                "recipient_delivery_observed": self.recipient_delivery_observed,
                "root_job_bound": self.root_job_bound,
                "cleanup_state": self.cleanup_state,
                "gmail_mutations": self.gmail_mutations,
                "scenario_cleanup_mutations": self.scenario_cleanup_mutations,
                "workflow_cleanup_mutations": self.workflow_cleanup_mutations,
                "total_gmail_mutations": self.total_gmail_mutations,
                "cleanup_adapter_called": self.cleanup_adapter_called,
                "cleanup_adapter_result": self.cleanup_adapter_result,
                "redacted_error": self.redacted_error,
                "intake_skip_reason": self.intake_skip_reason,
                "safety_reason": self.safety_reason,
                "workflow_sha": self.workflow_sha,
            }
        if self.timeout_reason:
            payload["timeout_reason"] = self.timeout_reason
        if self.timeout_job_snapshot:
            payload["timeout_job_snapshot"] = self.timeout_job_snapshot
        if self.poll_attempts is not None:
            payload["poll_attempts"] = self.poll_attempts
        if self.poll_duration_seconds is not None:
            payload["poll_duration_seconds"] = round(self.poll_duration_seconds, 3)
        return redact_sensitive(payload)


def build_failure_summary(
    *,
    evaluation_run_id: str,
    scenario_id: str,
    attempt_id: int,
    failure_category: str | None,
    failed_stage: str,
    primary_exit_code: int | None,
    cleanup_exit_code: int | None,
    artifact_status: str,
    send_state: str,
    send_attempted: bool,
    send_confirmed: bool,
    reconciliation_result: str,
    recipient_delivery_observed: bool,
    root_job_bound: bool,
    cleanup_state: str,
    gmail_mutations: int = 0,
    scenario_cleanup_mutations: int = 0,
    workflow_cleanup_mutations: int = 0,
    total_gmail_mutations: int | None = None,
    cleanup_adapter_called: bool = False,
    cleanup_adapter_result: str | None = None,
    error: str | BaseException | None = None,
    intake_skip_reason: str | None = None,
    safety_reason: str | None = None,
    workflow_sha: str | None = None,
    timeout_reason: str | None = None,
    timeout_job_snapshot: dict[str, Any] | None = None,
    poll_attempts: int | None = None,
    poll_duration_seconds: float | None = None,
) -> FailureSummary:
    final_exit_code = compute_final_exit_code(
        primary_exit_code=primary_exit_code,
        cleanup_exit_code=cleanup_exit_code,
        artifact_status=artifact_status,
    )
    redacted_error = _truncate_error(str(error)) if error else None
    resolved_total = (
        total_gmail_mutations
        if total_gmail_mutations is not None
        else scenario_cleanup_mutations + workflow_cleanup_mutations
    )
    if gmail_mutations == 0 and resolved_total:
        resolved_gmail_mutations = resolved_total
    else:
        resolved_gmail_mutations = gmail_mutations or resolved_total
    return FailureSummary(
        evaluation_run_id=evaluation_run_id,
        scenario_id=scenario_id,
        attempt_id=attempt_id,
        failure_category=failure_category,
        failed_stage=failed_stage,
        primary_exit_code=primary_exit_code,
        cleanup_exit_code=cleanup_exit_code,
        artifact_status=artifact_status,
        final_exit_code=final_exit_code,
        send_state=send_state,
        send_attempted=send_attempted,
        send_confirmed=send_confirmed,
        reconciliation_result=reconciliation_result,
        recipient_delivery_observed=recipient_delivery_observed,
        root_job_bound=root_job_bound,
        cleanup_state=cleanup_state,
        gmail_mutations=resolved_gmail_mutations,
        scenario_cleanup_mutations=scenario_cleanup_mutations,
        workflow_cleanup_mutations=workflow_cleanup_mutations,
        total_gmail_mutations=resolved_total,
        cleanup_adapter_called=cleanup_adapter_called,
        cleanup_adapter_result=cleanup_adapter_result,
        redacted_error=redacted_error,
        intake_skip_reason=intake_skip_reason,
        safety_reason=safety_reason,
        workflow_sha=workflow_sha,
        timeout_reason=timeout_reason,
        timeout_job_snapshot=timeout_job_snapshot,
        poll_attempts=poll_attempts,
        poll_duration_seconds=poll_duration_seconds,
    )


def emit_run_summary_stdout(summary: FailureSummary) -> None:
    print(json.dumps(summary.to_dict(), ensure_ascii=False))


_FIXTURE_WORKFLOW_SHA_MARKERS = frozenset({"abc123", "abc", "abc1234"})


def _resolve_workflow_sha_for_summary() -> str | None:
    sha = (os.environ.get("BUILD_GIT_SHA") or os.environ.get("GITHUB_SHA") or "").strip()
    if not sha or sha.lower() in _FIXTURE_WORKFLOW_SHA_MARKERS:
        return None
    return sha


def write_github_step_summary(summary: FailureSummary) -> None:
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return
    payload = summary.to_dict()
    workflow_sha = payload.get("workflow_sha") or _resolve_workflow_sha_for_summary()
    lines = [
        "## Live Gmail eval run summary",
        f"- evaluation_run_id: `{payload['evaluation_run_id']}`",
        f"- scenario_id: `{payload['scenario_id']}`",
        f"- attempt_id: {payload['attempt_id']}",
    ]
    if workflow_sha:
        lines.append(f"- workflow_sha: `{workflow_sha}`")
    lines.extend(
        [
        f"- final_exit_code: **{payload['final_exit_code']}**",
        f"- primary_exit_code: {payload['primary_exit_code']}",
        f"- cleanup_exit_code: {payload['cleanup_exit_code']}",
        f"- artifact_status: `{payload['artifact_status']}`",
        f"- failed_stage: `{payload['failed_stage']}`",
        f"- send_state: `{payload['send_state']}`",
        f"- send_attempted: {payload['send_attempted']}",
        f"- send_confirmed: {payload['send_confirmed']}",
        f"- reconciliation_result: `{payload['reconciliation_result']}`",
        f"- recipient_delivery_observed: {payload['recipient_delivery_observed']}",
        f"- root_job_bound: {payload['root_job_bound']}",
        f"- cleanup_state: `{payload['cleanup_state']}`",
        f"- gmail_mutations: {payload['gmail_mutations']}",
        f"- scenario_cleanup_mutations: {payload.get('scenario_cleanup_mutations', 0)}",
        f"- workflow_cleanup_mutations: {payload.get('workflow_cleanup_mutations', 0)}",
        f"- total_gmail_mutations: {payload.get('total_gmail_mutations', payload['gmail_mutations'])}",
        ]
    )
    if payload.get("cleanup_adapter_result"):
        lines.append(f"- cleanup_adapter_result: `{payload['cleanup_adapter_result']}`")
    if payload.get("failure_category"):
        lines.append(f"- failure_category: `{payload['failure_category']}`")
    if payload.get("intake_skip_reason"):
        lines.append(f"- intake_skip_reason: `{payload['intake_skip_reason']}`")
    if payload.get("safety_reason"):
        lines.append(f"- safety_reason: `{payload['safety_reason']}`")
    if payload.get("timeout_reason"):
        lines.append(f"- timeout_reason: `{payload['timeout_reason']}`")
    if payload.get("poll_attempts") is not None:
        lines.append(f"- poll_attempts: {payload['poll_attempts']}")
    if payload.get("redacted_error"):
        lines.append(f"- redacted_error: {payload['redacted_error']}")
    Path(summary_path).write_text("\n".join(lines) + "\n", encoding="utf-8")
