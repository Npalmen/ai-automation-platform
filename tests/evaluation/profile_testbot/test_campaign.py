"""Campaign readiness and operator guard tests."""

from __future__ import annotations

import pytest

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.profile_testbot.campaign.hermetic_runner import run_hermetic_profile_campaign
from app.evaluation.profile_testbot.campaign.live_runners import plan_semi_auto_live_campaign
from app.evaluation.profile_testbot.campaign.readiness import (
    require_live_semi_auto_approval,
    validate_profile_testbot_tenant,
)
from app.evaluation.profile_testbot.constants import OPERATOR_STOP_SEMI_AUTO
from app.evaluation.profile_testbot.generator.profile_generator import generate_semi_auto_campaign
from app.evaluation.profile_testbot.harness.operator_guards import require_oracle_pass_for_operator_action
from app.evaluation.profile_testbot.learning.failure_loop import classify_failure, promote_failure_to_regression
from app.evaluation.profile_testbot.oracles.runner import run_oracles
from app.evaluation.profile_testbot.oracles.hard_safety import HardSafetyContext
from app.evaluation.profile_testbot.profile_contract import load_customer_profile


def test_production_pilot_tenant_blocked():
    assert validate_profile_testbot_tenant("TENANT_PRODUCTION_PILOT_01")


def test_live_semi_auto_requires_approval(monkeypatch):
    monkeypatch.delenv("PROFILE_TESTBOT_LIVE_SEMI_AUTO_APPROVED", raising=False)
    assert require_live_semi_auto_approval() == OPERATOR_STOP_SEMI_AUTO


def test_semi_auto_plan_stops_without_approval(monkeypatch):
    monkeypatch.delenv("PROFILE_TESTBOT_LIVE_SEMI_AUTO_APPROVED", raising=False)
    plan = plan_semi_auto_live_campaign()
    assert plan.blocked_reason == OPERATOR_STOP_SEMI_AUTO


def test_operator_guard_blocks_without_oracle_pass():
    profile = load_customer_profile("pilot-service-company-v1")
    scenario = next(
        s for s in generate_semi_auto_campaign(profile, seed=0)
        if s.expected_send_behavior == "send_after_approval"
    )
    evaluation = run_oracles(
        scenario=scenario,
        profile=profile,
        safety_context=HardSafetyContext(
            tenant_id="TENANT_PRODUCTION_PILOT_01",
            recipient_email="recipient@eval.test",
            sender_allowlist={scenario.input.sender_email},
            recipient_allowlist={"recipient@eval.test"},
        ),
    )
    with pytest.raises(LiveEvalSafetyError):
        require_oracle_pass_for_operator_action(scenario=scenario, evaluation=evaluation)


def test_hermetic_campaign_passes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run_hermetic_profile_campaign(seed=0)
    assert result.overall_status == "PASS"
    assert result.scenario_count == 120


def test_failure_promotion_writes_regression_corpus(tmp_path):
    failure = classify_failure(scenario_id="PTB-0001", blockers=["route_queue"])
    record = promote_failure_to_regression(
        failure=failure,
        scenario_payload={"scenario_id": "PTB-0001"},
        corpus_path=str(tmp_path / "regression_corpus.json"),
    )
    assert record["category"] == "routing"
