"""Generator determinism and coverage tests."""

from __future__ import annotations

from app.evaluation.profile_testbot.constants import HERMETIC_SCENARIO_TARGET
from app.evaluation.profile_testbot.generator.deduplication import find_semantic_duplicates
from app.evaluation.profile_testbot.generator.profile_generator import (
    generate_hermetic_campaign,
    generate_semi_auto_campaign,
)
from app.evaluation.profile_testbot.profile_contract import load_customer_profile


def test_generator_reproducible_from_seed():
    profile = load_customer_profile("pilot-service-company-v1")
    first = generate_hermetic_campaign(profile, seed=42)
    second = generate_hermetic_campaign(profile, seed=42)
    assert [s.scenario_id for s in first] == [s.scenario_id for s in second]
    assert [s.semantic_hash for s in first] == [s.semantic_hash for s in second]


def test_hermetic_campaign_meets_volume():
    profile = load_customer_profile("pilot-service-company-v1")
    scenarios = generate_hermetic_campaign(profile, seed=0)
    assert len(scenarios) == HERMETIC_SCENARIO_TARGET
    assert not find_semantic_duplicates(scenarios)


def test_semi_auto_campaign_distribution():
    profile = load_customer_profile("pilot-service-company-v1")
    scenarios = generate_semi_auto_campaign(profile, seed=0)
    assert len(scenarios) == 40
    send_after = [s for s in scenarios if s.expected_send_behavior == "send_after_approval"]
    hold_edge = [
        s
        for s in scenarios
        if s.expected_send_behavior in {"hold", "reject", "no_reply", "observe_only"}
    ]
    assert len(send_after) >= 20
    assert len(hold_edge) >= 20
