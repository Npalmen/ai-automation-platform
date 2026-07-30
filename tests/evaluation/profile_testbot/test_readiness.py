"""Readiness report tests."""

from __future__ import annotations

import pytest

from app.evaluation.profile_testbot.campaign.readiness import build_profile_testbot_readiness


@pytest.fixture
def readiness_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", "TENANT_LIVE_EVAL")
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", "sender@eval.test")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", "recipient@eval.test")
    monkeypatch.setenv("LIVE_EVAL_MAX_GMAIL_REPLIES", "25")
    monkeypatch.setenv("LIVE_EVAL_SENDER_GMAIL_REFRESH_TOKEN", "test-sender-token")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_GMAIL_REFRESH_TOKEN", "test-recipient-token")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("LIVE_EVAL_PURGE_ALLOWED", "yes")
    storage = tmp_path / "live_eval"
    storage.mkdir()
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    from app.core.settings import get_settings
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


def test_readiness_reports_manifest_and_oracle_authority(readiness_env):
    report = build_profile_testbot_readiness()
    assert report["eval_tenant"] == "TENANT_LIVE_EVAL"
    assert report["semi_auto_manifest"]["scenario_manifest_count"] == 40
    assert report["semi_auto_manifest"]["send_after_approval_count"] >= 20
    assert report["semi_auto_manifest"]["hold_reject_no_reply_count"] >= 20
    assert report["oracle_authority"]["semantic_judge"] == "STUB_NOT_QUALIFICATION_AUTHORITY"
    assert report["live_qualifications"]["PROFILE_DRIVEN_SEMI_AUTO_GMAIL_QUALIFIED"] == "PENDING"
