"""Regression tests for semi-auto live stabilization (run 30219704813)."""

from __future__ import annotations

import pytest

from app.evaluation.live.assertions import assert_target_scoped_execution_chain
from app.evaluation.live.campaign.generator import build_campaign_message_body
from app.evaluation.live.campaign.operator_contract import (
    build_semi_auto_operator_contract_matrix,
    validate_semi_auto_operator_contract,
)
from app.evaluation.live.campaign.registry import clear_campaign_registry_cache, get_campaign_scenario
from app.evaluation.live.campaign.reply_metrics import build_scenario_reply_metrics
from app.evaluation.live.campaign.semi_automatic_expected_outcomes import (
    resolve_semi_automatic_expected_outcome,
)
from app.evaluation.live.campaign.tenant_materialization import (
    resolve_expected_actions_for_semi_auto,
    resolve_live_eval_tenant_context,
)


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
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


def test_live_eval_tenant_handoff_not_materialized():
    ctx = resolve_live_eval_tenant_context()
    actions = resolve_expected_actions_for_semi_auto(
        target_action_type="send_customer_auto_reply",
        context=ctx,
    )
    handoff = next(a for a in actions if a.action_type == "send_internal_handoff")
    assert handoff.materialization == "not_materialized"
    assert handoff.reason == "tenant_internal_notification_disabled"


def test_tenant_with_internal_notification_expects_remain_pending():
    ctx = resolve_live_eval_tenant_context(
        tenant_settings={"branding": {"internal_notification_email": "ops@example.com"}},
    )
    actions = resolve_expected_actions_for_semi_auto(
        target_action_type="send_customer_auto_reply",
        context=ctx,
    )
    handoff = next(a for a in actions if a.action_type == "send_internal_handoff")
    assert handoff.materialization == "remain_pending"


def test_readiness_blocks_remain_pending_without_internal_email(semi_auto_env):
    issues, _, _ = validate_semi_auto_operator_contract()
    assert not any("remain_pending conflicts" in issue for issue in issues)


def test_tbsm08_negative_control_skips_target_scoped_assertions():
    outcome = resolve_semi_automatic_expected_outcome(
        get_campaign_scenario("TBSM08_unknown_negative_hold")
    )
    assert outcome.is_negative_hold
    violations = assert_target_scoped_execution_chain(
        {"job": {"decision_records": []}},
        target_action_operation_id=None,
        expect_execution_outcome=False,
    )
    assert "missing target_action_operation_id" in violations[0]


def test_campaign_run_marker_in_body():
    scenario = get_campaign_scenario("TBSM01_lead_approve_reply")
    body = build_campaign_message_body(
        scenario=scenario,
        evaluation_run_id="run-abc",
        campaign_run_id="campaign-xyz",
    )
    assert "KROWOLF_CAMPAIGN_RUN:campaign-xyz" in body
    assert "KROWOLF_EVAL:evaluation_run_id=run-abc" in body


def test_reply_metrics_independent_counters():
    metrics = build_scenario_reply_metrics(
        expected_reply=True,
        observation={
            "events": [],
            "job": {
                "decision_records": [
                    {"record_type": "execution_intent"},
                    {"record_type": "execution_outcome", "execution_status": "succeeded"},
                ]
            },
        },
        recipient_verified=False,
        unauthorized=False,
    )
    assert metrics.execution_intent_count == 1
    assert metrics.adapter_invocation_count == 1
    assert metrics.provider_accepted_count == 1
    assert metrics.recipient_verified_reply_count == 0
    assert metrics.provider_outcome_unknown_count == 0


def test_matrix_expected_materialized_count_is_one_for_approve_scenarios(semi_auto_env):
    matrix = build_semi_auto_operator_contract_matrix()
    tbsm01 = next(
        row for row in matrix["per_scenario"] if row["scenario_id"] == "TBSM01_lead_approve_reply"
    )
    assert tbsm01["expected_materialized_approvals"] == 1
