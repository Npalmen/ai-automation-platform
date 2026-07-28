"""Automatic expected outcome resolver tests."""

from __future__ import annotations

from app.evaluation.live.campaign.automatic_expected_outcomes import (
    resolve_automatic_expected_outcome,
)
from app.evaluation.live.campaign.registry import clear_campaign_registry_cache, get_campaign_scenario


def setup_function():
    clear_campaign_registry_cache()


def teardown_function():
    clear_campaign_registry_cache()


def test_tba01_expects_auto_reply():
    scenario = get_campaign_scenario("TBA01_safe_lead_auto_reply")
    outcome = resolve_automatic_expected_outcome(scenario)
    assert outcome.expected_reply is True
    assert outcome.policy_authorization == "execution_allowed"
    assert outcome.final_job_status == "completed"
    assert outcome.expect_execution_intent is True


def test_tba02_expects_hold_without_reply():
    scenario = get_campaign_scenario("TBA02_unknown_auto_hold")
    outcome = resolve_automatic_expected_outcome(scenario)
    assert outcome.expected_reply is False
    assert outcome.is_negative_hold is True
    assert outcome.expect_execution_intent is False
