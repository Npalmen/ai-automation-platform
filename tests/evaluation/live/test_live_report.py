"""Assertion and report schema tests for 2F.2."""

from __future__ import annotations

from app.evaluation.live.assertions import (
    REQUIRED_DECISION_SUBSEQUENCE,
    assert_s01_pipeline,
    assert_telemetry_summary,
)
from app.evaluation.live.constants import REPORT_SCHEMA_VERSION
from app.evaluation.live.schemas import LiveEvalReport


def test_report_schema_version():
    assert REPORT_SCHEMA_VERSION == "2f.2"
    report = LiveEvalReport(evaluation_run_id="run-1")
    assert report.report_schema_version == "2f.2"


def test_s01_pipeline_assertion_passes():
    observation = {
        "job": {
            "job_type": "lead",
            "job_status": "awaiting_approval",
            "has_pending_approvals": True,
            "classification": {"detected_job_type": "lead"},
            "policy": {
                "policy_authorization": "approval_required",
                "decision": "send_for_approval",
            },
            "decision_records": [
                {"record_type": rt, "event_sequence": i + 1}
                for i, rt in enumerate(REQUIRED_DECISION_SUBSEQUENCE)
            ],
        },
        "telemetry_summary": {
            "app_live_eval_delivery_observed:succeeded": 1,
            "app_live_eval_intake_succeeded:succeeded": 1,
        },
    }
    assert assert_s01_pipeline(observation) == []


def test_telemetry_summary_requires_zero_reply():
    testbot = [{"category": "testbot_gmail_send_succeeded"}]
    app_events = [
        {
            "category": "app_live_eval_delivery_observed",
            "outcome": "succeeded",
            "operation_key": "delivery-1",
        },
        {
            "category": "app_live_eval_intake_succeeded",
            "outcome": "succeeded",
            "operation_key": "intake-1",
        },
        {
            "category": "app_gmail_reply",
            "outcome": "succeeded",
            "operation_key": "reply-1",
        },
    ]
    violations = assert_telemetry_summary(testbot, app_events, {})
    assert any("app_gmail_reply" in v for v in violations)
