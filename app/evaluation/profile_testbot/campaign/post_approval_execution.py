"""Post-approval reply execution observation for profile semi-auto harness."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.provider_recipient_verification import (
    ProviderExecutionOutcome,
    extract_provider_execution_outcome,
    provider_execution_outcome_ready,
)

TERMINAL_SUCCESS_STATUSES = frozenset({"succeeded", "executed", "success"})
TERMINAL_FAILURE_STATUSES = frozenset({"failed", "skipped"})
OUTCOME_UNKNOWN_STATUSES = frozenset(
    {"outcome_unknown", "reconciliation_required", "pending_reconciliation"}
)


@dataclass
class ReplyExecutionEvidence:
    inbound_provider_message_id: str | None = None
    inbound_rfc_message_id: str | None = None
    reply_action_operation_id: str | None = None
    reply_execution_status: str | None = None
    reply_provider_outcome: str | None = None
    reply_provider_message_id: str | None = None
    reply_rfc_message_id: str | None = None

    def to_evidence_dict(self) -> dict[str, str]:
        payload: dict[str, str] = {}
        if self.inbound_provider_message_id:
            payload["inbound_provider_message_id"] = self.inbound_provider_message_id
        if self.inbound_rfc_message_id:
            payload["inbound_rfc_message_id"] = self.inbound_rfc_message_id
        if self.reply_action_operation_id:
            payload["reply_action_operation_id"] = self.reply_action_operation_id
        if self.reply_execution_status:
            payload["reply_execution_status"] = self.reply_execution_status
        if self.reply_provider_outcome:
            payload["reply_provider_outcome"] = self.reply_provider_outcome
        if self.reply_provider_message_id:
            payload["reply_provider_message_id"] = self.reply_provider_message_id
        if self.reply_rfc_message_id:
            payload["reply_rfc_message_id"] = self.reply_rfc_message_id
        return payload


@dataclass
class JobActionExecutionSnapshot:
    action_type: str
    status: str
    error_message: str | None = None
    external_id: str | None = None


def assert_reply_evidence_invariants(evidence: ReplyExecutionEvidence) -> None:
    """Fail closed when inbound and reply provider IDs are conflated."""
    inbound = (evidence.inbound_provider_message_id or "").strip()
    reply = (evidence.reply_provider_message_id or "").strip()
    if inbound and reply and inbound == reply:
        raise LiveEvalSafetyError(
            "evidence invariant violated: inbound_provider_message_id equals reply_provider_message_id"
        )
    if (evidence.reply_execution_status or "") == "succeeded" and not reply:
        raise LiveEvalSafetyError(
            "evidence invariant violated: succeeded execution without reply_provider_message_id"
        )


def _operation_records(
    observation: dict[str, Any],
    *,
    action_operation_id: str | None,
) -> list[dict[str, Any]]:
    job = observation.get("job") or {}
    records = list(job.get("decision_records") or [])
    if not action_operation_id:
        return records
    return [
        row
        for row in records
        if str(row.get("action_operation_id") or "") in ("", action_operation_id)
    ]


def classify_reply_execution_status(
    observation: dict[str, Any],
    *,
    action_operation_id: str | None = None,
    job_actions: list[JobActionExecutionSnapshot] | None = None,
) -> str:
    """Return succeeded|skipped|failed|outcome_unknown|pending|not_observed."""
    if provider_execution_outcome_ready(observation):
        return "succeeded"

    for row in _operation_records(observation, action_operation_id=action_operation_id):
        if str(row.get("record_type") or "") != "execution_outcome":
            continue
        status = str(row.get("execution_status") or "").strip().lower()
        if status in TERMINAL_SUCCESS_STATUSES:
            return "succeeded"
        if status in TERMINAL_FAILURE_STATUSES:
            return "skipped" if status == "skipped" else "failed"
        if status in OUTCOME_UNKNOWN_STATUSES:
            return "outcome_unknown"

    if job_actions:
        reply_rows = [
            row
            for row in job_actions
            if row.action_type == "send_customer_auto_reply"
        ]
        if reply_rows:
            terminal = [row for row in reply_rows if row.status in {"executed", "succeeded", "failed", "skipped"}]
            if terminal:
                latest = terminal[-1]
                if latest.status in {"executed", "succeeded"}:
                    return "succeeded"
                if latest.status == "skipped":
                    return "skipped"
                return "failed"

    job = observation.get("job") or {}
    result = job.get("result") or {}
    if result.get("send_error"):
        return "failed"
    summary = str(result.get("summary") or "").lower()
    if "kunde inte skickas" in summary:
        return "failed"

    for row in _operation_records(observation, action_operation_id=action_operation_id):
        if str(row.get("record_type") or "") == "execution_intent":
            if str(row.get("execution_status") or "").lower() == "pending":
                return "pending"

    return "not_observed"


def build_reply_execution_evidence(
    *,
    observation: dict[str, Any],
    action_operation_id: str | None,
    inbound_provider_message_id: str | None,
    inbound_rfc_message_id: str | None,
    job_actions: list[JobActionExecutionSnapshot] | None = None,
) -> ReplyExecutionEvidence:
    status = classify_reply_execution_status(
        observation,
        action_operation_id=action_operation_id,
        job_actions=job_actions,
    )
    outcome = extract_provider_execution_outcome(observation)
    reply_provider_message_id: str | None = None
    reply_rfc_message_id: str | None = None
    provider_outcome: str | None = None

    if outcome is not None:
        reply_provider_message_id = outcome.provider_message_id
        reply_rfc_message_id = outcome.provider_rfc_message_id
        provider_outcome = outcome.adapter_status

    if job_actions and not reply_provider_message_id:
        for row in reversed(job_actions):
            if row.action_type != "send_customer_auto_reply":
                continue
            if row.external_id:
                reply_provider_message_id = row.external_id
                break

    if status == "succeeded" and not provider_outcome:
        provider_outcome = "executed"

    evidence = ReplyExecutionEvidence(
        inbound_provider_message_id=inbound_provider_message_id,
        inbound_rfc_message_id=inbound_rfc_message_id,
        reply_action_operation_id=action_operation_id,
        reply_execution_status=status,
        reply_provider_outcome=provider_outcome,
        reply_provider_message_id=reply_provider_message_id,
        reply_rfc_message_id=reply_rfc_message_id,
    )
    if status == "succeeded":
        assert_reply_evidence_invariants(evidence)
    elif inbound_provider_message_id and reply_provider_message_id:
        if inbound_provider_message_id == reply_provider_message_id:
            raise LiveEvalSafetyError(
                "evidence invariant violated: inbound_provider_message_id equals reply_provider_message_id"
            )
    return evidence


def poll_post_approval_reply_execution(
    fetch_observation: Callable[[], dict[str, Any]],
    fetch_job_actions: Callable[[], list[JobActionExecutionSnapshot]] | None,
    *,
    action_operation_id: str | None,
    inbound_provider_message_id: str | None,
    inbound_rfc_message_id: str | None,
    timeout_seconds: float = 120.0,
    poll_interval_seconds: float = 2.0,
) -> ReplyExecutionEvidence:
    deadline = time.monotonic() + timeout_seconds
    last_status = "pending"
    while time.monotonic() < deadline:
        observation = fetch_observation()
        job_actions = fetch_job_actions() if fetch_job_actions else None
        status = classify_reply_execution_status(
            observation,
            action_operation_id=action_operation_id,
            job_actions=job_actions,
        )
        last_status = status
        if status in TERMINAL_SUCCESS_STATUSES | TERMINAL_FAILURE_STATUSES | OUTCOME_UNKNOWN_STATUSES:
            return build_reply_execution_evidence(
                observation=observation,
                action_operation_id=action_operation_id,
                inbound_provider_message_id=inbound_provider_message_id,
                inbound_rfc_message_id=inbound_rfc_message_id,
                job_actions=job_actions,
            )
        if status == "not_observed" and job_actions:
            reply_failed = any(
                row.action_type == "send_customer_auto_reply" and row.status == "failed"
                for row in job_actions
            )
            reply_skipped = any(
                row.action_type == "send_customer_auto_reply" and row.status == "skipped"
                for row in job_actions
            )
            if reply_failed:
                return build_reply_execution_evidence(
                    observation=observation,
                    action_operation_id=action_operation_id,
                    inbound_provider_message_id=inbound_provider_message_id,
                    inbound_rfc_message_id=inbound_rfc_message_id,
                    job_actions=job_actions,
                )
            if reply_skipped:
                evidence = build_reply_execution_evidence(
                    observation=observation,
                    action_operation_id=action_operation_id,
                    inbound_provider_message_id=inbound_provider_message_id,
                    inbound_rfc_message_id=inbound_rfc_message_id,
                    job_actions=job_actions,
                )
                evidence.reply_execution_status = "skipped"
                return evidence
        time.sleep(poll_interval_seconds)

    observation = fetch_observation()
    job_actions = fetch_job_actions() if fetch_job_actions else None
    evidence = build_reply_execution_evidence(
        observation=observation,
        action_operation_id=action_operation_id,
        inbound_provider_message_id=inbound_provider_message_id,
        inbound_rfc_message_id=inbound_rfc_message_id,
        job_actions=job_actions,
    )
    if evidence.reply_execution_status in {"pending", "not_observed"}:
        evidence.reply_execution_status = last_status if last_status != "pending" else "outcome_unknown"
    return evidence


def provider_accepted(evidence: ReplyExecutionEvidence) -> bool:
    return (evidence.reply_execution_status or "") in TERMINAL_SUCCESS_STATUSES
