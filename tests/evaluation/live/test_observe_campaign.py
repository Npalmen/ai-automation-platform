"""Tests for observe campaign assertions and fixture bundles."""

from __future__ import annotations

from app.evaluation.live.assertions import assert_observe_campaign_pipeline
from app.evaluation.live.fixture_bundle import resolve_fixture_bundle_id


def test_tbs_scenarios_have_fixture_bundles():
    for scenario_id in (
        "TBS01_lead_observe",
        "TBS02_support_observe",
        "TBS03_invoice_observe",
        "TBS04_unknown_observe",
        "TBS05_noisy_observe",
    ):
        bundle_id = resolve_fixture_bundle_id(scenario_id=scenario_id, ai_mode="fixture_ai")
        assert bundle_id is not None


def test_observe_assertion_passes_awaiting_approval():
    observation = {
        "job": {
            "job_id": "job-001",
            "job_status": "awaiting_approval",
            "has_pending_approvals": True,
            "classification": {"detected_job_type": "lead"},
            "policy": {"policy_authorization": "approval_required"},
            "decision_records": [
                {"record_type": "pipeline_run_started", "event_sequence": 1},
                {"record_type": "classification", "event_sequence": 2},
                {"record_type": "decisioning_recommendation", "event_sequence": 3},
                {"record_type": "policy_authorization", "event_sequence": 4},
            ],
        },
        "events": [],
    }
    assert assert_observe_campaign_pipeline(observation, expected_job_type="lead") == []


def test_observe_assertion_fails_wrong_classification():
    observation = {
        "job": {
            "job_id": "job-001",
            "job_status": "awaiting_approval",
            "has_pending_approvals": True,
            "classification": {"detected_job_type": "invoice"},
            "policy": {"policy_authorization": "approval_required"},
            "decision_records": [],
        },
        "events": [],
    }
    violations = assert_observe_campaign_pipeline(observation, expected_job_type="lead")
    assert any("expected classification" in v for v in violations)
