"""Regression tests for semi-automatic campaign contractual expected outcomes."""

from __future__ import annotations

import pytest

from app.evaluation.live.assertions import (
    REQUIRED_DECISION_SUBSEQUENCE,
    assert_post_reject_terminal_contract,
    assert_semi_automatic_campaign_pipeline,
    assert_semi_automatic_telemetry,
    assert_target_scoped_execution_chain,
)
from app.evaluation.live.campaign.registry import clear_campaign_registry_cache, get_campaign_scenario
from app.evaluation.live.campaign.semi_automatic_expected_outcomes import (
    resolve_semi_automatic_expected_outcome,
    validate_post_operator_final_job_status_contract,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    clear_campaign_registry_cache()
    yield
    clear_campaign_registry_cache()


def test_tbsm01_lead_approve_reply_expectations():
    scenario = get_campaign_scenario("TBSM01_lead_approve_reply")
    outcome = resolve_semi_automatic_expected_outcome(scenario)
    assert outcome.operator_action == "approve"
    assert outcome.expected_reply is True
    assert outcome.final_job_status == "awaiting_approval"
    assert outcome.post_operator_final_job_status == "completed"
    assert outcome.final_success_statuses == frozenset({"awaiting_approval"})
    assert outcome.expect_approval_resolution is True
    assert outcome.decision_subsequence == REQUIRED_DECISION_SUBSEQUENCE
    assert outcome.operator_plan[0].action_type == "send_customer_auto_reply"
    assert validate_post_operator_final_job_status_contract(scenario, outcome) == []


def test_tbsm04_lead_reject_expectations():
    scenario = get_campaign_scenario("TBSM04_lead_reject")
    outcome = resolve_semi_automatic_expected_outcome(scenario)
    assert outcome.operator_action == "reject"
    assert outcome.expected_reply is False
    assert outcome.final_job_status == "awaiting_approval"
    assert outcome.post_operator_final_job_status == "manual_review"
    assert outcome.is_post_reject_terminal is True
    assert validate_post_operator_final_job_status_contract(scenario, outcome) == []


@pytest.mark.parametrize(
    "scenario_id",
    ["TBSM05_support_reject", "TBSM07_stale_approve"],
)
def test_reject_scenarios_post_operator_manual_review(scenario_id: str):
    scenario = get_campaign_scenario(scenario_id)
    outcome = resolve_semi_automatic_expected_outcome(scenario)
    assert outcome.post_operator_final_job_status == "manual_review"
    assert validate_post_operator_final_job_status_contract(scenario, outcome) == []


def test_post_reject_manual_review_passes_contract():
    observation = {
        "job": {
            "job_id": "job-1",
            "job_status": "manual_review",
            "pending_approval_count": 0,
            "decision_records": [
                {"record_type": "action_approval_resolution"},
            ],
        },
        "events": [],
    }
    assert assert_post_reject_terminal_contract(
        observation,
        operator_decision_observed="reject",
        expected_reply_count=0,
    ) == []


def test_post_reject_requires_zero_intents_and_outcomes():
    observation = {
        "job": {
            "job_status": "manual_review",
            "pending_approval_count": 0,
            "decision_records": [
                {"record_type": "action_approval_resolution"},
                {"record_type": "execution_intent"},
            ],
        },
        "events": [],
    }
    violations = assert_post_reject_terminal_contract(
        observation,
        operator_decision_observed="reject",
    )
    assert any("execution_intent" in v for v in violations)


def test_tbsm06_duplicate_approve_variant():
    scenario = get_campaign_scenario("TBSM06_duplicate_approve")
    outcome = resolve_semi_automatic_expected_outcome(scenario)
    assert outcome.test_variant == "duplicate_approve"
    assert outcome.expect_duplicate_idempotent is True
    assert outcome.expected_reply is True
    assert scenario.budgets.gmail_replies == 1


def test_tbsm07_stale_action_variant():
    scenario = get_campaign_scenario("TBSM07_stale_approve")
    outcome = resolve_semi_automatic_expected_outcome(scenario)
    assert outcome.test_variant == "stale_action"
    assert outcome.expect_stale_conflict is True


def test_tbsm08_unknown_negative_hold_blocks_operator():
    scenario = get_campaign_scenario("TBSM08_unknown_negative_hold")
    outcome = resolve_semi_automatic_expected_outcome(scenario)
    assert outcome.is_negative_hold is True
    assert outcome.allow_operator_action is False
    assert outcome.final_job_status == "manual_review"


def test_semi_auto_core_has_eight_scenarios():
    from app.evaluation.live.campaign.registry import list_campaign_scenarios

    scenarios = list_campaign_scenarios(campaign_type="semi-auto-core")
    assert len(scenarios) == 8
    assert all(s.mode == "semi_automatic" for s in scenarios)


def test_tbsm_scenarios_have_fixture_bundles():
    from app.evaluation.live.fixture_bundle import resolve_fixture_bundle_id

    for scenario_id in (
        "TBSM01_lead_approve_reply",
        "TBSM02_support_approve_reply",
        "TBSM03_noisy_approve_reply",
        "TBSM04_lead_reject",
        "TBSM05_support_reject",
        "TBSM06_duplicate_approve",
        "TBSM07_stale_approve",
        "TBSM08_unknown_negative_hold",
    ):
        bundle_id = resolve_fixture_bundle_id(scenario_id=scenario_id, ai_mode="fixture_ai")
        assert bundle_id is not None


def test_approve_reply_telemetry_allows_one_reply():
    violations = assert_semi_automatic_telemetry(
        [{"category": "testbot_gmail_send_succeeded"}],
        [
            {"category": "app_live_eval_delivery_observed", "outcome": "succeeded", "operation_key": "d1"},
            {"category": "app_live_eval_intake_succeeded", "outcome": "succeeded", "operation_key": "i1"},
            {"category": "app_gmail_reply", "outcome": "succeeded", "operation_key": "r1"},
        ],
        expected_reply_count=1,
    )
    assert violations == []


def test_reject_telemetry_requires_zero_replies():
    violations = assert_semi_automatic_telemetry(
        [{"category": "testbot_gmail_send_succeeded"}],
        [
            {"category": "app_live_eval_delivery_observed", "outcome": "succeeded", "operation_key": "d1"},
            {"category": "app_live_eval_intake_succeeded", "outcome": "succeeded", "operation_key": "i1"},
        ],
        expected_reply_count=0,
    )
    assert violations == []


def test_semi_auto_pipeline_allows_post_approval_interleaved_records():
    observation = {
        "job": {
            "job_id": "job-1",
            "job_status": "awaiting_approval",
            "has_pending_approvals": True,
            "classification": {"detected_job_type": "lead"},
            "policy": {"policy_authorization": "approval_required"},
            "decision_records": [
                {"record_type": "pipeline_run_started", "event_sequence": 1},
                {"record_type": "classification", "event_sequence": 2},
                {"record_type": "decisioning_recommendation", "event_sequence": 3},
                {"record_type": "policy_authorization", "event_sequence": 4},
                {"record_type": "pipeline_run_started", "event_sequence": 5},
                {"record_type": "action_authorization", "event_sequence": 6},
                {
                    "record_type": "action_approval_resolution",
                    "event_sequence": 7,
                    "action_operation_id": "op-target",
                },
                {
                    "record_type": "execution_intent",
                    "event_sequence": 8,
                    "action_operation_id": "op-target",
                },
                {
                    "record_type": "execution_outcome",
                    "event_sequence": 9,
                    "action_operation_id": "op-target",
                    "execution_status": "succeeded",
                },
            ],
        },
        "events": [],
    }
    violations = assert_semi_automatic_campaign_pipeline(
        observation,
        expected_job_type="lead",
        expected_job_status="awaiting_approval",
        expected_policy_authorization="approval_required",
        expect_pending_approval=True,
        expect_approval_resolution_record=True,
    )
    assert violations == []
    assert assert_target_scoped_execution_chain(
        observation,
        target_action_operation_id="op-target",
        expect_execution_outcome=True,
    ) == []


def test_semi_auto_pipeline_requires_resolution_record_on_approve():
    observation = {
        "job": {
            "job_id": "job-1",
            "job_status": "completed",
            "has_pending_approvals": False,
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
    violations = assert_semi_automatic_campaign_pipeline(
        observation,
        expected_job_type="lead",
        expected_job_status="completed",
        expected_policy_authorization="approval_required",
        expect_pending_approval=False,
        expect_approval_resolution_record=True,
    )
    assert any("action_approval_resolution" in v for v in violations)
