"""Fail-closed read-only guard for live Gmail forensics."""

from __future__ import annotations

import os

from app.evaluation.live.config import LiveEvalConfig, get_live_eval_config
from app.evaluation.live.errors import LiveEvalSafetyError


def assert_readonly_forensics_budget(config: LiveEvalConfig | None = None) -> LiveEvalConfig:
    config = config or get_live_eval_config()
    if config.max_gmail_sends_per_run != 0:
        raise LiveEvalSafetyError(
            "forensics requires LIVE_EVAL_MAX_GMAIL_SENDS=0"
        )
    if config.max_gmail_replies_per_run != 0:
        raise LiveEvalSafetyError(
            "forensics requires LIVE_EVAL_MAX_GMAIL_REPLIES=0"
        )
    if os.environ.get("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED", "").strip().lower() in (
        "yes",
        "true",
        "1",
    ):
        raise LiveEvalSafetyError(
            "forensics must not run with FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED=yes"
        )
    return config


def install_readonly_gmail_guard() -> None:
    """Block Gmail mutation methods for the duration of a forensics run."""
    from app.integrations.google import mail_client

    blocked_methods = (
        "send_message",
        "archive_from_inbox",
        "create_label",
        "modify_message_labels",
        "trash_message",
        "delete_message",
    )

    original = mail_client.GoogleMailClient

    class _ReadOnlyGoogleMailClient(original):  # type: ignore[misc,valid-type]
        def __getattribute__(self, name: str):
            if name in blocked_methods:
                raise LiveEvalSafetyError(
                    f"forensics blocked Gmail write operation: {name}"
                )
            return super().__getattribute__(name)

    mail_client.GoogleMailClient = _ReadOnlyGoogleMailClient  # type: ignore[misc]
