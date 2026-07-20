"""Tests for centralized action authorization."""

from __future__ import annotations

from app.workflows.action_authorization import (
    ActionAuthorization,
    authorize_action,
    classify_action,
)


def test_unknown_action_blocked():
    assert classify_action("totally_unknown") is None
    assert (
        authorize_action(
            "totally_unknown",
            job_type="lead",
            auto_actions={},
            risk_detected=False,
            policy_decision="auto_execute",
        )
        == ActionAuthorization.BLOCKED
    )


def test_injected_external_write_requires_approval_when_manual():
    assert (
        authorize_action(
            "create_monday_item",
            job_type="lead",
            auto_actions={"lead": "manual"},
            risk_detected=False,
            policy_decision="auto_execute",
        )
        == ActionAuthorization.APPROVAL_REQUIRED
    )


def test_notify_slack_classified_external_write():
    spec = classify_action("notify_slack")
    assert spec is not None
    assert spec.effect.value == "external_write"


def test_pre_authorized_bypasses_manual_mode():
    assert (
        authorize_action(
            "send_customer_auto_reply",
            job_type="lead",
            auto_actions={},
            risk_detected=False,
            policy_decision="auto_execute",
            pre_authorized=True,
        )
        == ActionAuthorization.EXECUTION_ALLOWED
    )
