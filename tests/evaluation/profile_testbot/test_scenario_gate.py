"""Tests for profile testbot live Gmail scenario gates."""

from __future__ import annotations

import pytest

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.safety import (
    require_scenario_allowed_for_live_gmail,
    validate_live_gmail_registration,
    validate_registration_request,
)
from app.evaluation.profile_testbot.campaign.scenario_gate import (
    is_profile_testbot_quality_scenario,
    locked_profile_testbot_quality_scenario_ids,
)
from app.evaluation.profile_testbot.qualification.live_canary_manifest import (
    LIVE_QUALITY_CANARY_SCENARIO_IDS,
)


@pytest.fixture
def quality_live_env(monkeypatch):
    sha = "ffdc0091b8a61b38c49aae6c8ccd351a2405ad0f"
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_GMAIL_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_LLM_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", "TENANT_LIVE_EVAL")
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", "sender@eval.test")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", "recipient@eval.test")
    monkeypatch.setenv("LIVE_EVAL_LLM_MODEL", "gpt-4o-mini")
    monkeypatch.setenv("LIVE_EVAL_LLM_PROVIDER", "openai")
    monkeypatch.setenv("BUILD_GIT_SHA", sha)
    monkeypatch.setenv("BUILD_COMMIT_SHA", sha)
    monkeypatch.setenv("GIT_COMMIT", sha)
    monkeypatch.setenv("PROFILE_TESTBOT_LIVE_QUALITY_APPROVED", "yes")
    monkeypatch.setenv("PROFILE_TESTBOT_LIVE_QUALITY_RUNNER_APPROVED", "yes")
    monkeypatch.setenv("PROFILE_TESTBOT_LIVE_QUALITY_RUNNER_APPROVED_SHA", sha)
    from app.core.settings import get_settings
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


def test_locked_quality_manifest_includes_canary_ids():
    locked = locked_profile_testbot_quality_scenario_ids()
    assert LIVE_QUALITY_CANARY_SCENARIO_IDS[0] in locked
    assert is_profile_testbot_quality_scenario("PTB-Q96-0000")
    assert not is_profile_testbot_quality_scenario("PTB-Q96-9999")


def test_quality_scenario_allowed_for_live_gmail(quality_live_env):
    require_scenario_allowed_for_live_gmail("PTB-Q96-0000")
    validate_live_gmail_registration(
        transport_mode="live_gmail",
        scenario_id="PTB-Q96-0000",
        ai_mode="live_llm",
    )


def test_quality_scenario_rejects_fixture_ai(quality_live_env):
    with pytest.raises(LiveEvalSafetyError, match="live_llm"):
        validate_live_gmail_registration(
            transport_mode="live_gmail",
            scenario_id="PTB-Q96-0000",
            ai_mode="fixture_ai",
        )


def test_quality_registration_requires_operator_approval(quality_live_env, monkeypatch):
    monkeypatch.delenv("PROFILE_TESTBOT_LIVE_QUALITY_APPROVED", raising=False)
    with pytest.raises(LiveEvalSafetyError, match="PROFILE_TESTBOT_LIVE_QUALITY_APPROVED"):
        validate_registration_request(
            tenant_id="TENANT_LIVE_EVAL",
            transport_mode="live_gmail",
            ai_mode="live_llm",
            scenario_id="PTB-Q96-0000",
            expected_sender="sender@eval.test",
            expected_recipient="recipient@eval.test",
            llm_provider="openai",
            llm_requested_model="gpt-4o-mini",
        )
