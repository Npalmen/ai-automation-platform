"""Live Gmail read-only forensics tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.forensics.readonly import (
    assert_readonly_forensics_budget,
    install_readonly_gmail_guard,
)
from app.evaluation.live.forensics.gmail_forensics import run_live_gmail_forensics
from app.workflows.external_write_trace import _adapter_outcome_metadata


@pytest.fixture
def forensics_env(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_GMAIL_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED", "no")
    monkeypatch.setenv("LIVE_EVAL_TENANT_IDS", "TENANT_LIVE_EVAL")
    monkeypatch.setenv("LIVE_EVAL_SENDER_EMAILS", "sender@eval.test")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_EMAILS", "recipient@eval.test")
    monkeypatch.setenv("LIVE_EVAL_MAX_GMAIL_SENDS", "0")
    monkeypatch.setenv("LIVE_EVAL_MAX_GMAIL_REPLIES", "0")
    monkeypatch.setenv("LIVE_EVAL_SENDER_GMAIL_REFRESH_TOKEN", "sender-token")
    monkeypatch.setenv("LIVE_EVAL_SENDER_GMAIL_CLIENT_ID", "sender-client")
    monkeypatch.setenv("LIVE_EVAL_SENDER_GMAIL_CLIENT_SECRET", "sender-secret")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_GMAIL_REFRESH_TOKEN", "recipient-token")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_GMAIL_CLIENT_ID", "recipient-client")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_GMAIL_CLIENT_SECRET", "recipient-secret")
    from app.core.settings import get_settings
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


def test_readonly_budget_blocks_campaign_mode(forensics_env, monkeypatch):
    monkeypatch.setenv("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED", "yes")
    with pytest.raises(LiveEvalSafetyError, match="FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED"):
        assert_readonly_forensics_budget()


def test_readonly_budget_requires_zero_sends(forensics_env, monkeypatch):
    monkeypatch.setenv("LIVE_EVAL_MAX_GMAIL_SENDS", "1")
    with pytest.raises(LiveEvalSafetyError, match="LIVE_EVAL_MAX_GMAIL_SENDS=0"):
        assert_readonly_forensics_budget()


def test_forensics_blocks_gmail_send(forensics_env):
    install_readonly_gmail_guard()
    from app.integrations.google.mail_client import GoogleMailClient

    client = GoogleMailClient(
        api_url="https://gmail.googleapis.com/gmail/v1",
        access_token="token",
        user_id="me",
    )
    with pytest.raises(LiveEvalSafetyError, match="forensics blocked Gmail write"):
        client.send_message(to="a@b.com", subject="x", body="y")


def test_adapter_outcome_metadata_persists_provider_ids():
    metadata = _adapter_outcome_metadata(
        {
            "status": "executed",
            "external_id": "gmail-123",
            "payload": {"google_message_id": "gmail-123", "rfc_message_id": "<rfc@test>"},
        },
        action={"to": "sender@eval.test"},
    )
    assert metadata["provider_message_id"] == "gmail-123"
    assert metadata["provider_rfc_message_id"] == "<rfc@test>"
    assert metadata["adapter_recipient"] == "sender@eval.test"


def test_provider_message_id_from_events():
    from app.evaluation.live.runner import _provider_message_id_from_observation

    observation = {
        "job": {"decision_records": []},
        "events": [
            {"metadata": {"provider_message_id": "from-event-1"}},
        ],
    }
    assert _provider_message_id_from_observation(observation) == "from-event-1"


def test_credential_role_collision_detected(forensics_env):
    client = MagicMock()
    client.get_profile_email.return_value = "same@eval.test"
    client.list_messages_page.return_value = MagicMock(message_ids=[], truncated=False)
    client.list_message_ids.return_value = []

    with patch(
        "app.evaluation.live.forensics.gmail_forensics.build_sender_client",
        return_value=client,
    ), patch(
        "app.evaluation.live.forensics.gmail_forensics.build_recipient_client",
        return_value=client,
    ):
        report = run_live_gmail_forensics(
            evaluation_run_id="run-collision-1",
            scenario_id="TBSM01_lead_approve_reply",
        )
    assert report.credential_role_collision is True
    assert report.root_cause_classification == "H2"


def test_fetch_provider_allows_send_as_alias(forensics_env):
    from app.evaluation.live.gmail_transport import fetch_provider_sent_reply_object

    client = MagicMock()
    client.get_message.return_value = {
        "message_id": "provider-1",
        "thread_id": "t1",
        "from": "alias@eval.test",
        "to": "sender@eval.test",
        "subject": "Re: test",
        "internet_message_id": "<provider-rfc@mail.test>",
        "label_ids": ["SENT"],
        "internal_date_ms": 1,
    }
    with patch(
        "app.evaluation.live.gmail_transport.build_recipient_client",
        return_value=client,
    ):
        result = fetch_provider_sent_reply_object(
            provider_message_id="provider-1",
            expected_sender="sender@eval.test",
            expected_recipient="recipient@eval.test",
        )
    assert result is not None
    assert result.in_sent is True


def test_forensics_h5_when_provider_message_id_missing(forensics_env):
    sender = MagicMock()
    sender.get_profile_email.return_value = "sender@eval.test"
    sender.list_messages_page.return_value = MagicMock(message_ids=[], truncated=False)
    sender.list_message_ids.return_value = []

    recipient = MagicMock()
    recipient.get_profile_email.return_value = "recipient@eval.test"
    recipient.list_messages_page.return_value = MagicMock(message_ids=[], truncated=False)
    recipient.list_message_ids.return_value = []

    with patch(
        "app.evaluation.live.forensics.gmail_forensics.build_sender_client",
        return_value=sender,
    ), patch(
        "app.evaluation.live.forensics.gmail_forensics.build_recipient_client",
        return_value=recipient,
    ):
        report = run_live_gmail_forensics(
            evaluation_run_id="run-h5-1",
            scenario_id="TBSM01_lead_approve_reply",
        )
    assert report.root_cause_classification == "H5"
    assert "provider_metadata_not_persisted" in report.root_cause_subcodes


def test_forensics_recipient_search_uses_in_anywhere(forensics_env):
    sender = MagicMock()
    sender.get_profile_email.return_value = "sender@eval.test"
    sender.list_messages_page.return_value = MagicMock(message_ids=[], truncated=False)
    sender.list_message_ids.return_value = []

    recipient = MagicMock()
    recipient.get_profile_email.return_value = "recipient@eval.test"
    recipient.list_messages_page.return_value = MagicMock(message_ids=[], truncated=False)
    recipient.list_message_ids.return_value = []
    recipient.get_message.return_value = {
        "message_id": "provider-99",
        "thread_id": "t1",
        "from": "recipient@eval.test",
        "to": "sender@eval.test",
        "subject": "Re: test",
        "internet_message_id": "<provider-rfc@mail.test>",
        "label_ids": ["SENT"],
        "internal_date_ms": 1,
    }

    with patch(
        "app.evaluation.live.forensics.gmail_forensics.build_sender_client",
        return_value=sender,
    ), patch(
        "app.evaluation.live.forensics.gmail_forensics.build_recipient_client",
        return_value=recipient,
    ):
        report = run_live_gmail_forensics(
            evaluation_run_id="run-search-1",
            scenario_id="TBSM01_lead_approve_reply",
            provider_message_id="provider-99",
            inbound_rfc_message_id="<inbound-rfc@mail.test>",
        )
    assert report.recipient_searches
    assert all("in:anywhere" in row.query for row in report.recipient_searches)


def test_forensics_h4_provider_sent_recipient_not_delivered(forensics_env):
    sender = MagicMock()
    sender.get_profile_email.return_value = "sender@eval.test"
    sender.list_messages_page.return_value = MagicMock(message_ids=[], truncated=False)
    sender.list_message_ids.return_value = []

    recipient = MagicMock()
    recipient.get_profile_email.return_value = "recipient@eval.test"
    recipient.list_messages_page.return_value = MagicMock(message_ids=[], truncated=False)
    recipient.list_message_ids.return_value = []
    recipient.get_message.return_value = {
        "message_id": "provider-h4",
        "thread_id": "t1",
        "from": "recipient@eval.test",
        "to": "sender@eval.test",
        "subject": "Re: test",
        "internet_message_id": "<provider-rfc@mail.test>",
        "label_ids": ["SENT"],
        "internal_date_ms": 1,
    }

    with patch(
        "app.evaluation.live.forensics.gmail_forensics.build_sender_client",
        return_value=sender,
    ), patch(
        "app.evaluation.live.forensics.gmail_forensics.build_recipient_client",
        return_value=recipient,
    ):
        report = run_live_gmail_forensics(
            evaluation_run_id="run-h4-1",
            scenario_id="TBSM01_lead_approve_reply",
            provider_message_id="provider-h4",
            adapter_recipient="sender@eval.test",
        )
    assert report.provider_sent_status == "provider_sent_object_verified"
    assert report.root_cause_classification == "H4"
    assert "provider_sent_recipient_not_delivered" in report.root_cause_subcodes


def test_forensics_mailbox_identities_verified_separately(forensics_env):
    sender = MagicMock()
    sender.get_profile_email.return_value = "sender@eval.test"
    sender.list_messages_page.return_value = MagicMock(message_ids=[], truncated=False)
    sender.list_message_ids.return_value = []

    recipient = MagicMock()
    recipient.get_profile_email.return_value = "recipient@eval.test"
    recipient.list_messages_page.return_value = MagicMock(message_ids=[], truncated=False)
    recipient.list_message_ids.return_value = []

    with patch(
        "app.evaluation.live.forensics.gmail_forensics.build_sender_client",
        return_value=sender,
    ), patch(
        "app.evaluation.live.forensics.gmail_forensics.build_recipient_client",
        return_value=recipient,
    ):
        report = run_live_gmail_forensics(
            evaluation_run_id="run-ident-1",
            scenario_id="TBSM01_lead_approve_reply",
        )
    assert report.sender_identity.allowlist_match is True
    assert report.recipient_identity.allowlist_match is True
    assert report.credential_role_collision is False
    sender.get_profile_email.assert_called()
    recipient.get_profile_email.assert_called()
