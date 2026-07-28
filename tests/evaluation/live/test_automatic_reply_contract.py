"""Automatic reply contract tests."""

from __future__ import annotations

import pytest

from app.evaluation.live.campaign.automatic_reply_contract import (
    build_automatic_reply_contract_matrix,
    validate_automatic_reply_contract,
)
from app.evaluation.live.campaign.registry import clear_campaign_registry_cache
from app.evaluation.live.config import get_live_eval_config


@pytest.fixture(autouse=True)
def _clear_registry(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_GMAIL_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", "TENANT_LIVE_EVAL")
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", "sender@eval.test")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", "recipient@eval.test")
    monkeypatch.setenv("LIVE_EVAL_MAX_GMAIL_REPLIES", "1")
    from app.core.settings import get_settings

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    clear_campaign_registry_cache()
    yield
    clear_campaign_registry_cache()
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


def test_automatic_reply_contract_matrix_expected_total_is_one():
    matrix = build_automatic_reply_contract_matrix()
    assert matrix["scenario_expected_reply_total"] == 1


def test_automatic_reply_contract_passes_with_reply_budget():
    issues, matrix = validate_automatic_reply_contract()
    assert issues == []
    assert matrix["scenario_expected_reply_total"] == 1
