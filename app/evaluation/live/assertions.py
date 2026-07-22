"""S01 live-eval assertions (HTTP observation payloads)."""

from __future__ import annotations

from typing import Any

from app.evaluation.live.constants import (
    INTERNAL_LIVE_EVAL_TELEMETRY_CATEGORIES,
    TELEMETRY_APP_DELIVERY_OBSERVED,
    TELEMETRY_APP_GMAIL_REPLY,
    TELEMETRY_APP_INTAKE_SUCCEEDED,
    TELEMETRY_APP_LIVE_LLM,
    TELEMETRY_TESTBOT_SEND_SUCCEEDED,
)

FORBIDDEN_DECISION_TYPES = frozenset({
    "action_authorization",
    "execution_intent",
    "execution_outcome",
    "action_approval_resolution",
    "dispatch_approval_resolution",
})

REQUIRED_DECISION_SUBSEQUENCE = (
    "pipeline_run_started",
    "classification",
    "decisioning_recommendation",
    "policy_authorization",
)

ALLOWED_INTERLEAVED_DECISION_TYPES: frozenset[str] = frozenset()


def _assert_decision_subsequence(types: list[str]) -> list[str]:
    violations: list[str] = []
    cursor = 0
    for record_type in types:
        if record_type in ALLOWED_INTERLEAVED_DECISION_TYPES:
            continue
        if cursor < len(REQUIRED_DECISION_SUBSEQUENCE) and record_type == REQUIRED_DECISION_SUBSEQUENCE[cursor]:
            cursor += 1
            continue
        if record_type in REQUIRED_DECISION_SUBSEQUENCE:
            violations.append(f"decision record out of order: {record_type}")
            return violations
        violations.append(f"unknown decision record type: {record_type}")
        return violations
    if cursor != len(REQUIRED_DECISION_SUBSEQUENCE):
        violations.append(f"decision record subsequence incomplete: {types}")
    return violations


def assert_s01_pipeline(observation: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    job = observation.get("job") or {}
    if job.get("job_type") != "lead":
        violations.append(f"expected job_type lead, got {job.get('job_type')!r}")
    if job.get("job_status") != "awaiting_approval":
        violations.append(f"expected awaiting_approval, got {job.get('job_status')!r}")
    if not job.get("has_pending_approvals"):
        violations.append("expected pending approval")

    classification = job.get("classification") or {}
    if classification.get("detected_job_type") != "lead":
        violations.append("classification lead mismatch")

    policy = job.get("policy") or {}
    if policy.get("policy_authorization") != "approval_required":
        violations.append(
            f"expected policy_authorization approval_required, got {policy.get('policy_authorization')!r}"
        )
    if policy.get("decision") != "send_for_approval":
        violations.append(f"expected send_for_approval, got {policy.get('decision')!r}")

    records = job.get("decision_records") or []
    types = [r.get("record_type") for r in sorted(records, key=lambda x: int(x.get("event_sequence") or 0))]
    violations.extend(_assert_decision_subsequence(types))
    for forbidden in FORBIDDEN_DECISION_TYPES:
        if forbidden in types:
            violations.append(f"forbidden decision record {forbidden}")

    return violations


def _count_unique_succeeded_operation_keys(events: list[dict[str, Any]], category: str) -> int:
    keys = {
        e.get("operation_key")
        for e in events
        if e.get("category") == category and e.get("outcome") == "succeeded" and e.get("operation_key")
    }
    return len(keys)


def assert_no_forbidden_external_writes(events: list[dict[str, Any]]) -> list[str]:
    violations: list[str] = []
    for event in events:
        outcome = str(event.get("outcome") or "")
        if outcome != "succeeded":
            continue
        category = str(event.get("category") or "")
        if category in INTERNAL_LIVE_EVAL_TELEMETRY_CATEGORIES:
            continue
        if category.startswith("testbot_"):
            continue
        integration_type = str(event.get("integration_type") or "").strip()
        if integration_type:
            violations.append(
                f"forbidden external write succeeded: {integration_type}:{category}"
            )
            continue
        if category.endswith("_blocked"):
            continue
        violations.append(f"forbidden succeeded external event: {category}")
    return violations


def assert_telemetry_summary(
    testbot_events: list[dict[str, Any]],
    app_events: list[dict[str, Any]],
    app_summary: dict[str, int] | None = None,
) -> list[str]:
    violations: list[str] = []

    def count_testbot(category: str) -> int:
        return sum(1 for e in testbot_events if e.get("category") == category)

    if count_testbot(TELEMETRY_TESTBOT_SEND_SUCCEEDED) != 1:
        violations.append("testbot_gmail_send_succeeded must be 1")

    delivery = _count_unique_succeeded_operation_keys(app_events, TELEMETRY_APP_DELIVERY_OBSERVED)
    if delivery != 1:
        violations.append("app_live_eval_delivery_observed succeeded must be 1")

    intake = _count_unique_succeeded_operation_keys(app_events, TELEMETRY_APP_INTAKE_SUCCEEDED)
    if intake != 1:
        violations.append("app_live_eval_intake_succeeded must be 1")

    reply = _count_unique_succeeded_operation_keys(app_events, TELEMETRY_APP_GMAIL_REPLY)
    if reply != 0:
        violations.append("app_gmail_reply succeeded must be 0")

    llm = _count_unique_succeeded_operation_keys(app_events, TELEMETRY_APP_LIVE_LLM)
    if llm != 0:
        violations.append("app_live_llm succeeded must be 0")

    violations.extend(assert_no_forbidden_external_writes(app_events))

    if app_summary:
        if app_summary.get(f"{TELEMETRY_APP_GMAIL_REPLY}:succeeded", 0) != 0:
            violations.append("app_gmail_reply summary must be 0")
        if app_summary.get(f"{TELEMETRY_APP_LIVE_LLM}:succeeded", 0) != 0:
            violations.append("app_live_llm summary must be 0")

    return violations


def assert_no_unexpected_reply(unexpected_reply: dict[str, Any] | None) -> list[str]:
    if unexpected_reply:
        return ["unexpected_external_write: sender reply detected"]
    return []


def assert_safety_invariants(
    *,
    run: dict[str, Any],
    sender_message_id: str | None,
    recipient_message_id: str | None,
) -> list[str]:
    violations: list[str] = []
    if run.get("status") not in ("active", "completed"):
        violations.append(f"unexpected run status {run.get('status')!r}")
    if not sender_message_id:
        violations.append("missing sender_gmail_message_id")
    if not recipient_message_id:
        violations.append("missing recipient_gmail_message_id")
    if run.get("root_gmail_message_id") and recipient_message_id:
        if run["root_gmail_message_id"] != recipient_message_id:
            violations.append("recipient id does not match registry root")
    if run.get("ai_mode") != "fixture_ai":
        violations.append("fixture_ai required")
    return violations
