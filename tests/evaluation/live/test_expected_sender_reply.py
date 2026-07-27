"""Expected sender reply verification tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.evaluation.live.gmail_transport import observe_expected_sender_reply
from app.evaluation.live.subject_parser import build_subject_with_token


def test_expected_reply_found_in_recipient_sent_folder(live_eval_env, monkeypatch):
    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    run_id = "run-reply-sent-1"
    base_subject = build_subject_with_token(
        evaluation_run_id=run_id,
        scenario_id="TBSM01_lead_approve_reply",
        attempt_id=1,
        base_subject="Offert",
    )
    subject = f"Re: {base_subject}"
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    msg = {
        "message_id": "sent-reply-1",
        "subject": subject,
        "from": "recipient@eval.test",
        "to": "sender@eval.test",
        "internal_date_ms": now_ms,
    }
    sender_client = MagicMock()
    sender_client.list_message_ids.return_value = []
    recipient_client = MagicMock()
    recipient_client.list_message_ids.return_value = ["sent-reply-1"]
    recipient_client.get_message.return_value = msg

    with patch(
        "app.evaluation.live.gmail_transport.build_sender_client",
        return_value=sender_client,
    ), patch(
        "app.evaluation.live.gmail_transport.build_recipient_client",
        return_value=recipient_client,
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
    assert result.message_id == "sent-reply-1"


def test_expected_reply_found_by_provider_message_id(live_eval_env, monkeypatch):
    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    run_id = "run-reply-provider-1"
    base_subject = build_subject_with_token(
        evaluation_run_id=run_id,
        scenario_id="TBSM01_lead_approve_reply",
        attempt_id=1,
        base_subject="Offert",
    )
    subject = f"Re: {base_subject}"
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    msg = {
        "message_id": "provider-msg-99",
        "subject": subject,
        "from": "alias@eval.test",
        "to": "sender@eval.test",
        "internal_date_ms": now_ms,
    }
    recipient_client = MagicMock()
    recipient_client.get_message.return_value = msg

    with patch(
        "app.evaluation.live.gmail_transport.build_recipient_client",
        return_value=recipient_client,
    ), patch(
        "app.evaluation.live.gmail_transport.build_sender_client",
        side_effect=AssertionError("sender search should not run when provider id matches"),
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
            provider_message_id="provider-msg-99",
        )

    assert result is not None
    assert result.message_id == "provider-msg-99"
