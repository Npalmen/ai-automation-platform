"""Tests for full-system testbot readiness builder."""

from __future__ import annotations

import pytest

from app.evaluation.live.campaign.readiness import build_full_system_testbot_readiness
from app.evaluation.live.campaign.registry import clear_campaign_registry_cache


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
    monkeypatch.setenv("LIVE_GMAIL_EVAL_ALLOWED", "yes")
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


def test_readiness_passes_with_campaign_env(campaign_env):
    report = build_full_system_testbot_readiness(campaign_type="transport-smoke")
    assert report.scenario_count == 5
    assert report.campaign_manifest_version == "full-system-testbot-campaign-v1"
    assert report.gates["campaign_enabled"] is True


def test_readiness_fails_for_production_url(campaign_env):
    report = build_full_system_testbot_readiness(
        campaign_type="transport-smoke",
        app_base_url="https://api.krowolf.se",
    )
    assert not report.ready
    assert any("production host" in i for i in report.issues)
