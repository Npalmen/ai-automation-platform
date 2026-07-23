"""Constants for live evaluation."""

from __future__ import annotations

SUBJECT_TOKEN_PREFIX = "KROWOLF-EVAL"

RUN_STATUS_REGISTERED = "registered"
RUN_STATUS_ACTIVE = "active"
RUN_STATUS_COMPLETED = "completed"
RUN_STATUS_ABORTED = "aborted"
RUN_STATUS_EXPIRED = "expired"

TERMINAL_RUN_STATUSES = frozenset(
    {RUN_STATUS_COMPLETED, RUN_STATUS_ABORTED, RUN_STATUS_EXPIRED}
)

ALLOWED_RUN_TRANSITIONS: dict[str, frozenset[str]] = {
    RUN_STATUS_REGISTERED: frozenset(
        {RUN_STATUS_ACTIVE, RUN_STATUS_ABORTED, RUN_STATUS_EXPIRED}
    ),
    RUN_STATUS_ACTIVE: frozenset(
        {RUN_STATUS_COMPLETED, RUN_STATUS_ABORTED, RUN_STATUS_EXPIRED}
    ),
}

ALLOWED_TRANSPORT_MODES = frozenset({"live_gmail"})
ALLOWED_AI_MODES = frozenset({"fixture_ai", "live_llm"})

EVENT_OUTCOME_BLOCKED = "blocked"
EVENT_OUTCOME_FAILED = "failed"
EVENT_OUTCOME_SUCCEEDED = "succeeded"

REPORT_SCHEMA_VERSION = "2f.2"

ALLOWED_2F2_SCENARIOS = frozenset({"S01_lead_laddbox_quality"})

SENDER_EVAL_LABEL = "krowolf-live-eval-sent"

# Logical telemetry categories (app + testbot journal)
TELEMETRY_TESTBOT_SEND_ATTEMPT = "testbot_gmail_send_attempt"
TELEMETRY_TESTBOT_SEND_SUCCEEDED = "testbot_gmail_send_succeeded"
TELEMETRY_TESTBOT_SEND_RECONCILE = "testbot_gmail_send_reconcile_read"
TELEMETRY_APP_DELIVERY_OBSERVED = "app_live_eval_delivery_observed"
TELEMETRY_APP_INTAKE_STARTED = "app_live_eval_intake_started"
TELEMETRY_APP_INTAKE_SUCCEEDED = "app_live_eval_intake_succeeded"
TELEMETRY_APP_INTAKE_FAILED = "app_live_eval_intake_failed"
TELEMETRY_APP_GMAIL_REPLY = "app_gmail_reply"
TELEMETRY_APP_LIVE_LLM = "app_live_llm"
TELEMETRY_APP_EXTERNAL_BLOCKED = "app_external_write_blocked"
TELEMETRY_APP_CLEANUP_ARCHIVED = "app_live_eval_cleanup_archived"

LIVE_EVAL_MUTATION_CLEANUP_ARCHIVE = "cleanup_archive"

# Authoritative cleanup lifecycle states for live-eval reporting.
CLEANUP_STATE_NOT_STARTED = "not_started"
CLEANUP_STATE_DEFERRED = "deferred"
CLEANUP_STATE_IN_PROGRESS = "in_progress"
CLEANUP_STATE_SUCCESS = "success"
CLEANUP_STATE_ALREADY_ARCHIVED = "already_archived"
CLEANUP_STATE_BLOCKED = "blocked"
CLEANUP_STATE_FAILED = "failed"
TERMINAL_CLEANUP_STATES = frozenset(
    {CLEANUP_STATE_SUCCESS, CLEANUP_STATE_ALREADY_ARCHIVED}
)

ALLOWED_INTERLEAVED_DECISION_TYPES: frozenset[str] = frozenset()

# Delivery time window skew (seconds)
DELIVERY_CLOCK_SKEW_SECONDS = 60
DELIVERY_FUTURE_SKEW_SECONDS = 30

# Internal live-eval telemetry categories (not external writes)
INTERNAL_LIVE_EVAL_TELEMETRY_CATEGORIES = frozenset({
    TELEMETRY_APP_DELIVERY_OBSERVED,
    TELEMETRY_APP_INTAKE_STARTED,
    TELEMETRY_APP_INTAKE_SUCCEEDED,
    TELEMETRY_APP_INTAKE_FAILED,
    TELEMETRY_APP_EXTERNAL_BLOCKED,
    TELEMETRY_APP_CLEANUP_ARCHIVED,
    "testbot_gmail_send_attempt",
    TELEMETRY_TESTBOT_SEND_SUCCEEDED,
    TELEMETRY_TESTBOT_SEND_RECONCILE,
    "testbot_unexpected_sender_reply_detected",
})

PYTEST_MARKER_EXPR = (
    "not monday_live and not live_gmail_eval and not live_llm_eval and not live_e2e_eval"
)
