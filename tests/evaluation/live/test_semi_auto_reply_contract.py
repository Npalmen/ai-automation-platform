"""Regression tests for semi-auto reply contract (TBSM06 + 4-reply budget)."""

from __future__ import annotations

import pytest

from app.evaluation.live.assertions import assert_duplicate_approve_execution_chain
from app.evaluation.live.campaign.modes import CAMPAIGN_TYPE_REPLY_BUDGET
from app.evaluation.live.campaign.readiness import build_full_system_testbot_readiness
from app.evaluation.live.campaign.registry import clear_campaign_registry_cache, get_campaign_scenario
from app.evaluation.live.campaign.reply_contract import (
    build_semi_auto_reply_contract_matrix,
    validate_semi_auto_reply_contract,
)
from app.evaluation.live.campaign.reply_metrics import (
    CampaignReplyTotals,
    ScenarioReplyMetrics,
    build_scenario_reply_metrics,
)
from app.evaluation.live.campaign.semi_automatic_expected_outcomes import (
    resolve_semi_automatic_expected_outcome,
)
from app.evaluation.live.config import get_live_eval_config


@pytest.fixture(autouse=True)
def _clear_registry():
    clear_campaign_registry_cache()
    yield
    clear_campaign_registry_cache()


@pytest.fixture
def semi_auto_env(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_GMAIL_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", "TENANT_LIVE_EVAL")
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", "sender@eval.test")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", "recipient@eval.test")
    monkeypatch.setenv("LIVE_EVAL_MAX_SCENARIOS_PER_RUN", "8")
    monkeypatch.setenv("LIVE_EVAL_MAX_GMAIL_SENDS", "8")
    monkeypatch.setenv("LIVE_EVAL_MAX_GMAIL_REPLIES", "1")
    from app.core.settings import get_settings

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


def test_tbsm06_expected_reply_is_true():
    scenario = get_campaign_scenario("TBSM06_duplicate_approve")
    outcome = resolve_semi_automatic_expected_outcome(scenario)
    assert outcome.expected_reply is True
    assert outcome.expect_duplicate_idempotent is True
    assert scenario.budgets.gmail_replies == 1


def test_semi_auto_campaign_reply_budget_is_four():
    assert CAMPAIGN_TYPE_REPLY_BUDGET["semi-auto-core"] == 4


def test_semi_auto_expected_reply_total_is_four(semi_auto_env):
    matrix = build_semi_auto_reply_contract_matrix()
    assert matrix["scenario_expected_reply_total"] == 4
    assert matrix["scenario_budget_reply_total"] == 4
    assert matrix["workflow_reply_budget"] == 4


def test_readiness_contract_passes_with_four_replies(semi_auto_env):
    issues, matrix = validate_semi_auto_reply_contract()
    assert issues == []
    assert matrix["tbsm06_expected_reply"] is True
    assert matrix["tbsm06_budget_gmail_replies"] == 1


def test_readiness_stops_when_workflow_budget_is_three(semi_auto_env, monkeypatch):
    monkeypatch.setitem(CAMPAIGN_TYPE_REPLY_BUDGET, "semi-auto-core", 3)
    issues, _ = validate_semi_auto_reply_contract()
    assert any("workflow reply budget must be 4" in issue for issue in issues)
    assert any("does not match scenario expected_reply total" in issue for issue in issues)


def test_readiness_includes_contract_matrix(semi_auto_env):
    report = build_full_system_testbot_readiness(campaign_type="semi-auto-core")
    contract = report.gates.get("semi_auto_reply_contract") or {}
    assert contract.get("scenario_expected_reply_total") == 4
    assert report.ready is True


def test_zero_reply_scenarios_remain_zero(semi_auto_env):
    for scenario_id in (
        "TBSM04_lead_reject",
        "TBSM05_support_reject",
        "TBSM07_stale_approve",
        "TBSM08_unknown_negative_hold",
    ):
        scenario = get_campaign_scenario(scenario_id)
        outcome = resolve_semi_automatic_expected_outcome(scenario)
        assert outcome.expected_reply is False
        assert scenario.budgets.gmail_replies == 0


def test_build_scenario_reply_metrics_separates_physical_counts():
    observation = {
        "job": {
            "decision_records": [
                {"record_type": "execution_intent", "execution_status": "pending"},
                {
                    "record_type": "execution_outcome",
                    "execution_status": "succeeded",
                },
            ]
        },
        "events": [
            {
                "category": "app_gmail_reply",
                "outcome": "succeeded",
                "operation_key": "reply-1",
            }
        ],
    }
    metrics = build_scenario_reply_metrics(
        expected_reply=True,
        observation=observation,
        recipient_verified=True,
        unauthorized=False,
    )
    assert metrics.expected_reply_count == 1
    assert metrics.adapter_send_count == 1
    assert metrics.provider_accepted_count == 1
    assert metrics.recipient_verified_reply_count == 1
    assert metrics.unauthorized_reply_count == 0


def test_campaign_reply_totals_sum_physical_counts():
    totals = CampaignReplyTotals.from_scenarios(
        [
            ScenarioReplyMetrics(1, 1, 1, 1, 0, 0, 1, 0),
            ScenarioReplyMetrics(1, 1, 1, 1, 0, 0, 1, 0),
            ScenarioReplyMetrics(1, 1, 1, 1, 0, 0, 1, 0),
            ScenarioReplyMetrics(1, 1, 1, 1, 0, 0, 1, 0),
        ]
    )
    assert totals.expected_reply_count == 4
    assert totals.recipient_verified_reply_count == 4
    assert totals.unauthorized_reply_count == 0


def test_duplicate_approve_execution_chain_requires_single_records():
    observation = {
        "job": {
            "decision_records": [
                {"record_type": "action_approval_resolution", "action_operation_id": "op-target"},
                {"record_type": "execution_intent", "action_operation_id": "op-target"},
                {
                    "record_type": "execution_outcome",
                    "execution_status": "succeeded",
                    "action_operation_id": "op-target",
                },
            ]
        }
    }
    assert assert_duplicate_approve_execution_chain(
        observation,
        target_action_operation_id="op-target",
    ) == []


def test_duplicate_approve_execution_chain_fails_on_extra_outcome():
    observation = {
        "job": {
            "decision_records": [
                {"record_type": "action_approval_resolution", "action_operation_id": "op-target"},
                {"record_type": "execution_intent", "action_operation_id": "op-target"},
                {
                    "record_type": "execution_outcome",
                    "execution_status": "succeeded",
                    "action_operation_id": "op-target",
                },
                {
                    "record_type": "execution_outcome",
                    "execution_status": "succeeded",
                    "action_operation_id": "op-target",
                },
            ]
        }
    }
    violations = assert_duplicate_approve_execution_chain(
        observation,
        target_action_operation_id="op-target",
    )
    assert any("exactly one execution_outcome" in v for v in violations)
