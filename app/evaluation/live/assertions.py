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
    "execution_intent",
    "execution_outcome",
    "action_approval_resolution",
    "dispatch_approval_resolution",
})

PIPELINE_PRE_APPROVAL_INTERLEAVED: frozenset[str] = frozenset({
    "action_authorization",
})

REQUIRED_DECISION_SUBSEQUENCE = (
    "pipeline_run_started",
    "classification",
    "decisioning_recommendation",
    "policy_authorization",
)

OBSERVE_DECISION_SUBSEQUENCE_NO_DECISIONING = (
    "pipeline_run_started",
    "classification",
    "policy_authorization",
)

ALLOWED_INTERLEAVED_DECISION_TYPES: frozenset[str] = frozenset()

SEMI_AUTO_POST_APPROVAL_INTERLEAVED: frozenset[str] = frozenset({
    "pipeline_run_started",
    "classification",
    "decisioning_recommendation",
    "policy_authorization",
    "action_authorization",
    "action_approval_resolution",
    "execution_intent",
    "execution_outcome",
})


def _assert_decision_subsequence(
    types: list[str],
    *,
    required: tuple[str, ...] = REQUIRED_DECISION_SUBSEQUENCE,
    interleaved: frozenset[str] | None = None,
) -> list[str]:
    violations: list[str] = []
    allowed_interleaved = interleaved or ALLOWED_INTERLEAVED_DECISION_TYPES
    cursor = 0
    for record_type in types:
        if cursor < len(required) and record_type == required[cursor]:
            cursor += 1
            continue
        if record_type in allowed_interleaved:
            continue
        if record_type in required:
            violations.append(f"decision record out of order: {record_type}")
            return violations
        violations.append(f"unknown decision record type: {record_type}")
        return violations
    if cursor != len(required):
        violations.append(f"decision record subsequence incomplete: {types}")
    return violations


def assert_observe_campaign_pipeline(
    observation: dict[str, Any],
    *,
    expected_job_type: str | None = None,
    expected_job_status: str = "awaiting_approval",
    expected_policy_authorization: str = "approval_required",
    expect_pending_approval: bool = True,
    decision_subsequence: tuple[str, ...] | None = None,
) -> list[str]:
    """Observe-mode campaign assertions: pipeline ran, no outbound, contract terminal state."""
    violations: list[str] = []
    job = observation.get("job") or {}
    if not job.get("job_id"):
        violations.append("expected job_id in observation")

    observed_status = job.get("job_status")
    if observed_status != expected_job_status:
        violations.append(
            f"expected job_status {expected_job_status!r}, got {observed_status!r}"
        )

    if expect_pending_approval:
        if not job.get("has_pending_approvals"):
            violations.append("expected pending approval")
    elif job.get("has_pending_approvals"):
        violations.append("unexpected pending approval")

    if expected_job_type:
        classification = job.get("classification") or {}
        detected = classification.get("detected_job_type")
        if detected != expected_job_type:
            violations.append(
                f"expected classification {expected_job_type!r}, got {detected!r}"
            )

    policy = job.get("policy") or {}
    observed_auth = policy.get("policy_authorization")
    if observed_auth != expected_policy_authorization:
        violations.append(
            f"expected policy_authorization {expected_policy_authorization!r}, "
            f"got {observed_auth!r}"
        )

    records = job.get("decision_records") or []
    types = [r.get("record_type") for r in sorted(records, key=lambda x: int(x.get("event_sequence") or 0))]
    violations.extend(
        _assert_decision_subsequence(
            types,
            required=decision_subsequence or REQUIRED_DECISION_SUBSEQUENCE,
            interleaved=PIPELINE_PRE_APPROVAL_INTERLEAVED,
        )
    )
    for forbidden in FORBIDDEN_DECISION_TYPES:
        if forbidden in types:
            violations.append(f"forbidden decision record {forbidden}")

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
    violations.extend(
        _assert_decision_subsequence(
            types,
            interleaved=PIPELINE_PRE_APPROVAL_INTERLEAVED,
        )
    )
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


def assert_semi_automatic_telemetry(
    testbot_events: list[dict[str, Any]],
    app_events: list[dict[str, Any]],
    *,
    expected_reply_count: int,
    app_summary: dict[str, int] | None = None,
) -> list[str]:
    """Semi-auto telemetry: allow bounded app Gmail replies to testbot sender."""
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
    if reply != expected_reply_count:
        violations.append(
            f"app_gmail_reply succeeded must be {expected_reply_count}, got {reply}"
        )

    llm = _count_unique_succeeded_operation_keys(app_events, TELEMETRY_APP_LIVE_LLM)
    if llm != 0:
        violations.append("app_live_llm succeeded must be 0")

    violations.extend(assert_no_forbidden_external_writes(app_events))

    if app_summary:
        summary_reply = app_summary.get(f"{TELEMETRY_APP_GMAIL_REPLY}:succeeded", 0)
        if summary_reply != expected_reply_count:
            violations.append(
                f"app_gmail_reply summary must be {expected_reply_count}, got {summary_reply}"
            )
        if app_summary.get(f"{TELEMETRY_APP_LIVE_LLM}:succeeded", 0) != 0:
            violations.append("app_live_llm summary must be 0")

    return violations


def assert_semi_automatic_campaign_pipeline(
    observation: dict[str, Any],
    *,
    expected_job_type: str | None,
    expected_job_status: str,
    expected_policy_authorization: str,
    expect_pending_approval: bool,
    decision_subsequence: tuple[str, ...] | None = None,
    expect_approval_resolution_record: bool = False,
) -> list[str]:
    """Semi-auto assertions: terminal state plus optional approval resolution record."""
    violations: list[str] = []
    job = observation.get("job") or {}
    if not job.get("job_id"):
        violations.append("expected job_id in observation")

    observed_status = job.get("job_status")
    if observed_status != expected_job_status:
        violations.append(
            f"expected job_status {expected_job_status!r}, got {observed_status!r}"
        )

    if expect_pending_approval:
        if not job.get("has_pending_approvals"):
            violations.append("expected pending approval")
    elif job.get("has_pending_approvals"):
        violations.append("unexpected pending approval")

    if expected_job_type:
        classification = job.get("classification") or {}
        detected = classification.get("detected_job_type")
        if detected != expected_job_type:
            violations.append(
                f"expected classification {expected_job_type!r}, got {detected!r}"
            )

    policy = job.get("policy") or {}
    observed_auth = policy.get("policy_authorization")
    if observed_auth != expected_policy_authorization:
        violations.append(
            f"expected policy_authorization {expected_policy_authorization!r}, "
            f"got {observed_auth!r}"
        )

    records = job.get("decision_records") or []
    types = [r.get("record_type") for r in sorted(records, key=lambda x: int(x.get("event_sequence") or 0))]
    violations.extend(
        _assert_decision_subsequence(
            types,
            required=decision_subsequence or REQUIRED_DECISION_SUBSEQUENCE,
            interleaved=(
                SEMI_AUTO_POST_APPROVAL_INTERLEAVED
                if expect_approval_resolution_record
                else None
            ),
        )
    )

    if expect_approval_resolution_record:
        if "action_approval_resolution" not in types:
            violations.append("expected action_approval_resolution decision record")
    for forbidden in FORBIDDEN_DECISION_TYPES:
        if forbidden in types:
            if expect_approval_resolution_record and forbidden in SEMI_AUTO_POST_APPROVAL_INTERLEAVED:
                continue
            violations.append(f"forbidden decision record {forbidden}")

    return violations


def assert_duplicate_approve_execution_chain(observation: dict[str, Any]) -> list[str]:
    """TBSM06: exactly one resolution/intent/outcome; duplicate approve must not add more."""
    violations: list[str] = []
    job = observation.get("job") or {}
    records = job.get("decision_records") or []

    def _count(record_type: str) -> int:
        return sum(1 for row in records if row.get("record_type") == record_type)

    for record_type in (
        "action_approval_resolution",
        "execution_intent",
        "execution_outcome",
    ):
        count = _count(record_type)
        if count != 1:
            violations.append(
                f"duplicate approve requires exactly one {record_type}, got {count}"
            )

    outcomes = [
        row
        for row in records
        if row.get("record_type") == "execution_outcome"
    ]
    if outcomes and outcomes[0].get("execution_status") != "succeeded":
        violations.append(
            f"execution_outcome must be succeeded, got {outcomes[0].get('execution_status')!r}"
        )

    return violations


def assert_expected_sender_reply(
    expected_reply: dict[str, Any] | None,
    *,
    required: bool,
) -> list[str]:
    if required and not expected_reply:
        return ["expected app reply in sender inbox not observed"]
    if not required and expected_reply:
        return ["unexpected app reply in sender inbox"]
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
