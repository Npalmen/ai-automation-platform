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

AUTOMATIC_AUTO_EXECUTE_INTERLEAVED: frozenset[str] = frozenset({
    "pipeline_run_started",
    "classification",
    "decisioning_recommendation",
    "policy_authorization",
    "action_authorization",
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


def _count_decision_records(observation: dict[str, Any], record_type: str) -> int:
    job = observation.get("job") or {}
    records = job.get("decision_records") or []
    return sum(1 for row in records if str(row.get("record_type") or "") == record_type)


def assert_post_reject_terminal_contract(
    observation: dict[str, Any],
    *,
    operator_decision_observed: str,
    expected_reply_count: int = 0,
) -> list[str]:
    """Accept manual_review post-reject only when reject terminal contract is fully proven."""
    violations: list[str] = []
    job = observation.get("job") or {}

    if operator_decision_observed != "reject":
        violations.append("post_reject_contract requires operator reject")
        return violations

    if str(job.get("job_status") or "") != "manual_review":
        violations.append("post_reject_contract requires job_status manual_review")

    pending = int(job.get("pending_approval_count") or 0)
    if pending != 0:
        violations.append(f"post_reject_contract requires pending_approval_count 0, got {pending}")

    if _count_decision_records(observation, "action_approval_resolution") != 1:
        violations.append("post_reject_contract requires exactly one action_approval_resolution")

    if _count_decision_records(observation, "execution_intent") != 0:
        violations.append("post_reject_contract requires zero execution_intent records")

    if _count_decision_records(observation, "execution_outcome") != 0:
        violations.append("post_reject_contract requires zero execution_outcome records")

    reply_events = sum(
        1
        for event in observation.get("events") or []
        if str(event.get("category") or "") == "app_gmail_reply"
        and str(event.get("outcome") or "") == "succeeded"
    )
    if reply_events != expected_reply_count:
        violations.append(
            f"post_reject_contract requires gmail reply events {expected_reply_count}, got {reply_events}"
        )

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


def _records_for_operation(
    records: list[dict[str, Any]],
    *,
    record_type: str,
    action_operation_id: str | None,
) -> list[dict[str, Any]]:
    if not action_operation_id:
        return [row for row in records if row.get("record_type") == record_type]
    return [
        row for row in records
        if row.get("record_type") == record_type
        and row.get("action_operation_id") == action_operation_id
    ]


def assert_target_scoped_execution_chain(
    observation: dict[str, Any],
    *,
    target_action_operation_id: str | None,
    expect_execution_outcome: bool,
) -> list[str]:
    """Assert resolution/intent/outcome records are scoped to the target operation."""
    violations: list[str] = []
    if not target_action_operation_id:
        violations.append("missing target_action_operation_id for scoped assertions")
        return violations

    job = observation.get("job") or {}
    records = job.get("decision_records") or []

    resolution_count = len(
        _records_for_operation(
            records,
            record_type="action_approval_resolution",
            action_operation_id=target_action_operation_id,
        )
    )
    if resolution_count != 1:
        violations.append(
            "target requires exactly one action_approval_resolution, "
            f"got {resolution_count}"
        )

    if expect_execution_outcome:
        intent_count = len(
            _records_for_operation(
                records,
                record_type="execution_intent",
                action_operation_id=target_action_operation_id,
            )
        )
        outcome_rows = _records_for_operation(
            records,
            record_type="execution_outcome",
            action_operation_id=target_action_operation_id,
        )
        if intent_count != 1:
            violations.append(
                f"target requires exactly one execution_intent, got {intent_count}"
            )
        if len(outcome_rows) != 1:
            violations.append(
                f"target requires exactly one execution_outcome, got {len(outcome_rows)}"
            )
        elif outcome_rows[0].get("execution_status") != "succeeded":
            violations.append(
                "target execution_outcome must be succeeded, got "
                f"{outcome_rows[0].get('execution_status')!r}"
            )
    else:
        for record_type in ("execution_intent", "execution_outcome"):
            count = len(
                _records_for_operation(
                    records,
                    record_type=record_type,
                    action_operation_id=target_action_operation_id,
                )
            )
            if count:
                violations.append(
                    f"target reject must not create {record_type}, got {count}"
                )

    return violations


def assert_automatic_campaign_pipeline(
    observation: dict[str, Any],
    *,
    expected_job_type: str | None,
    expected_job_status: str,
    expected_policy_authorization: str,
    expect_pending_approval: bool,
    decision_subsequence: tuple[str, ...] | None = None,
    expect_execution_intent: bool = False,
) -> list[str]:
    """Automatic canary assertions: terminal state without operator involvement."""
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
    types = [
        r.get("record_type")
        for r in sorted(records, key=lambda x: int(x.get("event_sequence") or 0))
    ]
    interleaved = (
        AUTOMATIC_AUTO_EXECUTE_INTERLEAVED if expect_execution_intent else None
    )
    violations.extend(
        _assert_decision_subsequence(
            types,
            required=decision_subsequence or REQUIRED_DECISION_SUBSEQUENCE,
            interleaved=interleaved,
        )
    )

    if "action_approval_resolution" in types:
        violations.append("automatic canary must not create action_approval_resolution")

    if expect_execution_intent:
        if types.count("execution_intent") != 1:
            violations.append(
                f"automatic canary requires exactly one execution_intent, "
                f"got {types.count('execution_intent')}"
            )
        if types.count("execution_outcome") != 1:
            violations.append(
                f"automatic canary requires exactly one execution_outcome, "
                f"got {types.count('execution_outcome')}"
            )
    else:
        for forbidden in ("execution_intent", "execution_outcome"):
            if forbidden in types:
                violations.append(
                    f"automatic hold scenario must not create {forbidden}"
                )

    return violations


def assert_automatic_execution_chain(
    observation: dict[str, Any],
    *,
    expect_execution_outcome: bool,
) -> list[str]:
    """Assert auto-execute path observed intent/outcome without approval resolution."""
    violations: list[str] = []
    records = (observation.get("job") or {}).get("decision_records") or []
    intent_rows = _records_for_operation(records, record_type="execution_intent", action_operation_id=None)
    outcome_rows = _records_for_operation(records, record_type="execution_outcome", action_operation_id=None)
    resolution_rows = _records_for_operation(
        records,
        record_type="action_approval_resolution",
        action_operation_id=None,
    )

    if resolution_rows:
        violations.append(
            f"automatic canary requires zero action_approval_resolution, got {len(resolution_rows)}"
        )

    if expect_execution_outcome:
        if len(intent_rows) != 1:
            violations.append(
                f"automatic canary requires exactly one execution_intent, got {len(intent_rows)}"
            )
        if len(outcome_rows) != 1:
            violations.append(
                f"automatic canary requires exactly one execution_outcome, got {len(outcome_rows)}"
            )
        elif outcome_rows[0].get("execution_status") != "succeeded":
            violations.append(
                "automatic execution_outcome must be succeeded, got "
                f"{outcome_rows[0].get('execution_status')!r}"
            )
    else:
        if intent_rows or outcome_rows:
            violations.append(
                "automatic hold scenario must not create execution intent/outcome"
            )

    return violations


def assert_duplicate_approve_execution_chain(
    observation: dict[str, Any],
    *,
    target_action_operation_id: str | None = None,
) -> list[str]:
    """TBSM06: exactly one target-scoped resolution/intent/outcome."""
    return assert_target_scoped_execution_chain(
        observation,
        target_action_operation_id=target_action_operation_id,
        expect_execution_outcome=True,
    )


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
