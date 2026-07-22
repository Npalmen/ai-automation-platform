"""Hermetic tests for read-only sender Gmail readiness."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.gmail_transport import run_sender_readiness_read_only
from app.integrations.google.mail_client import GmailMessageListResult


@pytest.fixture
def single_address_env(live_eval_env, monkeypatch):
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", "sender@eval.test")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", "recipient@eval.test")
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    yield
    get_live_eval_config.cache_clear()


def test_sender_readiness_read_only_passes_with_profile_and_read_scope(single_address_env):
    client = MagicMock()
    client.get_profile_email.return_value = "sender@eval.test"
    client.list_messages_page.return_value = GmailMessageListResult(message_ids=[], truncated=False)

    with patch("app.evaluation.live.gmail_transport.build_sender_client", return_value=client):
        report = run_sender_readiness_read_only(
            expected_sender="sender@eval.test",
            expected_recipient="recipient@eval.test",
        )

    assert report.ready is True
    assert report.read_scope_verified is True
    client.send_message.assert_not_called()
    client.archive_from_inbox.assert_not_called()
    client.modify_message_labels.assert_not_called()


def test_sender_readiness_read_only_profile_mismatch(single_address_env):
    client = MagicMock()
    client.get_profile_email.return_value = "other@eval.test"
    client.list_messages_page.return_value = GmailMessageListResult(message_ids=[], truncated=False)

    with patch("app.evaluation.live.gmail_transport.build_sender_client", return_value=client):
        report = run_sender_readiness_read_only(
            expected_sender="sender@eval.test",
            expected_recipient="recipient@eval.test",
        )

    assert report.ready is False
    assert any("profile email" in issue for issue in report.issues)


def test_sender_readiness_read_only_multiple_senders_fail(live_eval_env, monkeypatch):
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", "a@eval.test,b@eval.test")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", "recipient@eval.test")
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()

    report = run_sender_readiness_read_only(
        expected_sender="a@eval.test",
        expected_recipient="recipient@eval.test",
    )
    assert report.ready is False
    assert any("exactly one LIVE_EVAL_SENDER_EMAILS" in issue for issue in report.issues)


def test_sender_readiness_read_only_missing_credentials(single_address_env, monkeypatch):
    monkeypatch.delenv("LIVE_EVAL_SENDER_GMAIL_REFRESH_TOKEN", raising=False)
    report = run_sender_readiness_read_only(
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
    )
    assert report.ready is False
    assert report.issues


def test_sender_readiness_read_only_auth_failure(single_address_env):
    with patch(
        "app.evaluation.live.gmail_transport.build_sender_client",
        side_effect=RuntimeError("token refresh failed"),
    ):
        report = run_sender_readiness_read_only(
            expected_sender="sender@eval.test",
            expected_recipient="recipient@eval.test",
        )
    assert report.ready is False
    assert any("sender_auth" in issue for issue in report.issues)


def test_validate_config_sender_readiness_redacted_output(single_address_env, monkeypatch):
    client = MagicMock()
    client.get_profile_email.return_value = "sender@eval.test"
    client.list_messages_page.return_value = GmailMessageListResult(message_ids=[], truncated=False)

    with patch("app.evaluation.live.gmail_transport.build_sender_client", return_value=client):
        from scripts.run_live_eval import main

        exit_code = main(
            [
                "validate-config",
                "--sender-readiness",
                "--confirm-read-only",
            ]
        )

    assert exit_code == 0


def test_readiness_only_writes_redacted_report(single_address_env, monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin")
    monkeypatch.setenv("LIVE_EVAL_APP_BASE_URL", "http://127.0.0.1:8010")
    monkeypatch.setenv("BUILD_GIT_SHA", "abc123")

    client = MagicMock()
    client.get_profile_email.return_value = "sender@eval.test"
    client.list_messages_page.return_value = GmailMessageListResult(message_ids=[], truncated=False)

    runtime = {"env": "test", "database_ok": True, "build_git_sha": "abc123"}
    gmail = {
        "ready": True,
        "issues": [],
        "checks": {
            "gmail_profile_email": "recipient@eval.test",
            "label_present": True,
            "intake_query": "label:krowolf-live-eval is:unread",
        },
    }

    with patch("app.evaluation.live.gmail_transport.build_sender_client", return_value=client), patch(
        "scripts.run_live_eval._fetch_runtime_and_recipient_readiness",
        return_value=(runtime, gmail, 200),
    ):
        from scripts.run_live_eval import main

        report_path = tmp_path / "readiness_report.json"
        exit_code = main(
            [
                "readiness-only",
                "--tenant-id",
                "TENANT_LIVE_EVAL",
                "--confirm-read-only",
                "--report-file",
                str(report_path),
            ]
        )

    assert exit_code == 0
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["result"] == "passed"
    assert payload["external_sends"] == 0
    assert payload["gmail_mutations"] == 0
    assert "refresh_token" not in report_path.read_text(encoding="utf-8")
    assert "sender@eval.test" not in report_path.read_text(encoding="utf-8")
