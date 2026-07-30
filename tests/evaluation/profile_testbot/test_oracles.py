"""Oracle layer tests."""

from __future__ import annotations

import pytest

from app.evaluation.profile_testbot.generator.profile_generator import generate_hermetic_campaign
from app.evaluation.profile_testbot.oracles.hard_safety import HardSafetyContext, evaluate_hard_safety
from app.evaluation.profile_testbot.oracles.runner import run_oracles
from app.evaluation.profile_testbot.oracles.semantic_judge import evaluate_semantic_judge
from app.evaluation.profile_testbot.profile_contract import load_customer_profile


@pytest.fixture
def profile():
    return load_customer_profile("pilot-service-company-v1")


def test_hard_safety_blocks_wrong_tenant(profile):
    scenario = generate_hermetic_campaign(profile, seed=0)[0]
    results = evaluate_hard_safety(
        scenario=scenario,
        profile=profile,
        context=HardSafetyContext(
            tenant_id="TENANT_PRODUCTION_PILOT_01",
            recipient_email="recipient@eval.test",
            sender_allowlist={"sender@eval.test"},
            recipient_allowlist={"recipient@eval.test"},
        ),
    )
    assert any(r.name == "tenant_isolated" and r.status == "fail" for r in results)


def test_judge_cannot_override_hard_safety(profile):
    scenario = generate_hermetic_campaign(profile, seed=0)[0]
    hard = evaluate_hard_safety(
        scenario=scenario,
        profile=profile,
        context=HardSafetyContext(
            tenant_id="TENANT_PRODUCTION_PILOT_01",
            recipient_email="recipient@eval.test",
            sender_allowlist={"sender@eval.test"},
            recipient_allowlist={"recipient@eval.test"},
        ),
    )
    judge = evaluate_semantic_judge(scenario=scenario, reply_text="ok", hard_safety_results=hard)
    assert judge[0].name == "semantic_judge_skipped"


def test_price_scenario_holds(profile):
    scenarios = generate_hermetic_campaign(profile, seed=0)
    price = next(s for s in scenarios if s.intent == "lead_price")
    evaluation = run_oracles(
        scenario=price,
        profile=profile,
        safety_context=HardSafetyContext(
            tenant_id="TENANT_LIVE_EVAL",
            recipient_email="recipient@eval.test",
            sender_allowlist={price.input.sender_email},
            recipient_allowlist={"recipient@eval.test"},
            gmail_replies=0,
        ),
    )
    assert evaluation.passed
