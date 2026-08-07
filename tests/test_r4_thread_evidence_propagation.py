"""Thread evidence propagation for R4 reviewed-live reply verification."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.evaluation.live.gmail_transport import (
    ExpectedReplyEvidence,
    ProviderSentObjectEvidence,
    _reply_evidence_from_message,
    compute_reply_thread_match,
    fetch_provider_sent_reply_object,
)
from app.evaluation.profile_testbot.campaign.post_approval_execution import ReplyExecutionEvidence
from app.evaluation.profile_testbot.campaign.semi_auto_contract import ReplyVerification
from app.evaluation.profile_testbot.campaign.semi_auto_live_backend import (
    LiveSemiAutoBackend,
    _ScenarioRunContext,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_live_backend import _redact_id
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario, ProfileScenarioInput


INBOUND_RFC = "inbound-rfc@mail.test"
PROVIDER_RFC = "provider-rfc@mail.test"


def _provider_sent(**overrides) -> ProviderSentObjectEvidence:
    base = ProviderSentObjectEvidence(
        message_id="provider-msg-1",
        thread_id="thread-shared",
        rfc_message_id=PROVIDER_RFC,
        in_reply_to=None,
        references=None,
        labels=("SENT",),
        in_sent=True,
        to_recipients=("sender@eval.test",),
        from_email="recipient@eval.test",
        reply_to=None,
        subject_truncated="Re: test",
    )
    for key, value in overrides.items():
        object.__setattr__(base, key, value)
    return base


def test_reply_evidence_from_message_propagates_thread_fields():
    detail = {
        "message_id": "msg-1",
        "thread_id": "thread-9",
        "subject": "Re: token",
        "from": "recipient@eval.test",
        "internet_message_id": f"<{PROVIDER_RFC}>",
        "in_reply_to": f"<{INBOUND_RFC}>",
        "references": f"<{INBOUND_RFC}>",
        "label_ids": ["INBOX"],
        "internal_date_ms": 1,
    }
    evidence = _reply_evidence_from_message(message_id="msg-1", detail=detail)
    assert evidence.thread_id == "thread-9"
    assert evidence.rfc_message_id == PROVIDER_RFC
    assert evidence.in_reply_to == INBOUND_RFC
    assert evidence.references == f"<{INBOUND_RFC}>"


def test_compute_thread_match_in_reply_to():
    provider = _provider_sent(in_reply_to=INBOUND_RFC)
    ok, basis = compute_reply_thread_match(
        provider_sent=provider,
        inbound_rfc_message_id=INBOUND_RFC,
    )
    assert ok is True
    assert basis == "rfc_in_reply_to"


def test_compute_thread_match_references():
    provider = _provider_sent(references=f"<{INBOUND_RFC}> other@mail.test")
    ok, basis = compute_reply_thread_match(
        provider_sent=provider,
        inbound_rfc_message_id=INBOUND_RFC,
    )
    assert ok is True
    assert basis == "rfc_references"


def test_compute_thread_match_same_mailbox_gmail_thread():
    provider = _provider_sent(thread_id="thread-shared")
    ok, basis = compute_reply_thread_match(
        provider_sent=provider,
        inbound_rfc_message_id=None,
        inbound_gmail_thread_id="thread-shared",
    )
    assert ok is True
    assert basis == "gmail_same_mailbox_thread"


def test_compute_thread_match_delivered_rfc_must_match_provider():
    provider = _provider_sent(in_reply_to=INBOUND_RFC)
    delivered = ExpectedReplyEvidence(
        message_id="delivered-1",
        subject_truncated="Re",
        from_masked="r…@eval.test",
        internal_date_ms=1,
        rfc_message_id="other-rfc@mail.test",
    )
    ok, basis = compute_reply_thread_match(
        provider_sent=provider,
        inbound_rfc_message_id=INBOUND_RFC,
        delivered=delivered,
    )
    assert ok is False
    assert basis is None


def test_compute_thread_match_delivered_rfc_equal_passes():
    provider = _provider_sent(in_reply_to=INBOUND_RFC)
    delivered = ExpectedReplyEvidence(
        message_id="delivered-1",
        subject_truncated="Re",
        from_masked="r…@eval.test",
        internal_date_ms=1,
        rfc_message_id=PROVIDER_RFC,
    )
    ok, basis = compute_reply_thread_match(
        provider_sent=provider,
        inbound_rfc_message_id=INBOUND_RFC,
        delivered=delivered,
    )
    assert ok is True
    assert basis == "rfc_in_reply_to"


def test_compute_thread_match_unrelated_reply_fails():
    provider = _provider_sent(in_reply_to="other@mail.test", references="<other@mail.test>")
    ok, basis = compute_reply_thread_match(
        provider_sent=provider,
        inbound_rfc_message_id=INBOUND_RFC,
    )
    assert ok is False
    assert basis is None


def test_compute_thread_match_missing_linkage_fails():
    provider = _provider_sent()
    ok, basis = compute_reply_thread_match(
        provider_sent=provider,
        inbound_rfc_message_id=INBOUND_RFC,
    )
    assert ok is False
    assert basis is None


def test_r4_report_fields_use_thread_match_not_bool_rfc():
    verification = ReplyVerification(
        execution_intents=1,
        adapter_invocations=1,
        provider_accepted=True,
        recipient_verified=True,
        duplicate_send=False,
        reply_hash="abc",
        reply_provider_message_id="provider-msg-1",
        reply_rfc_message_id="present-but-unlinked@mail.test",
        reply_thread_id="thread-shared",
        thread_match=True,
        thread_match_basis="rfc_in_reply_to",
        reply_execution_status="succeeded",
    )
    thread_match = bool(getattr(verification, "thread_match", False))
    assert thread_match is True
    assert bool(verification.reply_rfc_message_id) is True
    assert _redact_id(verification.reply_thread_id) != _redact_id(verification.reply_rfc_message_id)


def test_thread_match_not_inferred_from_rfc_presence():
    verification = ReplyVerification(
        execution_intents=1,
        adapter_invocations=1,
        provider_accepted=True,
        recipient_verified=True,
        duplicate_send=False,
        reply_hash="abc",
        reply_provider_message_id="provider-msg-1",
        reply_rfc_message_id="present-but-unlinked@mail.test",
        thread_match=False,
        reply_execution_status="succeeded",
    )
    assert bool(verification.reply_rfc_message_id) is True
    assert verification.thread_match is False
    passed = verification.thread_match
    assert passed is False


def test_provider_sent_object_fetch_preserves_rfc_message_id(live_eval_env):
    from unittest.mock import MagicMock

    client = MagicMock()
    client.get_message.return_value = {
        "message_id": "provider-42",
        "thread_id": "thread-1",
        "from": "recipient@eval.test",
        "to": "sender@eval.test",
        "subject": "Re: test",
        "internet_message_id": f"<{PROVIDER_RFC}>",
        "in_reply_to": f"<{INBOUND_RFC}>",
        "label_ids": ["SENT"],
        "internal_date_ms": 1,
    }
    with patch(
        "app.evaluation.live.gmail_transport.build_recipient_client",
        return_value=client,
    ):
        result = fetch_provider_sent_reply_object(
            provider_message_id="provider-42",
            expected_sender="sender@eval.test",
            expected_recipient="recipient@eval.test",
            inbound_rfc_message_id=INBOUND_RFC,
        )
    assert result is not None
    assert result.rfc_message_id == PROVIDER_RFC
    assert result.in_reply_to == INBOUND_RFC


def _ptb_scenario() -> ProfileScenario:
    return ProfileScenario(
        scenario_id="PTB-DCQ-0000",
        profile_id="niklas-demo-live-eval-v1",
        profile_snapshot_hash="hash",
        family="solar",
        intent="reply",
        risk_class="low",
        input=ProfileScenarioInput(
            subject="Test",
            message_text="Hej",
            sender_name="Test",
            sender_email="sender@eval.test",
        ),
        expected_classification={},
        expected_route={},
        expected_authorization={},
        expected_send_behavior="send_after_approval",
    )


def test_verify_reply_propagates_provider_thread_evidence(live_eval_env):
    scenario = _ptb_scenario()
    backend = LiveSemiAutoBackend(
        campaign_id="camp-1",
        base_url="http://127.0.0.1:8010",
        admin_api_key="key",
        tenant_id="TENANT_LIVE_EVAL",
        sender_email="sender@eval.test",
        recipient_email="recipient@eval.test",
    )
    backend.runs["PTB-DCQ-0000"] = _ScenarioRunContext(
        evaluation_run_id="run-1",
        inbound_provider_message_id="inbound-msg",
        inbound_rfc_message_id=INBOUND_RFC,
        reply_execution=ReplyExecutionEvidence(
            reply_provider_message_id="provider-msg-1",
            reply_rfc_message_id=None,
            reply_execution_status="succeeded",
            reply_action_operation_id="op-1",
            reply_provider_outcome="executed",
        ),
    )
    observed = ExpectedReplyEvidence(
        message_id="delivered-1",
        subject_truncated="Re",
        from_masked="r…@eval.test",
        internal_date_ms=1,
        thread_id="thread-shared",
        rfc_message_id=PROVIDER_RFC,
        in_reply_to=INBOUND_RFC,
    )
    provider_object = _provider_sent(in_reply_to=INBOUND_RFC)
    with patch(
        "app.evaluation.profile_testbot.campaign.semi_auto_live_backend.observe_expected_sender_reply",
        return_value=observed,
    ), patch(
        "app.evaluation.profile_testbot.campaign.semi_auto_live_backend.fetch_provider_sent_reply_object",
        return_value=provider_object,
    ):
        reply = backend.verify_reply(
            scenario=scenario,
            approved=True,
            inbound_provider_message_id="inbound-msg",
            inbound_rfc_message_id=INBOUND_RFC,
        )
    assert reply.thread_match is True
    assert reply.thread_match_basis == "rfc_in_reply_to"
    assert reply.reply_rfc_message_id == PROVIDER_RFC
    assert reply.reply_thread_id == "thread-shared"


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
