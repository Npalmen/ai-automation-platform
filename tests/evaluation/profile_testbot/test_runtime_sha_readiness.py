"""Tests for remote eval-stack runtime SHA readiness enforcement."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.evaluation.profile_testbot.campaign.readiness import build_profile_testbot_readiness
from app.evaluation.profile_testbot.campaign.runtime_sha_readiness import (
    evaluate_eval_stack_runtime_sha,
)

APPROVED_SHA = "84887d9f336a27e94b0a7dcf8398e8b6d81338af"
OLD_SHA = "3d2b0acdbf3a599ac87f2b0f8d01b022bca9b59b"
BASE_URL = "http://127.0.0.1:8010"


def _remote_payload(*, api: str, worker: str) -> dict:
    return {
        "env": "test",
        "build_git_sha": api,
        "api_build_git_sha": api,
        "worker_build_git_sha": worker,
        "live_eval_enabled": True,
    }


def test_approved_matches_local_but_api_runs_old_sha():
    with patch(
        "app.evaluation.profile_testbot.campaign.runtime_sha_readiness.fetch_eval_stack_runtime_readiness",
        return_value=(_remote_payload(api=OLD_SHA, worker=OLD_SHA), None),
    ):
        report = evaluate_eval_stack_runtime_sha(
            base_url=BASE_URL,
            admin_api_key="test-admin-key",
            approved_runtime_sha=APPROVED_SHA,
            runner_runtime_sha=APPROVED_SHA,
            require_remote=True,
        )
    assert report["runtime_sha_consistent"] is False
    assert any("EVAL_STACK_RUNTIME_SHA_MISMATCH" in item for item in report["blocking_failures"])


def test_api_matches_but_worker_differs():
    with patch(
        "app.evaluation.profile_testbot.campaign.runtime_sha_readiness.fetch_eval_stack_runtime_readiness",
        return_value=(_remote_payload(api=APPROVED_SHA, worker=OLD_SHA), None),
    ):
        report = evaluate_eval_stack_runtime_sha(
            base_url=BASE_URL,
            admin_api_key="test-admin-key",
            approved_runtime_sha=APPROVED_SHA,
            runner_runtime_sha=APPROVED_SHA,
            require_remote=True,
        )
    assert report["runtime_sha_consistent"] is False
    assert any("EVAL_STACK_RUNTIME_SHA_MISMATCH" in item for item in report["blocking_failures"])


def test_remote_endpoint_missing_sha():
    with patch(
        "app.evaluation.profile_testbot.campaign.runtime_sha_readiness.fetch_eval_stack_runtime_readiness",
        return_value=({"build_git_sha": None, "worker_build_git_sha": None}, None),
    ):
        report = evaluate_eval_stack_runtime_sha(
            base_url=BASE_URL,
            admin_api_key="test-admin-key",
            approved_runtime_sha=APPROVED_SHA,
            runner_runtime_sha=APPROVED_SHA,
            require_remote=True,
        )
    assert report["runtime_sha_consistent"] is False
    assert any("EVAL_STACK_RUNTIME_SHA_MISSING" in item for item in report["blocking_failures"])


def test_remote_endpoint_down():
    with patch(
        "app.evaluation.profile_testbot.campaign.runtime_sha_readiness.fetch_eval_stack_runtime_readiness",
        return_value=(None, "EVAL_STACK_RUNTIME_READINESS_UNAVAILABLE: ConnectError"),
    ):
        report = evaluate_eval_stack_runtime_sha(
            base_url=BASE_URL,
            admin_api_key="test-admin-key",
            approved_runtime_sha=APPROVED_SHA,
            runner_runtime_sha=APPROVED_SHA,
            require_remote=True,
        )
    assert report["runtime_readiness_endpoint_verified"] is False
    assert any("EVAL_STACK_RUNTIME_READINESS_UNAVAILABLE" in item for item in report["blocking_failures"])


def test_remote_endpoint_auth_failed_without_secret_leak():
    with patch(
        "app.evaluation.profile_testbot.campaign.runtime_sha_readiness.fetch_eval_stack_runtime_readiness",
        return_value=(None, "EVAL_STACK_RUNTIME_READINESS_AUTH_FAILED: http_401"),
    ):
        report = evaluate_eval_stack_runtime_sha(
            base_url=BASE_URL,
            admin_api_key="super-secret-admin-key",
            approved_runtime_sha=APPROVED_SHA,
            runner_runtime_sha=APPROVED_SHA,
            require_remote=True,
        )
    assert any("AUTH_FAILED" in item for item in report["blocking_failures"])
    assert "super-secret-admin-key" not in str(report)


def test_all_runtime_shas_match_passes():
    with patch(
        "app.evaluation.profile_testbot.campaign.runtime_sha_readiness.fetch_eval_stack_runtime_readiness",
        return_value=(_remote_payload(api=APPROVED_SHA, worker=APPROVED_SHA), None),
    ):
        report = evaluate_eval_stack_runtime_sha(
            base_url=BASE_URL,
            admin_api_key="test-admin-key",
            approved_runtime_sha=APPROVED_SHA,
            runner_runtime_sha=APPROVED_SHA,
            require_remote=True,
        )
    assert report["runtime_sha_consistent"] is True
    assert report["blocking_failures"] == []
    assert report["api_runtime_sha"] == APPROVED_SHA
    assert report["worker_runtime_sha"] == APPROVED_SHA


@pytest.fixture
def live_runtime_env(monkeypatch, tmp_path):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", "TENANT_LIVE_EVAL")
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", "eval-sender-ptb@gmail.com")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", "eval-recipient-ptb@gmail.com")
    monkeypatch.setenv("LIVE_EVAL_MAX_GMAIL_REPLIES", "25")
    monkeypatch.setenv("LIVE_EVAL_SENDER_GMAIL_REFRESH_TOKEN", "test-sender-token")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_GMAIL_REFRESH_TOKEN", "test-recipient-token")
    monkeypatch.setenv("LIVE_EVAL_SENDER_GMAIL_CLIENT_ID", "sender-client-id")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_GMAIL_CLIENT_SECRET", "sender-client-secret")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_GMAIL_CLIENT_ID", "recipient-client-id")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_GMAIL_CLIENT_SECRET", "recipient-client-secret")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("LIVE_EVAL_PURGE_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_GMAIL_EVAL_ALLOWED", "yes")
    monkeypatch.delenv("PROFILE_TESTBOT_OFFLINE_MAILBOX_CONTRACT", raising=False)
    monkeypatch.setenv("LIVE_EVAL_APP_BASE_URL", BASE_URL)
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED", "yes")
    monkeypatch.setenv("PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED_SHA", APPROVED_SHA)
    monkeypatch.setenv("STORAGE_PATH", str(tmp_path))
    from app.core.settings import get_settings
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


def test_readiness_does_not_create_gmail_sends_or_jobs(live_runtime_env):
    sender_client = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    sender_client.get_profile_email.return_value = "eval-sender-ptb@gmail.com"
    recipient_client = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    recipient_client.get_profile_email.return_value = "eval-recipient-ptb@gmail.com"
    with patch(
        "app.evaluation.profile_testbot.campaign.runtime_sha_readiness.fetch_eval_stack_runtime_readiness",
        return_value=(_remote_payload(api=APPROVED_SHA, worker=APPROVED_SHA), None),
    ), patch(
        "app.evaluation.profile_testbot.campaign.mailbox_readiness.build_sender_client",
        return_value=sender_client,
    ), patch(
        "app.evaluation.profile_testbot.campaign.mailbox_readiness.build_recipient_client",
        return_value=recipient_client,
    ), patch("httpx.post") as post_mock, patch("httpx.get") as get_mock:
        report = build_profile_testbot_readiness()
    post_mock.assert_not_called()
    assert not any("/jobs" in str(call.args[0]) for call in get_mock.call_args_list if call.args)
    assert report["runtime_readiness_endpoint_verified"] is True


def test_existing_tenant_blockers_still_apply(live_runtime_env, monkeypatch):
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", "TENANT_OTHER")
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    with patch(
        "app.evaluation.profile_testbot.campaign.runtime_sha_readiness.fetch_eval_stack_runtime_readiness",
        return_value=(_remote_payload(api=APPROVED_SHA, worker=APPROVED_SHA), None),
    ):
        report = build_profile_testbot_readiness()
    assert any("LIVE_EVAL_TENANT_IDS must contain only" in item for item in report["blocking_failures"])
