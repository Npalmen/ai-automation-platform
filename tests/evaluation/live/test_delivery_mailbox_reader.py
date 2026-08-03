"""Tests for delivery mailbox credential resolver and read-only reader parity."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.delivery_mailbox_reader import (
    CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV,
    CREDENTIAL_SOURCE_TENANT_GOOGLE_MAIL,
    DeliveryMailboxReaderResolution,
    GoogleMailClientDeliveryReader,
    is_r3_frozen_live_eval_run,
    probe_orphan_delivery_observation,
    probe_delivery_reader_read_only,
    resolve_delivery_mailbox_reader,
    resolve_r3_recipient_delivery_reader,
)
from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.evaluation.profile_testbot.qualification.coworker_r3_registration_contract import (
    R3_FROZEN_EXECUTION_MODE,
)
from app.integrations.google.mail_client import GmailMessageListResult
from app.repositories.postgres.live_eval_models import LiveEvalRunRow


def _r3_row(**overrides) -> LiveEvalRunRow:
    now = datetime.now(timezone.utc)
    base = LiveEvalRunRow(
        evaluation_run_id="run-r3",
        tenant_id=LIVE_EVAL_TENANT_ID,
        scenario_id="PTB-DCQ-0000",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode=R3_FROZEN_EXECUTION_MODE,
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        status="registered",
        created_by="test",
        created_at=now,
        expires_at=now + timedelta(hours=2),
        config_hash="abc",
    )
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def _normal_row() -> LiveEvalRunRow:
    now = datetime.now(timezone.utc)
    return LiveEvalRunRow(
        evaluation_run_id="run-normal",
        tenant_id=LIVE_EVAL_TENANT_ID,
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        status="registered",
        created_by="test",
        created_at=now,
        expires_at=now + timedelta(hours=2),
        config_hash="abc",
    )


def _reader_client():
    client = MagicMock()
    client.list_labels.return_value = [{"id": "INBOX", "name": "INBOX"}]
    client.list_messages_page.return_value = GmailMessageListResult(
        message_ids=[], truncated=False
    )
    client.get_profile_email.return_value = "recipient@eval.test"
    return GoogleMailClientDeliveryReader(client)


def test_is_r3_frozen_live_eval_run():
    assert is_r3_frozen_live_eval_run(_r3_row()) is True
    assert is_r3_frozen_live_eval_run(_normal_row()) is False


def test_r3_resolver_uses_live_eval_recipient_env(single_address_env):
    with patch(
        "app.evaluation.live.delivery_mailbox_reader.build_recipient_client",
        return_value=_reader_client()._client,
    ), patch(
        "app.evaluation.live.delivery_mailbox_reader.load_recipient_credentials",
        return_value=MagicMock(),
    ):
        resolution = resolve_r3_recipient_delivery_reader(
            expected_recipient="recipient@eval.test"
        )
    assert resolution.credential_source == CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV
    assert resolution.ready is True


def test_r3_observer_does_not_use_tenant_integration(db, single_address_env):
    row = _r3_row()
    with patch(
        "app.evaluation.live.delivery_mailbox_reader.build_recipient_client",
        return_value=_reader_client()._client,
    ), patch(
        "app.evaluation.live.delivery_mailbox_reader.load_recipient_credentials",
        return_value=MagicMock(),
    ), patch(
        "app.evaluation.live.delivery_mailbox_reader.get_integration_connection_config",
    ) as tenant_cfg:
        resolution = resolve_delivery_mailbox_reader(db=db, row=row)
    tenant_cfg.assert_not_called()
    assert resolution.credential_source == CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV


def test_valid_eval_token_broken_tenant_r3_passes(db, single_address_env):
    row = _r3_row()
    with patch(
        "app.evaluation.live.delivery_mailbox_reader.build_recipient_client",
        return_value=_reader_client()._client,
    ), patch(
        "app.evaluation.live.delivery_mailbox_reader.load_recipient_credentials",
        return_value=MagicMock(),
    ), patch(
        "app.evaluation.live.delivery_mailbox_reader.get_integration_adapter",
        side_effect=RuntimeError("tenant 401"),
    ):
        resolution = resolve_delivery_mailbox_reader(db=db, row=row)
    assert resolution.ready is True


def test_broken_eval_token_valid_tenant_r3_blocked(db, single_address_env):
    row = _r3_row()
    adapter = MagicMock()
    adapter.execute_action.return_value = {"labels": [{"id": "L1", "name": "krowolf-live-eval"}]}
    adapter.client.list_messages_page.return_value = GmailMessageListResult(
        message_ids=[], truncated=False
    )
    with patch(
        "app.evaluation.live.delivery_mailbox_reader.load_recipient_credentials",
        side_effect=Exception("invalid_grant"),
    ), patch(
        "app.evaluation.live.delivery_mailbox_reader.get_integration_connection_config",
        return_value={},
    ), patch(
        "app.evaluation.live.delivery_mailbox_reader.get_integration_adapter",
        return_value=adapter,
    ):
        resolution = resolve_delivery_mailbox_reader(db=db, row=row)
    assert resolution.ready is False
    assert resolution.credential_source == CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV


def test_normal_flow_uses_tenant_google_mail(db, single_address_env):
    row = _normal_row()
    adapter = MagicMock()
    adapter.execute_action.side_effect = lambda action, payload: (
        {"labels": [{"id": "L1", "name": "krowolf-live-eval"}]}
        if action == "list_labels"
        else {"email_address": "recipient@eval.test"}
        if action == "get_profile"
        else {"message": payload}
    )
    adapter.client.list_messages_page.return_value = GmailMessageListResult(
        message_ids=[], truncated=False
    )
    with patch(
        "app.evaluation.live.delivery_mailbox_reader.get_integration_connection_config",
        return_value={},
    ), patch(
        "app.evaluation.live.delivery_mailbox_reader.get_integration_adapter",
        return_value=adapter,
    ):
        resolution = resolve_delivery_mailbox_reader(db=db, row=row)
    assert resolution.credential_source == CREDENTIAL_SOURCE_TENANT_GOOGLE_MAIL
    assert resolution.ready is True


def test_readiness_and_observation_share_resolver(single_address_env):
    with patch(
        "app.evaluation.live.delivery_mailbox_reader.build_recipient_client",
        return_value=_reader_client()._client,
    ), patch(
        "app.evaluation.live.delivery_mailbox_reader.load_recipient_credentials",
        return_value=MagicMock(),
    ):
        readiness = resolve_r3_recipient_delivery_reader(
            expected_recipient="recipient@eval.test"
        )
        observation = resolve_r3_recipient_delivery_reader(
            expected_recipient="recipient@eval.test"
        )
    assert readiness.credential_source == observation.credential_source


def test_probe_fails_when_list_labels_401(single_address_env):
    client = MagicMock()
    client.list_labels.side_effect = RuntimeError("401")
    ok, blockers = probe_delivery_reader_read_only(GoogleMailClientDeliveryReader(client))
    assert ok is False
    assert blockers


def test_probe_fails_when_read_query_401(single_address_env):
    client = MagicMock()
    client.list_labels.return_value = [{"id": "INBOX", "name": "INBOX"}]
    client.list_messages_page.side_effect = RuntimeError("401")
    ok, blockers = probe_delivery_reader_read_only(GoogleMailClientDeliveryReader(client))
    assert ok is False


def test_mailbox_identity_mismatch_blocks_r3(single_address_env):
    client = MagicMock()
    client.get_profile_email.return_value = "other@eval.test"
    with patch(
        "app.evaluation.live.delivery_mailbox_reader.build_recipient_client",
        return_value=client,
    ), patch(
        "app.evaluation.live.delivery_mailbox_reader.load_recipient_credentials",
        return_value=MagicMock(),
    ):
        resolution = resolve_r3_recipient_delivery_reader(
            expected_recipient="recipient@eval.test"
        )
    assert resolution.ready is False
    assert any("match" in item for item in resolution.blockers)


def test_credential_source_mismatch_fails_readiness(db, single_address_env):
    from app.evaluation.live.recipient_gmail_readiness import run_recipient_gmail_readiness
    from app.integrations.google.mail_client import TokenRefreshResult

    row = _r3_row()
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
            return_value=_reader_client()._client,
        ),
        patch(
            "app.evaluation.live.recipient_gmail_readiness.resolve_delivery_mailbox_reader",
            return_value=DeliveryMailboxReaderResolution(
                credential_source=CREDENTIAL_SOURCE_TENANT_GOOGLE_MAIL,
                source_allowed=True,
                source_matches_readiness=False,
                blockers=[],
                reader=_reader_client(),
            ),
        ),
    ):
        report = run_recipient_gmail_readiness(
            expected_recipient="recipient@eval.test",
            db=db,
            row=row,
        )
    assert report.ready is False
    assert report.credential_source_match is False


def test_orphan_probe_classification_not_approved_reply(db, single_address_env):
    from app.evaluation.live.subject_parser import build_subject_with_token

    row = _r3_row(evaluation_run_id="05839824-1fb1-4e98-b8e1-b8025df5db3d")
    subject = build_subject_with_token(
        evaluation_run_id=row.evaluation_run_id,
        scenario_id=row.scenario_id,
        attempt_id=row.attempt_id,
        base_subject="Offert",
    )
    msg = {
        "message_id": "m-orphan",
        "thread_id": "t1",
        "from": "sender@eval.test",
        "to": "recipient@eval.test",
        "subject": subject,
        "internet_message_id": "<orphan@mail>",
        "body_text": "",
        "internal_date_ms": int(row.created_at.timestamp() * 1000),
        "label_ids": ["Label_krowolf"],
    }
    client = MagicMock()
    client.list_labels.return_value = [{"id": "Label_krowolf", "name": "krowolf-live-eval"}]
    client.list_messages_page.return_value = GmailMessageListResult(
        message_ids=["m-orphan"], truncated=False
    )
    client.get_message.return_value = msg
    client.get_profile_email.return_value = "recipient@eval.test"
    resolution = DeliveryMailboxReaderResolution(
        reader=GoogleMailClientDeliveryReader(client),
        credential_source=CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV,
        mailbox_identity_redacted="re…@eval.test",
        source_allowed=True,
        source_matches_readiness=True,
        blockers=[],
    )
    with patch(
        "app.evaluation.live.delivery_mailbox_reader.resolve_delivery_mailbox_reader",
        return_value=resolution,
    ):
        result = probe_orphan_delivery_observation(db, row=row)
    assert result.classification == "orphaned_attempt_3_delivery_probe_verified"
    assert result.verified is True
    assert result.credential_source == CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV


def test_orphan_probe_report_has_no_secrets():
    from app.evaluation.live.delivery_mailbox_reader import OrphanDeliveryProbeResult

    result = OrphanDeliveryProbeResult(
        classification="orphaned_attempt_3_delivery_probe_verified",
        verified=True,
        credential_source=CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV,
        sender_message_id_redacted="19fc…be91",
    )
    payload = json.dumps(result.to_dict())
    assert "refresh_token" not in payload
    assert "client_secret" not in payload
    assert "access_token" not in payload
