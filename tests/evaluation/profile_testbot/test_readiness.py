"""Readiness report tests."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.campaign.gates import validate_no_production_resources
from app.evaluation.profile_testbot.campaign.mailbox_readiness import (
    is_non_deliverable_placeholder,
    mailbox_hash,
    verify_profile_testbot_mailboxes,
)
from app.evaluation.profile_testbot.campaign.readiness import build_profile_testbot_readiness

SENDER = "eval-sender-ptb@gmail.com"
RECIPIENT = "eval-recipient-ptb@gmail.com"


@pytest.fixture
def readiness_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", "TENANT_LIVE_EVAL")
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", SENDER)
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", RECIPIENT)
    monkeypatch.setenv("LIVE_EVAL_MAX_GMAIL_REPLIES", "25")
    monkeypatch.setenv("LIVE_EVAL_SENDER_GMAIL_REFRESH_TOKEN", "test-sender-token")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_GMAIL_REFRESH_TOKEN", "test-recipient-token")
    monkeypatch.setenv("LIVE_EVAL_SENDER_GMAIL_CLIENT_ID", "sender-client-id")
    monkeypatch.setenv("LIVE_EVAL_SENDER_GMAIL_CLIENT_SECRET", "sender-client-secret")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_GMAIL_CLIENT_ID", "recipient-client-id")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_GMAIL_CLIENT_SECRET", "recipient-client-secret")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("LIVE_EVAL_PURGE_ALLOWED", "yes")
    monkeypatch.setenv("PROFILE_TESTBOT_OFFLINE_MAILBOX_CONTRACT", "yes")
    monkeypatch.delenv("LIVE_GMAIL_EVAL_ALLOWED", raising=False)
    monkeypatch.delenv("PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED", raising=False)
    monkeypatch.delenv("PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED_SHA", raising=False)
    monkeypatch.delenv("LIVE_EVAL_APP_BASE_URL", raising=False)
    monkeypatch.delenv("ADMIN_API_KEY", raising=False)
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


def test_blocked_production_pilot_is_safety_assertion_not_blocker(readiness_env):
    issues = validate_no_production_resources(tenant_id="TENANT_PRODUCTION_PILOT_01")
    assert issues
    report = build_profile_testbot_readiness()
    assert report["production_pilot_tenant_blocked"] is True
    assert "production_pilot_tenant_blocked" in report["safety_assertions"]
    assert not any("TENANT_PRODUCTION_PILOT_01 is not allowed" in item for item in report["blocking_failures"])


def test_blocked_demo_tenant_is_safety_assertion_not_blocker(readiness_env):
    issues = validate_no_production_resources(tenant_id="T_NIKLAS_DEMO_001")
    assert issues
    report = build_profile_testbot_readiness()
    assert report["demo_tenant_blocked"] is True
    assert "demo_tenant_blocked" in report["safety_assertions"]
    assert not any("T_NIKLAS_DEMO_001 is not allowed" in item for item in report["blocking_failures"])


def test_p1_mailbox_blocked_is_safety_assertion(readiness_env, monkeypatch):
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", "niklas.palm@sol-f.se")
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    report = build_profile_testbot_readiness()
    assert "p1_mailbox_blocked" in report["safety_assertions"]
    assert any("P1/production mailbox blocked" in item for item in report["blocking_failures"])


def test_single_active_eval_consumer_passes(readiness_env):
    report = build_profile_testbot_readiness()
    assert report["single_active_consumer"] is True
    assert report["ready_for_live_semi_auto"] is True
    assert report["blocking_failures"] == []


def test_two_active_consumers_fail(readiness_env, monkeypatch):
    monkeypatch.setenv("LIVE_EVAL_MAILBOX_ACTIVE_CONSUMER_TENANTS", "TENANT_OTHER")
    report = build_profile_testbot_readiness()
    assert report["single_active_consumer"] is False
    assert any("multiple active mailbox consumers" in item for item in report["blocking_failures"])


def test_missing_eval_tenant_fails(readiness_env, monkeypatch):
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", "TENANT_OTHER")
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    report = build_profile_testbot_readiness()
    assert any("LIVE_EVAL_TENANT_IDS must contain only" in item for item in report["blocking_failures"])


def test_missing_sender_fails(readiness_env, monkeypatch):
    monkeypatch.delenv("LIVE_EVAL_SENDER_EMAILS", raising=False)
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    report = build_profile_testbot_readiness()
    assert any("sender allowlist must contain exactly one" in item for item in report["blocking_failures"])


def test_missing_recipient_fails(readiness_env, monkeypatch):
    monkeypatch.delenv("LIVE_EVAL_RECIPIENT_EMAILS", raising=False)
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    report = build_profile_testbot_readiness()
    assert any("recipient allowlist must contain exactly one" in item for item in report["blocking_failures"])


def test_eval_test_placeholder_fails_live_readiness(readiness_env, monkeypatch):
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", "sender@eval.test")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", "recipient@eval.test")
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    report = build_profile_testbot_readiness()
    assert report["ready_for_live_semi_auto"] is False
    assert any("non-deliverable placeholder" in item for item in report["blocking_failures"])


def test_report_uses_hashes_without_exposing_mailboxes(readiness_env, tmp_path, monkeypatch):
    from scripts.run_profile_testbot_campaign import _write_readiness_report

    report = build_profile_testbot_readiness()
    path = _write_readiness_report(report)
    text = path.read_text(encoding="utf-8")
    assert SENDER not in text
    assert RECIPIENT not in text
    assert report["sender_mailbox_hash"] == mailbox_hash(SENDER)
    assert report["recipient_mailbox_hash"] == mailbox_hash(RECIPIENT)


def test_sender_recipient_overlap_with_p1_fails(readiness_env, monkeypatch):
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", "niklas.palm@sol-f.se")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", RECIPIENT)
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    report = build_profile_testbot_readiness()
    assert report["ready_for_live_semi_auto"] is False


def test_oauth_missing_fails(readiness_env, monkeypatch):
    monkeypatch.delenv("LIVE_EVAL_SENDER_GMAIL_REFRESH_TOKEN", raising=False)
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    report = build_profile_testbot_readiness()
    assert any("OAuth" in item for item in report["blocking_failures"])


def test_write_budget_mismatch_fails(readiness_env, monkeypatch):
    monkeypatch.setenv("LIVE_EVAL_MAX_GMAIL_REPLIES", "5")
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    report = build_profile_testbot_readiness()
    assert any("semi-auto send budget" in item for item in report["blocking_failures"])


def test_production_demo_blocking_remains_active_after_fix(readiness_env):
    report = build_profile_testbot_readiness()
    assert report["production_pilot_tenant_blocked"] is True
    assert report["demo_tenant_blocked"] is True


def test_live_qualifications_remain_pending(readiness_env):
    report = build_profile_testbot_readiness()
    assert report["live_qualifications"]["PROFILE_DRIVEN_SEMI_AUTO_GMAIL_QUALIFIED"] == "PENDING"
    assert report["live_qualifications"]["PROFILE_DRIVEN_AUTOMATIC_GMAIL_QUALIFIED"] == "PENDING"
    assert report["live_qualifications"]["PROFILE_DRIVEN_TESTBOT_PASS"] == "PENDING"


def test_readiness_reports_manifest_and_oracle_authority(readiness_env):
    report = build_profile_testbot_readiness()
    assert report["eval_tenant"] == "TENANT_LIVE_EVAL"
    assert report["semi_auto_manifest"]["scenario_manifest_count"] == 40
    assert report["semi_auto_manifest"]["send_after_approval_count"] >= 20
    assert report["semi_auto_manifest"]["hold_reject_no_reply_count"] >= 20
    assert report["oracle_authority"]["semantic_judge"] == "STUB_NOT_QUALIFICATION_AUTHORITY"


def test_provider_read_only_verification_when_gmail_eval_enabled(readiness_env, monkeypatch):
    monkeypatch.setenv("LIVE_GMAIL_EVAL_ALLOWED", "yes")
    monkeypatch.delenv("PROFILE_TESTBOT_OFFLINE_MAILBOX_CONTRACT", raising=False)
    monkeypatch.setenv("LIVE_EVAL_APP_BASE_URL", "http://127.0.0.1:8010")
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED", "yes")
    monkeypatch.setenv(
        "PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED_SHA",
        "84887d9f336a27e94b0a7dcf8398e8b6d81338af",
    )
    sender_client = MagicMock()
    sender_client.get_profile_email.return_value = SENDER
    recipient_client = MagicMock()
    recipient_client.get_profile_email.return_value = RECIPIENT
    remote_payload = {
        "build_git_sha": "84887d9f336a27e94b0a7dcf8398e8b6d81338af",
        "worker_build_git_sha": "84887d9f336a27e94b0a7dcf8398e8b6d81338af",
    }
    with patch(
        "app.evaluation.profile_testbot.campaign.runtime_sha_readiness.fetch_eval_stack_runtime_readiness",
        return_value=(remote_payload, None),
    ), patch(
        "app.evaluation.profile_testbot.campaign.mailbox_readiness.build_sender_client",
        return_value=sender_client,
    ), patch(
        "app.evaluation.profile_testbot.campaign.mailbox_readiness.build_recipient_client",
        return_value=recipient_client,
    ):
        report = build_profile_testbot_readiness()
    assert report["sender_provider_verified"] is True
    assert report["recipient_deliverability_verified"] is True
    assert report["ready_for_live_semi_auto"] is True
    assert report["runtime_readiness_endpoint_verified"] is True
    assert report["runtime_sha_consistent"] is True
    sender_client.send_message.assert_not_called()


def test_non_deliverable_placeholder_detection():
    assert is_non_deliverable_placeholder("sender@eval.test")
    assert not is_non_deliverable_placeholder("eval-sender@gmail.com")


def test_mailbox_verify_rejects_placeholder():
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    report = verify_profile_testbot_mailboxes(
        sender_email="sender@eval.test",
        recipient_email="recipient@eval.test",
        config=get_live_eval_config(),
    )
    assert report["blocking_failures"]


def test_readiness_json_output_redacts_mailboxes(readiness_env, monkeypatch, capsys):
    from scripts.run_profile_testbot_campaign import main

    exit_code = main(["readiness"])
    captured = capsys.readouterr().out
    assert SENDER not in captured
    assert RECIPIENT not in captured
    payload = json.loads(captured.split("report=")[0].strip())
    assert payload["blocking_failures"] == []
    assert exit_code == 0
