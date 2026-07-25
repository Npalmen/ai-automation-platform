"""Tests for full-system testbot campaign registry."""

from __future__ import annotations

import pytest

from app.evaluation.live.campaign.registry import (
    clear_campaign_registry_cache,
    get_campaign_scenario,
    list_campaign_scenarios,
    load_campaign_manifest,
)
from app.evaluation.live.errors import LiveEvalSafetyError


@pytest.fixture(autouse=True)
def _clear_registry_cache():
    clear_campaign_registry_cache()
    yield
    clear_campaign_registry_cache()


def test_manifest_loads():
    manifest = load_campaign_manifest()
    assert manifest["manifest_version"] == "full-system-testbot-campaign-v1"


def test_transport_smoke_has_five_scenarios():
    scenarios = list_campaign_scenarios(campaign_type="transport-smoke")
    assert len(scenarios) == 5
    ids = {s.scenario_id for s in scenarios}
    assert ids == {
        "TBS01_lead_observe",
        "TBS02_support_observe",
        "TBS03_invoice_observe",
        "TBS04_unknown_observe",
        "TBS05_noisy_observe",
    }


def test_all_transport_scenarios_are_observe_mode():
    scenarios = list_campaign_scenarios(campaign_type="transport-smoke")
    assert all(s.mode == "observe" for s in scenarios)
    assert all(s.budgets.gmail_replies == 0 for s in scenarios)
    assert all(s.budgets.external_writes == 0 for s in scenarios)


def test_scenario_content_hash_is_stable():
    s1 = get_campaign_scenario("TBS01_lead_observe")
    s2 = get_campaign_scenario("TBS01_lead_observe")
    assert s1.content_hash == s2.content_hash
    assert len(s1.content_hash) == 64


def test_unknown_scenario_raises():
    with pytest.raises(LiveEvalSafetyError, match="not found"):
        get_campaign_scenario("TBS99_missing")
