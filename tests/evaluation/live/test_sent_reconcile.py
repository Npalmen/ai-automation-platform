"""Sent reconciliation and send-budget tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.gmail_transport import reconcile_sent_message
from app.evaluation.live.journal import RunCheckpoint, assert_journal_send_budget
from app.evaluation.live.safety import validate_config_readiness
from app.evaluation.live.subject_parser import build_subject_with_token


def test_send_budget_config_validation(live_eval_env, monkeypatch):
    monkeypatch.setenv("LIVE_EVAL_MAX_GMAIL_SENDS", "2")
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    issues = validate_config_readiness()
    assert any("GMAIL_SENDS" in issue for issue in issues)


def test_journal_send_budget_blocks_second_send(live_eval_env):
    cp = RunCheckpoint(
        evaluation_run_id="run-budget",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        tenant_id="TENANT_LIVE_EVAL",
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        config_hash="x",
        send_window_start=datetime.now(timezone.utc),
        sender_account_fingerprint="a",
        recipient_account_fingerprint="b",
        last_state="sent",
        send_succeeded=True,
        sender_gmail_message_id="msg-1",
    )
    with pytest.raises(LiveEvalSafetyError, match="send_budget_exhausted"):
        assert_journal_send_budget(cp)


def test_reconcile_zero_candidates_returns_none(live_eval_env, monkeypatch):
    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    client = MagicMock()
    client.list_message_ids.return_value = []
    with patch("app.evaluation.live.gmail_transport.build_sender_client", return_value=client):
        result = reconcile_sent_message(
            evaluation_run_id="run-reconcile-0",
            scenario_id="S01_lead_laddbox_quality",
            attempt_id=1,
            expected_sender="sender@eval.test",
            expected_recipient="recipient@eval.test",
            send_window_start=datetime.now(timezone.utc),
        )
    assert result is None


def test_reconcile_one_candidate_resolves(live_eval_env, monkeypatch):
    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    run_id = "run-reconcile-1"
    subject = build_subject_with_token(
        evaluation_run_id=run_id,
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        base_subject="Test",
    )
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    msg = {
        "message_id": "sent-1",
        "thread_id": "t1",
        "subject": subject,
        "from": "sender@eval.test",
        "to": "recipient@eval.test",
        "internal_date_ms": now_ms,
        "internet_message_id": "<abc@mail>",
    }
    client = MagicMock()
    client.list_message_ids.return_value = ["sent-1"]
    client.get_message.return_value = msg
    with patch("app.evaluation.live.gmail_transport.build_sender_client", return_value=client):
        result = reconcile_sent_message(
            evaluation_run_id=run_id,
            scenario_id="S01_lead_laddbox_quality",
            attempt_id=1,
            expected_sender="sender@eval.test",
            expected_recipient="recipient@eval.test",
            send_window_start=datetime.now(timezone.utc),
        )
    assert result is not None
    assert result.sender_gmail_message_id == "sent-1"
    assert result.reconciled is True


def test_reconcile_wrong_recipient_rejected(live_eval_env, monkeypatch):
    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    run_id = "run-reconcile-bad"
    subject = build_subject_with_token(
        evaluation_run_id=run_id,
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        base_subject="Test",
    )
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    msg = {
        "message_id": "sent-1",
        "subject": subject,
        "from": "sender@eval.test",
        "to": "wrong@eval.test",
        "internal_date_ms": now_ms,
    }
    client = MagicMock()
    client.list_message_ids.return_value = ["sent-1"]
    client.get_message.return_value = msg
    with patch("app.evaluation.live.gmail_transport.build_sender_client", return_value=client):
        result = reconcile_sent_message(
            evaluation_run_id=run_id,
            scenario_id="S01_lead_laddbox_quality",
            attempt_id=1,
            expected_sender="sender@eval.test",
            expected_recipient="recipient@eval.test",
            send_window_start=datetime.now(timezone.utc),
        )
    assert result is None


def test_reconcile_multiple_candidates_fails(live_eval_env, monkeypatch):
    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    run_id = "run-reconcile-dup"
    subject = build_subject_with_token(
        evaluation_run_id=run_id,
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        base_subject="Test",
    )
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    msg = {
        "message_id": "sent-1",
        "thread_id": "t1",
        "subject": subject,
        "from": "sender@eval.test",
        "to": "recipient@eval.test",
        "internal_date_ms": now_ms,
    }
    client = MagicMock()
    client.list_message_ids.return_value = ["sent-1", "sent-2"]
    client.get_message.return_value = msg
    with patch("app.evaluation.live.gmail_transport.build_sender_client", return_value=client):
        with pytest.raises(LiveEvalSafetyError, match="multiple sent matches"):
            reconcile_sent_message(
                evaluation_run_id=run_id,
                scenario_id="S01_lead_laddbox_quality",
                attempt_id=1,
                expected_sender="sender@eval.test",
                expected_recipient="recipient@eval.test",
                send_window_start=datetime.now(timezone.utc),
            )
