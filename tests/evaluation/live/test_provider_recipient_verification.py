"""Provider RFC recipient verification and execution outcome polling tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.gmail_transport import (
    _classify_sent_recipient_exclusion,
    _matches_provider_rfc_recipient_candidate,
    fetch_provider_sent_reply_object,
    observe_expected_sender_reply,
)
from app.evaluation.live.observer import LiveEvalObserver
from app.evaluation.live.pipeline_poll import poll_until_provider_execution_outcome
from app.evaluation.live.provider_recipient_verification import (
    extract_provider_execution_outcome,
    provider_execution_outcome_ready,
)
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


def test_extract_provider_execution_outcome_from_decision_record():
    observation = {
        "job": {
            "decision_records": [
                {
                    "record_type": "execution_outcome",
                    "execution_status": "succeeded",
                    "metadata": {
                        "provider_message_id": "gmail-99",
                        "adapter_recipient": "sender@eval.test",
                        "adapter_status": "executed",
                        "provider_rfc_message_id": "<provider-rfc@mail.test>",
                    },
                }
            ]
        },
        "events": [],
    }
    outcome = extract_provider_execution_outcome(observation)
    assert outcome is not None
    assert outcome.provider_message_id == "gmail-99"
    assert outcome.adapter_recipient == "sender@eval.test"
    assert outcome.provider_rfc_message_id == "<provider-rfc@mail.test>"


def test_provider_execution_outcome_ready_with_nested_persisted_metadata():
    """Regression H5-B: metadata persisted from integration_result shape."""
    observation = {
        "job": {
            "decision_records": [
                {
                    "record_type": "execution_outcome",
                    "execution_status": "succeeded",
                    "metadata": {
                        "provider_message_id": "gmail-nested-456",
                        "adapter_recipient": "sender@eval.test",
                        "adapter_status": "executed",
                        "provider_status": "success",
                        "provider_thread_id": "thread-789",
                    },
                }
            ]
        }
    }
    assert provider_execution_outcome_ready(observation) is True


def test_provider_execution_outcome_ready_requires_adapter_recipient():
    observation = {
        "job": {
            "decision_records": [
                {
                    "record_type": "execution_outcome",
                    "execution_status": "succeeded",
                    "metadata": {
                        "provider_message_id": "gmail-1",
                        "adapter_status": "executed",
                    },
                }
            ]
        }
    }
    assert provider_execution_outcome_ready(observation) is False


def test_poll_waits_for_execution_outcome_not_resolution_only():
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        if calls["n"] < 2:
            return {
                "job": {
                    "decision_records": [
                        {"record_type": "action_approval_resolution"},
                    ]
                }
            }
        return {
            "job": {
                "decision_records": [
                    {
                        "record_type": "execution_outcome",
                        "execution_status": "succeeded",
                        "metadata": {
                            "provider_message_id": "gmail-ready",
                            "adapter_recipient": "sender@eval.test",
                            "adapter_status": "executed",
                        },
                    }
                ]
            }
        }

    result = poll_until_provider_execution_outcome(fetch, timeout_seconds=5)
    assert result.observation["job"]["decision_records"][0]["record_type"] == "execution_outcome"
    assert calls["n"] == 2


def test_inbound_sent_copy_classified(live_eval_env):
    detail = {
        "from": "sender@eval.test",
        "internet_message_id": "<inbound-rfc@mail.test>",
        "label_ids": ["SENT"],
    }
    reason = _classify_sent_recipient_exclusion(
        detail,
        expected_sender="sender@eval.test",
        inbound_rfc_message_id="<inbound-rfc@mail.test>",
    )
    assert reason == "inbound_sent_copy_not_reply"


def test_sent_label_excluded_from_recipient_pass(live_eval_env):
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    detail = {
        "message_id": "sent-copy-1",
        "from": "sender@eval.test",
        "to": "sender@eval.test",
        "internet_message_id": "<inbound-rfc@mail.test>",
        "label_ids": ["SENT"],
        "internal_date_ms": now_ms,
        "in_reply_to": "<inbound-rfc@mail.test>",
    }
    assert _matches_provider_rfc_recipient_candidate(
        detail,
        provider_rfc_message_id="provider-rfc@mail.test",
        expected_recipient="recipient@eval.test",
        expected_sender="sender@eval.test",
        send_window_start=datetime.now(timezone.utc),
        window_end=datetime.now(timezone.utc),
        evaluation_run_id="run-1",
        scenario_id="TBSM01_lead_approve_reply",
        campaign_run_id=None,
        inbound_rfc_message_id="<inbound-rfc@mail.test>",
    ) is False


def test_provider_rfc_recipient_candidate_passes_all_mail(live_eval_env):
    run_id = "run-provider-rfc-1"
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    detail = {
        "message_id": "reply-1",
        "from": "recipient@eval.test",
        "to": "sender@eval.test",
        "internet_message_id": "<provider-rfc@mail.test>",
        "label_ids": ["CATEGORY_PERSONAL"],
        "internal_date_ms": now_ms,
        "in_reply_to": "<inbound-rfc@mail.test>",
    }
    assert _matches_provider_rfc_recipient_candidate(
        detail,
        provider_rfc_message_id="provider-rfc@mail.test",
        expected_recipient="recipient@eval.test",
        expected_sender="sender@eval.test",
        send_window_start=datetime.now(timezone.utc),
        window_end=datetime.now(timezone.utc),
        evaluation_run_id=run_id,
        scenario_id="TBSM01_lead_approve_reply",
        campaign_run_id=None,
        inbound_rfc_message_id="<inbound-rfc@mail.test>",
    ) is True


def test_wrong_rfc_message_id_blocks_pass(live_eval_env):
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    detail = {
        "from": "recipient@eval.test",
        "to": "sender@eval.test",
        "internet_message_id": "<other-rfc@mail.test>",
        "label_ids": ["INBOX"],
        "internal_date_ms": now_ms,
    }
    assert _matches_provider_rfc_recipient_candidate(
        detail,
        provider_rfc_message_id="provider-rfc@mail.test",
        expected_recipient="recipient@eval.test",
        expected_sender="sender@eval.test",
        send_window_start=datetime.now(timezone.utc),
        window_end=datetime.now(timezone.utc),
        evaluation_run_id="run-1",
        scenario_id="TBSM01_lead_approve_reply",
        campaign_run_id=None,
        inbound_rfc_message_id=None,
    ) is False


def test_provider_sent_requires_in_reply_to_match(live_eval_env):
    msg = {
        "message_id": "provider-inreply",
        "from": "recipient@eval.test",
        "to": "sender@eval.test",
        "internet_message_id": "<provider-rfc@mail.test>",
        "in_reply_to": "<wrong-inbound@mail.test>",
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
            provider_message_id="provider-inreply",
            expected_sender="sender@eval.test",
            expected_recipient="recipient@eval.test",
            inbound_rfc_message_id="<inbound-rfc@mail.test>",
        )
    assert result is None


def test_recipient_query_uses_provider_rfc_not_inbound(live_eval_env):
    run_id = "run-query-1"
    provider_msg = {
        "message_id": "provider-1",
        "from": "recipient@eval.test",
        "to": "sender@eval.test",
        "internet_message_id": "<provider-rfc@mail.test>",
        "in_reply_to": "<inbound-rfc@mail.test>",
        "label_ids": ["SENT"],
        "internal_date_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
    }
    reply_msg = {
        "message_id": "reply-1",
        "from": "recipient@eval.test",
        "to": "sender@eval.test",
        "internet_message_id": "<provider-rfc@mail.test>",
        "label_ids": ["INBOX"],
        "internal_date_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
        "in_reply_to": "<inbound-rfc@mail.test>",
    }
    sender_client = MagicMock()
    sender_client.list_message_ids.return_value = ["reply-1"]
    sender_client.get_message.return_value = reply_msg
    recipient_client = MagicMock()
    recipient_client.get_message.return_value = provider_msg

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
            provider_message_id="provider-1",
            inbound_rfc_message_id="<inbound-rfc@mail.test>",
        )

    assert result is not None
    first_query = sender_client.list_message_ids.call_args_list[0].kwargs["query"]
    assert "rfc822msgid:provider-rfc@mail.test" in first_query
    assert "inbound-rfc@mail.test" not in first_query


def test_inbound_sent_copy_does_not_verify_as_reply(live_eval_env):
    run_id = "run-false-positive"
    provider_msg = {
        "message_id": "provider-2",
        "from": "recipient@eval.test",
        "to": "sender@eval.test",
        "internet_message_id": "<provider-rfc@mail.test>",
        "in_reply_to": "<inbound-rfc@mail.test>",
        "label_ids": ["SENT"],
        "internal_date_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
    }
    sent_copy = {
        "message_id": "inbound-sent-copy",
        "from": "sender@eval.test",
        "to": "sender@eval.test",
        "internet_message_id": "<inbound-rfc@mail.test>",
        "label_ids": ["SENT"],
        "internal_date_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
    }
    sender_client = MagicMock()
    sender_client.list_message_ids.return_value = ["inbound-sent-copy"]
    sender_client.get_message.return_value = sent_copy
    recipient_client = MagicMock()
    recipient_client.get_message.return_value = provider_msg

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
            provider_message_id="provider-2",
            inbound_rfc_message_id="<inbound-rfc@mail.test>",
        )

    assert result is None


def test_observer_exposes_provider_outcome_poll():
    assert hasattr(LiveEvalObserver, "poll_until_provider_execution_outcome")


def test_missing_provider_metadata_not_ready():
    observation = {
        "job": {
            "decision_records": [
                {"record_type": "action_approval_resolution"},
            ]
        }
    }
    assert extract_provider_execution_outcome(observation) is None
