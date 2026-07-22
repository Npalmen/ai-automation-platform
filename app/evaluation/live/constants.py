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

REPORT_SCHEMA_VERSION = "2f.1"

PYTEST_MARKER_EXPR = (
    'not monday_live and not live_gmail_eval and not live_llm_eval and not live_e2e_eval'
)
