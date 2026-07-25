"""Regression tests for observe campaign contractual expected outcomes."""

from __future__ import annotations

from app.evaluation.live.assertions import assert_observe_campaign_pipeline
from app.evaluation.live.campaign.expected_outcomes import resolve_observe_expected_outcome
from app.evaluation.live.campaign.registry import clear_campaign_registry_cache, get_campaign_scenario
from app.evaluation.live.errors import LiveEvalPipelinePollError
from app.evaluation.live.pipeline_poll import poll_pipeline_observation
import pytest


@pytest.fixture(autouse=True)
def _clear_registry():
    clear_campaign_registry_cache()
    yield
    clear_campaign_registry_cache()


def _observation(*, status: str, policy_auth: str, pending: bool, job_type: str) -> dict:
    return {
        "run": {"tenant_id": "TENANT_LIVE_EVAL", "root_job_id": "job-1"},
        "job": {
            "job_id": "job-1",
            "job_status": status,
            "has_pending_approvals": pending,
            "policy": {"policy_authorization": policy_auth, "decision": policy_auth},
            "classification": {"detected_job_type": job_type},
            "decision_records": [
                {"record_type": "pipeline_run_started", "event_sequence": 1},
                {"record_type": "classification", "event_sequence": 2},
                {"record_type": "decisioning_recommendation", "event_sequence": 3},
                {"record_type": "policy_authorization", "event_sequence": 4},
            ],
        },
        "events": [],
    }


def test_tbs04_unknown_expects_safe_manual_review_hold():
    scenario = get_campaign_scenario("TBS04_unknown_observe")
    outcome = resolve_observe_expected_outcome(scenario)
    assert outcome.job_status == "manual_review"
    assert outcome.policy_authorization == "hold_for_review"
    assert outcome.expect_pending_approval is False
    assert "manual_review" in outcome.success_terminal_statuses


def test_tbs03_invoice_expects_manual_review_without_approval():
    scenario = get_campaign_scenario("TBS03_invoice_observe")
    outcome = resolve_observe_expected_outcome(scenario)
    assert outcome.job_status == "manual_review"
    assert outcome.expect_pending_approval is False


def test_manual_review_assertion_passes_without_approval():
    scenario = get_campaign_scenario("TBS04_unknown_observe")
    outcome = resolve_observe_expected_outcome(scenario)
    observation = _observation(
        status=outcome.job_status,
        policy_auth=outcome.policy_authorization,
        pending=False,
        job_type="unknown",
    )
    violations = assert_observe_campaign_pipeline(
        observation,
        expected_job_type="unknown",
        expected_job_status=outcome.job_status,
        expected_policy_authorization=outcome.policy_authorization,
        expect_pending_approval=False,
    )
    assert violations == []


def test_manual_review_poll_succeeds_when_expected():
    scenario = get_campaign_scenario("TBS04_unknown_observe")
    outcome = resolve_observe_expected_outcome(scenario)
    result = poll_pipeline_observation(
        lambda: _observation(
            status="manual_review",
            policy_auth="hold_for_review",
            pending=False,
            job_type="unknown",
        ),
        timeout_seconds=5,
        success_statuses=outcome.success_terminal_statuses,
    )
    assert result.observation["job"]["job_status"] == "manual_review"


def test_unexpected_approval_on_safe_hold_fails():
    observation = _observation(
        status="manual_review",
        policy_auth="hold_for_review",
        pending=True,
        job_type="unknown",
    )
    violations = assert_observe_campaign_pipeline(
        observation,
        expected_job_type="unknown",
        expected_job_status="manual_review",
        expected_policy_authorization="hold_for_review",
        expect_pending_approval=False,
    )
    assert any("unexpected pending approval" in v for v in violations)


def test_default_s01_poll_still_fails_on_manual_review():
    with pytest.raises(LiveEvalPipelinePollError) as exc_info:
        poll_pipeline_observation(
            lambda: _observation(
                status="manual_review",
                policy_auth="hold_for_review",
                pending=False,
                job_type="unknown",
            ),
            timeout_seconds=5,
        )
    assert exc_info.value.timeout_reason == "unexpected_terminal_status"
