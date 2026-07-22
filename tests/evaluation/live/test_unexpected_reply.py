"""Unexpected sender reply detection tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.gmail_transport import observe_unexpected_sender_reply
from app.evaluation.live.subject_parser import build_subject_with_token


def test_no_unexpected_reply_when_inbox_empty(live_eval_env, monkeypatch):
    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    client = MagicMock()
    client.list_message_ids.return_value = []
    with patch("app.evaluation.live.gmail_transport.build_sender_client", return_value=client):
        result = observe_unexpected_sender_reply(
            evaluation_run_id="run-reply-1",
            scenario_id="S01_lead_laddbox_quality",
            attempt_id=1,
            expected_recipient="recipient@eval.test",
            send_window_start=datetime.now(timezone.utc),
        )
    assert result is None


def test_unexpected_reply_detected_with_full_token(live_eval_env, monkeypatch):
    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    run_id = "run-reply-2"
    subject = build_subject_with_token(
        evaluation_run_id=run_id,
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        base_subject="Re: test",
    )
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    msg = {
        "message_id": "reply-1",
        "subject": subject,
        "from": "recipient@eval.test",
        "internal_date_ms": now_ms,
    }
    client = MagicMock()
    client.list_message_ids.return_value = ["reply-1"]
    client.get_message.return_value = msg
    with patch("app.evaluation.live.gmail_transport.build_sender_client", return_value=client):
        result = observe_unexpected_sender_reply(
            evaluation_run_id=run_id,
            scenario_id="S01_lead_laddbox_quality",
            attempt_id=1,
            expected_recipient="recipient@eval.test",
            send_window_start=datetime.now(timezone.utc),
        )
    assert result is not None
    assert result.message_id == "reply-1"


def test_multiple_unexpected_replies_correlation_failure(live_eval_env, monkeypatch):
    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    run_id = "run-reply-3"
    subject = build_subject_with_token(
        evaluation_run_id=run_id,
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        base_subject="Re",
    )
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    msg = {
        "subject": subject,
        "from": "recipient@eval.test",
        "internal_date_ms": now_ms,
    }
    client = MagicMock()
    client.list_message_ids.return_value = ["r1", "r2"]
    client.get_message.return_value = msg
    with patch("app.evaluation.live.gmail_transport.build_sender_client", return_value=client):
        with pytest.raises(LiveEvalSafetyError, match="correlation_failure"):
            observe_unexpected_sender_reply(
                evaluation_run_id=run_id,
                scenario_id="S01_lead_laddbox_quality",
                attempt_id=1,
                expected_recipient="recipient@eval.test",
                send_window_start=datetime.now(timezone.utc),
            )
