"""Tests for full-system testbot campaign gates."""

from __future__ import annotations

import pytest

from app.evaluation.live.campaign.gates import (
    campaign_enabled,
    require_campaign_scenario_allowed,
    require_scenario_allowed_for_live_gmail,
    validate_campaign_budget_config,
    validate_no_production_resources,
)
from app.evaluation.live.campaign.registry import clear_campaign_registry_cache
from app.evaluation.live.errors import LiveEvalSafetyError


@pytest.fixture(autouse=True)
def _clear_registry_cache():
    clear_campaign_registry_cache()
    yield
    clear_campaign_registry_cache()


@pytest.fixture
def campaign_env(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", "TENANT_LIVE_EVAL")
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", "sender@eval.test")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", "recipient@eval.test")
    monkeypatch.setenv("LIVE_EVAL_MAX_SCENARIOS_PER_RUN", "5")
    monkeypatch.setenv("LIVE_EVAL_MAX_GMAIL_SENDS", "5")
    monkeypatch.setenv("LIVE_EVAL_MAX_GMAIL_REPLIES", "0")
    from app.core.settings import get_settings
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


def test_campaign_enabled_requires_flag(campaign_env, monkeypatch):
    from app.evaluation.live.config import get_live_eval_config

    assert campaign_enabled()
    monkeypatch.delenv("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED", raising=False)
    get_live_eval_config.cache_clear()
    assert not campaign_enabled()


def test_s01_still_allowed_without_campaign_flag(live_eval_env):
    require_scenario_allowed_for_live_gmail("S01_lead_laddbox_quality")


def test_campaign_scenario_requires_campaign_flag(live_eval_env):
    with pytest.raises(LiveEvalSafetyError, match="FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED"):
        require_scenario_allowed_for_live_gmail("TBS01_lead_observe")


def test_campaign_scenario_allowed_with_flag(campaign_env):
    require_campaign_scenario_allowed("TBS01_lead_observe")
    require_scenario_allowed_for_live_gmail("TBS01_lead_observe")


def test_unknown_scenario_rejected(campaign_env):
    with pytest.raises(LiveEvalSafetyError, match="not allowlisted"):
        require_campaign_scenario_allowed("TBS99_missing")


def test_validate_no_production_resources_blocks_pilot_tenant():
    issues = validate_no_production_resources(tenant_id="T_NIKLAS_DEMO_001")
    assert any("pilot tenant" in i for i in issues)


def test_validate_no_production_resources_blocks_prod_url():
    issues = validate_no_production_resources(app_base_url="https://api.krowolf.se")
    assert any("production host" in i for i in issues)


def test_campaign_budget_allows_five_sends(campaign_env):
    from app.evaluation.live.config import get_live_eval_config

    issues = validate_campaign_budget_config(
        campaign_type="transport-smoke",
        config=get_live_eval_config(),
    )
    assert issues == []
