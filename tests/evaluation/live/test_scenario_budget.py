"""Selected-scenario budget and canary subset regression tests."""

from __future__ import annotations

import pytest

from app.evaluation.live.campaign.modes import CAMPAIGN_TYPE_REPLY_BUDGET
from app.evaluation.live.campaign.readiness import build_full_system_testbot_readiness
from app.evaluation.live.campaign.registry import clear_campaign_registry_cache
from app.evaluation.live.campaign.reply_contract import (
    build_semi_auto_reply_contract_matrix,
    validate_semi_auto_reply_contract,
)
from app.evaluation.live.campaign.runner import run_semi_automatic_campaign
from app.evaluation.live.campaign.scenario_budget import build_selected_scenario_budget
from app.evaluation.live.config import get_live_eval_config
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

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


def test_canary_subset_expected_replies_is_one(semi_auto_env):
    budget = build_selected_scenario_budget(
        campaign_type="semi-auto-core",
        selected_scenario_ids=("TBSM01_lead_approve_reply", "TBSM04_lead_reject"),
    )
    assert budget.expected_reply_count == 1


def test_canary_subset_inbound_sends_is_two(semi_auto_env):
    budget = build_selected_scenario_budget(
        campaign_type="semi-auto-core",
        selected_scenario_ids=("TBSM01_lead_approve_reply", "TBSM04_lead_reject"),
    )
    assert budget.inbound_send_budget == 2


def test_full_subset_expected_replies_is_four(semi_auto_env):
    budget = build_selected_scenario_budget(campaign_type="semi-auto-core")
    assert budget.expected_reply_count == 4
    assert budget.inbound_send_budget == 8


def test_subset_does_not_use_full_campaign_expected_count(semi_auto_env):
    canary = build_selected_scenario_budget(
        campaign_type="semi-auto-core",
        selected_scenario_ids=("TBSM01_lead_approve_reply", "TBSM04_lead_reject"),
    )
    full = build_selected_scenario_budget(campaign_type="semi-auto-core")
    assert canary.expected_reply_count == 1
    assert full.expected_reply_count == 4
    assert canary.expected_reply_count != full.campaign_type_reply_ceiling


def test_selected_budget_never_exceeds_campaign_ceiling(semi_auto_env):
    budget = build_selected_scenario_budget(campaign_type="semi-auto-core")
    assert budget.max_reply_count <= budget.campaign_type_reply_ceiling


def test_duplicate_scenario_id_blocked(semi_auto_env):
    with pytest.raises(LiveEvalSafetyError, match="duplicate scenario ids"):
        build_selected_scenario_budget(
            campaign_type="semi-auto-core",
            selected_scenario_ids=(
                "TBSM01_lead_approve_reply",
                "TBSM01_lead_approve_reply",
            ),
        )


def test_unknown_scenario_id_blocked(semi_auto_env):
    with pytest.raises(LiveEvalSafetyError, match="unknown or unavailable"):
        build_selected_scenario_budget(
            campaign_type="semi-auto-core",
            selected_scenario_ids=("TBSM99_missing",),
        )


def test_empty_scenario_selection_blocked(semi_auto_env):
    with pytest.raises(LiveEvalSafetyError, match="empty scenario selection"):
        build_selected_scenario_budget(
            campaign_type="semi-auto-core",
            selected_scenario_ids=(),
        )


def test_readiness_and_runner_share_budget_object(semi_auto_env):
    selected = ("TBSM01_lead_approve_reply", "TBSM04_lead_reject")
    readiness = build_full_system_testbot_readiness(
        campaign_type="semi-auto-core",
        selected_scenario_ids=selected,
    )
    matrix = readiness.gates["semi_auto_reply_contract"]
    runner_budget = build_selected_scenario_budget(
        campaign_type="semi-auto-core",
        selected_scenario_ids=selected,
    )
    assert matrix["selected_scenario_budget"]["expected_reply_count"] == 1
    assert runner_budget.expected_reply_count == matrix["scenario_expected_reply_total"]


def test_reported_expected_reply_count_from_selected_scenarios(semi_auto_env):
    matrix = build_semi_auto_reply_contract_matrix(
        selected_scenario_ids=("TBSM01_lead_approve_reply", "TBSM04_lead_reject"),
    )
    assert matrix["scenario_expected_reply_total"] == 1
    assert matrix["selected_scenario_budget"]["expected_reply_count"] == 1


def test_canary_with_one_observed_reply_passes_budget_gate(semi_auto_env):
    budget = build_selected_scenario_budget(
        campaign_type="semi-auto-core",
        selected_scenario_ids=("TBSM01_lead_approve_reply", "TBSM04_lead_reject"),
    )
    observed = 1
    assert observed <= budget.max_reply_count
    assert observed == budget.expected_reply_count


def test_canary_with_two_replies_blocks_budget_overrun(semi_auto_env):
    budget = build_selected_scenario_budget(
        campaign_type="semi-auto-core",
        selected_scenario_ids=("TBSM01_lead_approve_reply", "TBSM04_lead_reject"),
    )
    observed = 2
    assert observed > budget.max_reply_count


def test_full_campaign_budget_remains_four(semi_auto_env):
    assert CAMPAIGN_TYPE_REPLY_BUDGET["semi-auto-core"] == 4
    issues, matrix = validate_semi_auto_reply_contract()
    assert issues == []
    assert matrix["workflow_reply_budget"] == 4


def test_canary_readiness_passes_with_subset_budget(semi_auto_env):
    report = build_full_system_testbot_readiness(
        campaign_type="semi-auto-core",
        selected_scenario_ids=("TBSM01_lead_approve_reply", "TBSM04_lead_reject"),
    )
    assert report.ready is True
    contract = report.gates["semi_auto_reply_contract"]
    assert contract["selected_scenario_budget"]["expected_reply_count"] == 1


def test_run_semi_automatic_campaign_import_uses_selected_budget(semi_auto_env, monkeypatch):
    captured: dict[str, object] = {}

    class _FakeRunner:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run(self):
            return 0

        @property
        def observer(self):
            class _Observer:
                admin_api_key = "key"

                def get_observation(self, _run_id):
                    return {"job": {}}

            return _Observer()

        reply_metrics = None

    monkeypatch.setattr("app.evaluation.live.campaign.runner.LiveEvalRunner", _FakeRunner)
    run_semi_automatic_campaign(
        base_url="http://127.0.0.1:8010",
        admin_api_key="key",
        scenario_ids=("TBSM04_lead_reject",),
    )
    assert captured.get("reply_budget_remaining") == 0
