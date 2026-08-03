"""Tests for read-only recipient Gmail readiness."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.delivery_mailbox_reader import (
    CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV,
    GoogleMailClientDeliveryReader,
)
from app.evaluation.live.recipient_gmail_readiness import run_recipient_gmail_readiness
from app.integrations.google.mail_client import GmailMessageListResult, TokenRefreshResult


def _mock_reader():
    client = MagicMock()
    client.get_profile_email.return_value = "recipient@eval.test"
    client.list_labels.return_value = [{"id": "INBOX", "name": "INBOX"}]
    client.list_messages_page.return_value = GmailMessageListResult(
        message_ids=[], truncated=False
    )
    return GoogleMailClientDeliveryReader(client)


def test_recipient_readiness_passes_with_live_api_calls(single_address_env):
    refresh = TokenRefreshResult(
        access_token="access-token",
        granted_scopes=frozenset({"https://www.googleapis.com/auth/gmail.readonly"}),
    )
    with (
        patch(
            "app.evaluation.live.recipient_gmail_readiness.refresh_access_token_with_metadata",
            return_value=refresh,
        ),
        patch(
            "app.evaluation.live.recipient_gmail_readiness.load_recipient_credentials",
            return_value=MagicMock(),
        ),
        patch(
            "app.evaluation.live.delivery_mailbox_reader.build_recipient_client",
            return_value=_mock_reader()._client,
        ),
    ):
        report = run_recipient_gmail_readiness(expected_recipient="recipient@eval.test")

    assert report.ready is True
    assert report.recipient_delivery_observation_ready is True
    assert report.delivery_observation_path_ready is True
    assert report.recipient_credential_source == CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV
    assert report.credential_source_match is True


def test_recipient_readiness_fails_when_refresh_fails(single_address_env):
    with patch(
        "app.evaluation.live.recipient_gmail_readiness.refresh_access_token_with_metadata",
        side_effect=RuntimeError("invalid_grant"),
    ), patch(
        "app.evaluation.live.recipient_gmail_readiness.load_recipient_credentials",
        return_value=MagicMock(),
    ):
        report = run_recipient_gmail_readiness(expected_recipient="recipient@eval.test")

    assert report.ready is False
    assert report.recipient_token_refresh_passed is False


def test_recipient_readiness_fails_when_list_labels_401(single_address_env):
    client = MagicMock()
    client.get_profile_email.return_value = "recipient@eval.test"
    client.list_labels.side_effect = RuntimeError("Gmail API error (401)")
    refresh = TokenRefreshResult(
        access_token="access-token",
        granted_scopes=frozenset({"https://www.googleapis.com/auth/gmail.readonly"}),
    )

    with (
        patch(
            "app.evaluation.live.recipient_gmail_readiness.refresh_access_token_with_metadata",
            return_value=refresh,
        ),
        patch(
            "app.evaluation.live.recipient_gmail_readiness.load_recipient_credentials",
            return_value=MagicMock(),
        ),
        patch(
            "app.evaluation.live.delivery_mailbox_reader.build_recipient_client",
            return_value=client,
        ),
    ):
        report = run_recipient_gmail_readiness(expected_recipient="recipient@eval.test")

    assert report.ready is False
    assert report.delivery_observation_path_ready is False


def test_recipient_readiness_fails_on_mailbox_identity_mismatch(single_address_env):
    client = MagicMock()
    client.get_profile_email.return_value = "other@eval.test"
    refresh = TokenRefreshResult(
        access_token="access-token",
        granted_scopes=frozenset({"https://www.googleapis.com/auth/gmail.readonly"}),
    )

    with (
        patch(
            "app.evaluation.live.recipient_gmail_readiness.refresh_access_token_with_metadata",
            return_value=refresh,
        ),
        patch(
            "app.evaluation.live.recipient_gmail_readiness.load_recipient_credentials",
            return_value=MagicMock(),
        ),
        patch(
            "app.evaluation.live.delivery_mailbox_reader.build_recipient_client",
            return_value=client,
        ),
    ):
        report = run_recipient_gmail_readiness(expected_recipient="recipient@eval.test")

    assert report.ready is False
    assert report.recipient_mailbox_identity_match is False


def test_recipient_readiness_fails_when_scopes_missing(single_address_env):
    client = MagicMock()
    client.get_profile_email.return_value = "recipient@eval.test"
    refresh = TokenRefreshResult(access_token="access-token", granted_scopes=frozenset())

    with (
        patch(
            "app.evaluation.live.recipient_gmail_readiness.refresh_access_token_with_metadata",
            return_value=refresh,
        ),
        patch(
            "app.evaluation.live.recipient_gmail_readiness.load_recipient_credentials",
            return_value=MagicMock(),
        ),
        patch(
            "app.evaluation.live.delivery_mailbox_reader.build_recipient_client",
            return_value=client,
        ),
    ):
        report = run_recipient_gmail_readiness(expected_recipient="recipient@eval.test")

    assert report.ready is False
    assert report.recipient_required_scopes_present is False
