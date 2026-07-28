"""Automatic campaign pipeline assertion tests."""

from __future__ import annotations

from app.evaluation.live.assertions import (
    assert_automatic_campaign_pipeline,
    assert_automatic_execution_chain,
)


def _auto_execute_observation() -> dict:
    return {
        "job": {
            "job_id": "job-auto-1",
            "job_status": "completed",
            "has_pending_approvals": False,
            "classification": {"detected_job_type": "lead"},
            "policy": {"policy_authorization": "execution_allowed"},
            "decision_records": [
                {"record_type": "pipeline_run_started", "event_sequence": 1},
                {"record_type": "classification", "event_sequence": 2},
                {"record_type": "decisioning_recommendation", "event_sequence": 3},
                {"record_type": "policy_authorization", "event_sequence": 4},
                {"record_type": "action_authorization", "event_sequence": 5},
                {"record_type": "execution_intent", "event_sequence": 6},
                {"record_type": "execution_outcome", "event_sequence": 7, "execution_status": "succeeded"},
            ],
        },
        "events": [],
    }


def test_automatic_pipeline_passes_without_approval():
    observation = _auto_execute_observation()
    assert assert_automatic_campaign_pipeline(
        observation,
        expected_job_type="lead",
        expected_job_status="completed",
        expected_policy_authorization="execution_allowed",
        expect_pending_approval=False,
        expect_execution_intent=True,
    ) == []
    assert assert_automatic_execution_chain(
        observation,
        expect_execution_outcome=True,
    ) == []


def test_automatic_hold_rejects_execution_records():
    observation = {
        "job": {
            "job_id": "job-hold-1",
            "job_status": "manual_review",
            "has_pending_approvals": False,
            "classification": {"detected_job_type": "unknown"},
            "policy": {"policy_authorization": "hold_for_review"},
            "decision_records": [
                {"record_type": "pipeline_run_started", "event_sequence": 1},
                {"record_type": "classification", "event_sequence": 2},
                {"record_type": "policy_authorization", "event_sequence": 3},
            ],
        },
        "events": [],
    }
    assert assert_automatic_execution_chain(
        observation,
        expect_execution_outcome=False,
    ) == []
