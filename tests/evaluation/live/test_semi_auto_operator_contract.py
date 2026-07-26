"""Regression tests for semi-auto operator plan contract and target selection."""

from __future__ import annotations

import pytest

from app.evaluation.live.campaign.operator_contract import (
    OperatorPlanStep,
    build_semi_auto_operator_contract_matrix,
    parse_semi_auto_operator_contract,
    validate_semi_auto_operator_contract,
)
from app.evaluation.live.campaign.registry import clear_campaign_registry_cache, get_campaign_scenario
from app.evaluation.live.campaign.semi_automatic_expected_outcomes import (
    resolve_semi_automatic_expected_outcome,
)
from app.evaluation.live.campaign.test_operator import (
    PendingApproval,
    assert_secondary_approvals,
    match_target_approval,
)
from app.evaluation.live.errors import LiveEvalSafetyError


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


def _pending(
    *,
    approval_id: str,
    action_type: str,
    operation_id: str,
    state: str = "pending",
) -> PendingApproval:
    return PendingApproval(
        approval_id=approval_id,
        state=state,
        next_on_approve="action_execute",
        action_type=action_type,
        delivery_type=action_type,
        action_operation_id=operation_id,
        recipient_redacted="te***@eval.test",
    )


def test_match_target_selects_customer_reply_not_handoff():
    pending = [
        _pending(approval_id="handoff", action_type="send_internal_handoff", operation_id="op-handoff"),
        _pending(approval_id="reply", action_type="send_customer_auto_reply", operation_id="op-reply"),
    ]
    step = OperatorPlanStep(action_type="send_customer_auto_reply", decision="approve")
    selected = match_target_approval(pending, step)
    assert selected.approval_id == "reply"
    assert selected.action_operation_id == "op-reply"


def test_match_target_order_independent():
    pending = [
        _pending(approval_id="reply", action_type="send_customer_auto_reply", operation_id="op-reply"),
        _pending(approval_id="handoff", action_type="send_internal_handoff", operation_id="op-handoff"),
    ]
    step = OperatorPlanStep(action_type="send_customer_auto_reply", decision="approve")
    selected = match_target_approval(list(reversed(pending)), step)
    assert selected.action_operation_id == "op-reply"


def test_match_target_not_found():
    pending = [
        _pending(approval_id="handoff", action_type="send_internal_handoff", operation_id="op-handoff"),
    ]
    step = OperatorPlanStep(action_type="send_customer_auto_reply", decision="approve")
    with pytest.raises(LiveEvalSafetyError, match="target_approval_not_found"):
        match_target_approval(pending, step)


def test_match_target_ambiguous():
    pending = [
        _pending(approval_id="a", action_type="send_customer_auto_reply", operation_id="op-1"),
        _pending(approval_id="b", action_type="send_customer_auto_reply", operation_id="op-2"),
    ]
    step = OperatorPlanStep(action_type="send_customer_auto_reply", decision="approve")
    with pytest.raises(LiveEvalSafetyError, match="ambiguous_target_approval"):
        match_target_approval(pending, step)


def test_duplicate_step_reuses_locked_operation_id():
    pending = [
        _pending(approval_id="reply", action_type="send_customer_auto_reply", operation_id="op-reply"),
        PendingApproval(
            approval_id="reply",
            state="approved",
            next_on_approve="action_execute",
            action_type="send_customer_auto_reply",
            delivery_type="send_customer_auto_reply",
            action_operation_id="op-reply",
            recipient_redacted="te***@eval.test",
        ),
    ]
    step = OperatorPlanStep(
        action_type="send_customer_auto_reply",
        decision="approve",
        expected_result="idempotent",
    )
    selected = match_target_approval(pending, step, locked_operation_id="op-reply")
    assert selected.approval_id == "reply"


def test_tbsm01_has_operator_plan_and_secondary():
    contract = parse_semi_auto_operator_contract(get_campaign_scenario("TBSM01_lead_approve_reply"))
    assert len(contract.operator_plan) == 1
    assert contract.operator_plan[0].action_type == "send_customer_auto_reply"
    assert contract.secondary_approvals[0].expected_final_state == "remain_pending"
    assert contract.uses_legacy_operator_action is False


def test_tbsm08_has_no_operator_plan():
    contract = parse_semi_auto_operator_contract(get_campaign_scenario("TBSM08_unknown_negative_hold"))
    assert contract.operator_plan == ()
    assert contract.secondary_approvals == ()


def test_readiness_operator_contract_passes(semi_auto_env):
    issues, warnings, matrix = validate_semi_auto_operator_contract()
    assert issues == []
    assert matrix["workflow_reply_budget"] == 4
    assert len(matrix["per_scenario"]) == 8
    assert all(not row["uses_legacy_operator_action"] for row in matrix["per_scenario"])


def test_secondary_remain_pending_assertions():
    outcome = resolve_semi_automatic_expected_outcome(get_campaign_scenario("TBSM01_lead_approve_reply"))
    approvals = [
        _pending(approval_id="reply", action_type="send_customer_auto_reply", operation_id="op-reply", state="approved"),
        _pending(approval_id="handoff", action_type="send_internal_handoff", operation_id="op-handoff"),
    ]
    violations = assert_secondary_approvals(
        approvals=approvals,
        outcome=outcome,
        touched_approval_ids={"reply"},
        decision_records=[
            {"record_type": "action_approval_resolution", "action_operation_id": "op-reply"},
            {"record_type": "execution_intent", "action_operation_id": "op-reply"},
            {"record_type": "execution_outcome", "action_operation_id": "op-reply"},
        ],
    )
    assert violations == []


def test_secondary_must_not_have_resolution_records():
    outcome = resolve_semi_automatic_expected_outcome(get_campaign_scenario("TBSM04_lead_reject"))
    approvals = [
        _pending(approval_id="reply", action_type="send_customer_auto_reply", operation_id="op-reply", state="rejected"),
        _pending(approval_id="handoff", action_type="send_internal_handoff", operation_id="op-handoff"),
    ]
    violations = assert_secondary_approvals(
        approvals=approvals,
        outcome=outcome,
        touched_approval_ids={"reply"},
        decision_records=[
            {"record_type": "action_approval_resolution", "action_operation_id": "op-handoff"},
        ],
    )
    assert any("secondary" in v and "action_approval_resolution" in v for v in violations)


def test_operator_matrix_lists_all_scenarios():
    matrix = build_semi_auto_operator_contract_matrix()
    ids = {row["scenario_id"] for row in matrix["per_scenario"]}
    assert ids == {
        "TBSM01_lead_approve_reply",
        "TBSM02_support_approve_reply",
        "TBSM03_noisy_approve_reply",
        "TBSM04_lead_reject",
        "TBSM05_support_reject",
        "TBSM06_duplicate_approve",
        "TBSM07_stale_approve",
        "TBSM08_unknown_negative_hold",
    }
