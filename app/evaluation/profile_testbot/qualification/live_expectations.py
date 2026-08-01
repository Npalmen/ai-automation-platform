"""Resolve locked quality scenario expectations during live eval runs."""

from __future__ import annotations

from functools import lru_cache

from app.evaluation.profile_testbot.constants import QUALITY_LIVE_PROFILE_ID
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.profile_testbot.quality_dataset import generate_quality_dataset
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario


@lru_cache(maxsize=1)
def _quality_scenarios_by_id() -> dict[str, ProfileScenario]:
    profile = load_customer_profile(QUALITY_LIVE_PROFILE_ID)
    scenarios = generate_quality_dataset(profile, seed=0)
    return {scenario.scenario_id: scenario for scenario in scenarios}


def quality_scenario_for_live_eval(scenario_id: str | None) -> ProfileScenario | None:
    normalized = (scenario_id or "").strip()
    if not normalized.startswith("PTB-Q96-"):
        return None
    return _quality_scenarios_by_id().get(normalized)


def expected_send_behavior_for_live_eval(scenario_id: str | None) -> str | None:
    scenario = quality_scenario_for_live_eval(scenario_id)
    if scenario is None:
        return None
    return scenario.expected_send_behavior
