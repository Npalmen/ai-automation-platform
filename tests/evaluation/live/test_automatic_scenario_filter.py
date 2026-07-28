"""Automatic scenario filter and budget tests."""

from __future__ import annotations

import pytest

from app.evaluation.live.campaign.automatic_action_contract import (
    AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE,
    AUTOMATIC_GMAIL_CANARY_SCENARIO_IDS,
)
from app.evaluation.live.campaign.registry import clear_campaign_registry_cache
from app.evaluation.live.campaign.scenario_budget import build_selected_scenario_budget
from app.evaluation.live.errors import LiveEvalSafetyError


@pytest.fixture(autouse=True)
def _clear_registry():
    clear_campaign_registry_cache()
    yield
    clear_campaign_registry_cache()


def test_automatic_canary_budget_is_two_sends_one_reply():
    budget = build_selected_scenario_budget(
        campaign_type=AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE,
        selected_scenario_ids=AUTOMATIC_GMAIL_CANARY_SCENARIO_IDS,
    )
    assert budget.inbound_send_budget == 2
    assert budget.expected_reply_count == 1
    assert budget.non_gmail_write_budget == 0


def test_automatic_canary_rejects_unknown_scenario():
    with pytest.raises(LiveEvalSafetyError, match="unknown or unavailable"):
        build_selected_scenario_budget(
            campaign_type=AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE,
            selected_scenario_ids=("TBA99_missing", "TBA02_unknown_auto_hold"),
        )
