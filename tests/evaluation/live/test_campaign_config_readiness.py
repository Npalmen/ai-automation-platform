"""Regression tests for campaign-mode config readiness relaxation."""

from __future__ import annotations

import pytest

from app.evaluation.live.config import get_live_eval_config
from app.evaluation.live.safety import validate_config_readiness


@pytest.fixture
def live_eval_env(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", "TENANT_LIVE_EVAL")
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", "sender@eval.test")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", "recipient@eval.test")
    monkeypatch.setenv("LIVE_EVAL_MAX_GMAIL_REPLIES", "1")
    from app.core.settings import get_settings

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


def test_campaign_mode_allows_nonzero_reply_budget(live_eval_env):
    config = get_live_eval_config()
    assert validate_config_readiness(config, campaign_mode=True) == []


def test_default_mode_still_requires_zero_replies(live_eval_env):
    config = get_live_eval_config()
    issues = validate_config_readiness(config, campaign_mode=False)
    assert any("LIVE_EVAL_MAX_GMAIL_REPLIES" in issue for issue in issues)
