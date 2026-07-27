"""Gmail recipient verification regression tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.gmail_transport import (
    assert_live_reply_recipient_allowed,
    fetch_provider_sent_reply_object,
    is_synthetic_live_eval_recipient,
    observe_expected_sender_reply,
)
from app.evaluation.live.redaction import redact_sensitive
from app.evaluation.live.subject_parser import build_subject_with_token


@pytest.fixture
def live_eval_env(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    monkeypatch.setenv("LIVE_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_GMAIL_EVAL_ALLOWED", "yes")
    monkeypatch.setenv("LIVE_EVAL_SENDER_GMAIL_REFRESH_TOKEN", "sender-token")
    monkeypatch.setenv("LIVE_EVAL_SENDER_GMAIL_CLIENT_ID", "sender-client")
    monkeypatch.setenv("LIVE_EVAL_SENDER_GMAIL_CLIENT_SECRET", "sender-secret")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_GMAIL_REFRESH_TOKEN", "recipient-token")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_GMAIL_CLIENT_ID", "recipient-client")
    monkeypatch.setenv("LIVE_EVAL_RECIPIENT_GMAIL_CLIENT_SECRET", "recipient-secret")


def test_provider_object_fetched_by_exact_message_id(live_eval_env):
    msg = {
        "message_id": "provider-42",
        "thread_id": "thread-1",
        "from": "recipient@eval.test",
        "to": "sender@eval.test",
        "subject": "Re: test",
        "internet_message_id": "<provider-rfc@mail.test>",
        "label_ids": ["SENT"],
        "internal_date_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
    }
    client = MagicMock()
    client.get_message.return_value = msg

    with patch(
        "app.evaluation.live.gmail_transport.build_recipient_client",
        return_value=client,
    ):
        result = fetch_provider_sent_reply_object(
            provider_message_id="provider-42",
            expected_sender="sender@eval.test",
            expected_recipient="recipient@eval.test",
        )

    assert result is not None
    assert result.message_id == "provider-42"
    assert result.rfc_message_id == "provider-rfc@mail.test"
    client.get_message.assert_called_once_with("provider-42")


def test_rfc_message_id_normalized_from_angle_brackets():
    from app.evaluation.live.gmail_transport import _normalize_rfc_message_id

    assert _normalize_rfc_message_id("<abc@mail.test>") == "abc@mail.test"


def test_recipient_search_uses_rfc822msgid_query(live_eval_env):
    run_id = "run-rfc-1"
    sender_client = MagicMock()
    sender_client.list_message_ids.return_value = []
    recipient_client = MagicMock()
    recipient_client.get_message.return_value = {
        "message_id": "provider-1",
        "from": "recipient@eval.test",
        "to": "sender@eval.test",
        "subject": "Re: test",
        "internet_message_id": "<provider-rfc@mail.test>",
        "label_ids": ["SENT"],
        "internal_date_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
    }

    with patch(
        "app.evaluation.live.gmail_transport.build_sender_client",
        return_value=sender_client,
    ), patch(
        "app.evaluation.live.gmail_transport.build_recipient_client",
        return_value=recipient_client,
    ):
        observe_expected_sender_reply(
            evaluation_run_id=run_id,
            scenario_id="TBSM01_lead_approve_reply",
            attempt_id=1,
            expected_recipient="recipient@eval.test",
            expected_sender="sender@eval.test",
            send_window_start=datetime.now(timezone.utc),
            timeout_seconds=0.1,
            poll_interval_seconds=0.01,
            provider_message_id="provider-1",
        )

    first_query = sender_client.list_message_ids.call_args_list[0].kwargs["query"]
    assert "rfc822msgid:provider-rfc@mail.test" in first_query
    assert "in:anywhere" in first_query


def test_recipient_search_uses_in_anywhere(live_eval_env):
    run_id = "run-anywhere-1"
    base_subject = build_subject_with_token(
        evaluation_run_id=run_id,
        scenario_id="TBSM01_lead_approve_reply",
        attempt_id=1,
        base_subject="Offert",
    )
    sender_client = MagicMock()
    sender_client.list_message_ids.return_value = ["all-mail-1"]
    sender_client.get_message.return_value = {
        "message_id": "all-mail-1",
        "subject": f"Re: {base_subject}",
        "from": "recipient@eval.test",
        "to": "sender@eval.test",
        "label_ids": ["CATEGORY_PERSONAL"],
        "internal_date_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
    }

    with patch(
        "app.evaluation.live.gmail_transport.build_sender_client",
        return_value=sender_client,
    ), patch(
        "app.evaluation.live.gmail_transport.build_recipient_client",
        side_effect=LiveEvalSafetyError("missing recipient creds"),
    ):
        observe_expected_sender_reply(
            evaluation_run_id=run_id,
            scenario_id="TBSM01_lead_approve_reply",
            attempt_id=1,
            expected_recipient="recipient@eval.test",
            expected_sender="sender@eval.test",
            send_window_start=datetime.now(timezone.utc),
            timeout_seconds=0.1,
            poll_interval_seconds=0.01,
        )

    assert any(
        "in:anywhere" in call.kwargs["query"]
        for call in sender_client.list_message_ids.call_args_list
    )


def test_spam_result_can_verify(live_eval_env):
    run_id = "run-spam-1"
    base_subject = build_subject_with_token(
        evaluation_run_id=run_id,
        scenario_id="TBSM01_lead_approve_reply",
        attempt_id=1,
        base_subject="Offert",
    )
    msg = {
        "message_id": "spam-reply-1",
        "subject": f"Re: {base_subject}",
        "from": "recipient@eval.test",
        "to": "sender@eval.test",
        "label_ids": ["SPAM"],
        "internal_date_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
    }
    sender_client = MagicMock()
    sender_client.list_message_ids.return_value = ["spam-reply-1"]
    sender_client.get_message.return_value = msg

    with patch(
        "app.evaluation.live.gmail_transport.build_sender_client",
        return_value=sender_client,
    ), patch(
        "app.evaluation.live.gmail_transport.build_recipient_client",
        side_effect=LiveEvalSafetyError("missing recipient creds"),
    ):
        result = observe_expected_sender_reply(
            evaluation_run_id=run_id,
            scenario_id="TBSM01_lead_approve_reply",
            attempt_id=1,
            expected_recipient="recipient@eval.test",
            expected_sender="sender@eval.test",
            send_window_start=datetime.now(timezone.utc),
            timeout_seconds=0.1,
            poll_interval_seconds=0.01,
        )

    assert result is not None
    assert result.placement == "recipient_verified_in_spam"


def test_wrong_mailbox_cannot_pass(live_eval_env):
    sender_client = MagicMock()
    sender_client.list_message_ids.return_value = ["wrong-1"]
    sender_client.get_message.return_value = {
        "message_id": "wrong-1",
        "subject": "Re: unrelated",
        "from": "other@eval.test",
        "to": "sender@eval.test",
        "label_ids": ["INBOX"],
        "internal_date_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
    }

    with patch(
        "app.evaluation.live.gmail_transport.build_sender_client",
        return_value=sender_client,
    ), patch(
        "app.evaluation.live.gmail_transport.build_recipient_client",
        side_effect=LiveEvalSafetyError("missing recipient creds"),
    ):
        result = observe_expected_sender_reply(
            evaluation_run_id="run-wrong-mailbox",
            scenario_id="TBSM01_lead_approve_reply",
            attempt_id=1,
            expected_recipient="recipient@eval.test",
            expected_sender="sender@eval.test",
            send_window_start=datetime.now(timezone.utc),
            timeout_seconds=0.1,
            poll_interval_seconds=0.01,
        )

    assert result is None


def test_wrong_recipient_cannot_pass(live_eval_env):
    msg = {
        "message_id": "provider-wrong-to",
        "from": "recipient@eval.test",
        "to": "other@eval.test",
        "subject": "Re: test",
        "internet_message_id": "<provider-rfc@mail.test>",
        "label_ids": ["SENT"],
        "internal_date_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
    }
    recipient_client = MagicMock()
    recipient_client.get_message.return_value = msg

    with patch(
        "app.evaluation.live.gmail_transport.build_recipient_client",
        return_value=recipient_client,
    ):
        result = fetch_provider_sent_reply_object(
            provider_message_id="provider-wrong-to",
            expected_sender="sender@eval.test",
            expected_recipient="recipient@eval.test",
        )

    assert result is None


def test_synthetic_fixture_address_blocked():
    assert is_synthetic_live_eval_recipient("testbot-anna@eval.test") is True
    with pytest.raises(LiveEvalSafetyError, match="synthetic fixture recipient"):
        assert_live_reply_recipient_allowed(
            recipient_email="testbot-anna@eval.test",
            expected_sender="sender@eval.test",
            fixture_sender_email="testbot-anna@eval.test",
        )


def test_provider_accepted_without_recipient_is_not_verified():
    from app.evaluation.live.campaign.reply_metrics import build_scenario_reply_metrics

    metrics = build_scenario_reply_metrics(
        expected_reply=True,
        observation={
            "events": [{"category": "app_gmail_reply", "outcome": "succeeded", "operation_key": "op-1"}],
            "job": {
                "decision_records": [
                    {"record_type": "execution_intent"},
                    {"record_type": "execution_outcome", "execution_status": "succeeded"},
                ]
            },
        },
        recipient_verified=False,
        unauthorized=False,
    )
    assert metrics.provider_accepted_count == 1
    assert metrics.recipient_verified_reply_count == 0


def test_provider_sent_object_reported_separately(live_eval_env):
    msg = {
        "message_id": "provider-sent-1",
        "thread_id": "thread-sent",
        "from": "recipient@eval.test",
        "to": "sender@eval.test",
        "subject": "Re: test",
        "internet_message_id": "<provider-rfc@mail.test>",
        "label_ids": ["SENT"],
        "internal_date_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
    }
    client = MagicMock()
    client.get_message.return_value = msg

    with patch(
        "app.evaluation.live.gmail_transport.build_recipient_client",
        return_value=client,
    ):
        result = fetch_provider_sent_reply_object(
            provider_message_id="provider-sent-1",
            expected_sender="sender@eval.test",
            expected_recipient="recipient@eval.test",
        )

    assert result is not None
    assert result.in_sent is True


def test_recipient_verified_outside_inbox_counts(live_eval_env):
    run_id = "run-all-mail-1"
    base_subject = build_subject_with_token(
        evaluation_run_id=run_id,
        scenario_id="TBSM01_lead_approve_reply",
        attempt_id=1,
        base_subject="Offert",
    )
    msg = {
        "message_id": "all-mail-1",
        "subject": f"Re: {base_subject}",
        "from": "recipient@eval.test",
        "to": "sender@eval.test",
        "label_ids": ["CATEGORY_PERSONAL"],
        "internal_date_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
    }
    sender_client = MagicMock()
    sender_client.list_message_ids.return_value = ["all-mail-1"]
    sender_client.get_message.return_value = msg

    with patch(
        "app.evaluation.live.gmail_transport.build_sender_client",
        return_value=sender_client,
    ), patch(
        "app.evaluation.live.gmail_transport.build_recipient_client",
        side_effect=LiveEvalSafetyError("missing recipient creds"),
    ):
        result = observe_expected_sender_reply(
            evaluation_run_id=run_id,
            scenario_id="TBSM01_lead_approve_reply",
            attempt_id=1,
            expected_recipient="recipient@eval.test",
            expected_sender="sender@eval.test",
            send_window_start=datetime.now(timezone.utc),
            timeout_seconds=0.1,
            poll_interval_seconds=0.01,
        )

    assert result is not None
    assert result.placement == "recipient_verified_in_all_mail"


def test_polling_does_not_resend(live_eval_env):
    sender_client = MagicMock()
    sender_client.list_message_ids.return_value = []

    with patch(
        "app.evaluation.live.gmail_transport.build_sender_client",
        return_value=sender_client,
    ), patch(
        "app.evaluation.live.gmail_transport.build_recipient_client",
        side_effect=LiveEvalSafetyError("missing recipient creds"),
    ), patch("app.evaluation.live.gmail_transport.send_scenario_email") as send_mock:
        observe_expected_sender_reply(
            evaluation_run_id="run-no-resend",
            scenario_id="TBSM01_lead_approve_reply",
            attempt_id=1,
            expected_recipient="recipient@eval.test",
            expected_sender="sender@eval.test",
            send_window_start=datetime.now(timezone.utc),
            timeout_seconds=0.1,
            poll_interval_seconds=0.01,
        )
        send_mock.assert_not_called()


def test_run_and_scenario_id_must_match(live_eval_env):
    run_id = "run-match-1"
    other_run = "run-other-9"
    base_subject = build_subject_with_token(
        evaluation_run_id=other_run,
        scenario_id="TBSM01_lead_approve_reply",
        attempt_id=1,
        base_subject="Offert",
    )
    msg = {
        "message_id": "historical-1",
        "subject": f"Re: {base_subject}",
        "from": "recipient@eval.test",
        "to": "sender@eval.test",
        "label_ids": ["INBOX"],
        "internal_date_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
    }
    sender_client = MagicMock()
    sender_client.list_message_ids.return_value = ["historical-1"]
    sender_client.get_message.return_value = msg

    with patch(
        "app.evaluation.live.gmail_transport.build_sender_client",
        return_value=sender_client,
    ), patch(
        "app.evaluation.live.gmail_transport.build_recipient_client",
        side_effect=LiveEvalSafetyError("missing recipient creds"),
    ):
        result = observe_expected_sender_reply(
            evaluation_run_id=run_id,
            scenario_id="TBSM01_lead_approve_reply",
            attempt_id=1,
            expected_recipient="recipient@eval.test",
            expected_sender="sender@eval.test",
            send_window_start=datetime.now(timezone.utc),
            timeout_seconds=0.1,
            poll_interval_seconds=0.01,
        )

    assert result is None


def test_oauth_scope_gap_fails_closed_readiness(monkeypatch):
    monkeypatch.delenv("LIVE_EVAL_SENDER_GMAIL_REFRESH_TOKEN", raising=False)
    from app.evaluation.live.gmail_transport import run_sender_readiness_read_only

    report = run_sender_readiness_read_only(
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
    )
    assert report.ready is False


def test_redaction_clean():
    payload = {
        "provider_message_id": "abc123",
        "recipient_email": "sender@eval.test",
        "refresh_token": "secret-token",
    }
    redacted = redact_sensitive(payload)
    assert redacted["provider_message_id"] == "abc123"
    assert "secret-token" not in str(redacted)
