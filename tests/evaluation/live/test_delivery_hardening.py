"""Delivery hardening edge-case tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.delivery import observe_delivery_candidates, validate_delivery_candidate
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.safety import validate_delivery_observation_allowed
from app.evaluation.live.subject_parser import build_subject_with_token
from app.repositories.postgres.live_eval_models import LiveEvalRunRow


@pytest.fixture
def run_row():
    now = datetime.now(timezone.utc)
    return LiveEvalRunRow(
        evaluation_run_id="run-delivery-hard",
        tenant_id="TENANT_LIVE_EVAL",
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


def test_missing_internal_date_rejected(run_row, live_eval_env):
    subject = build_subject_with_token(
        evaluation_run_id=run_row.evaluation_run_id,
        scenario_id=run_row.scenario_id,
        attempt_id=run_row.attempt_id,
        base_subject="Test",
    )
    msg = {
        "subject": subject,
        "from": "sender@eval.test",
        "to": "recipient@eval.test",
        "internal_date_ms": None,
        "label_ids": ["Label_1"],
    }
    ok, reason = validate_delivery_candidate(
        msg, row=run_row, config=None, intake_label_id="Label_1"
    )
    assert not ok
    assert reason == "internal_date_out_of_window"


def test_exact_label_id_required(run_row, live_eval_env):
    subject = build_subject_with_token(
        evaluation_run_id=run_row.evaluation_run_id,
        scenario_id=run_row.scenario_id,
        attempt_id=run_row.attempt_id,
        base_subject="Test",
    )
    msg = {
        "subject": subject,
        "from": "sender@eval.test",
        "to": "recipient@eval.test",
        "internal_date_ms": int(run_row.created_at.timestamp() * 1000),
        "label_ids": ["Label_other"],
    }
    ok, reason = validate_delivery_candidate(
        msg, row=run_row, config=None, intake_label_id="Label_expected"
    )
    assert not ok
    assert reason == "missing_intake_label"


def test_active_without_root_binding_rejected(run_row):
    run_row.status = "active"
    with pytest.raises(LiveEvalSafetyError, match="missing root binding"):
        validate_delivery_observation_allowed(run_row)


def _valid_msg(run_row):
    subject = build_subject_with_token(
        evaluation_run_id=run_row.evaluation_run_id,
        scenario_id=run_row.scenario_id,
        attempt_id=run_row.attempt_id,
        base_subject="Test",
    )
    return {
        "message_id": "m1",
        "thread_id": "t1",
        "from": "sender@eval.test",
        "to": "recipient@eval.test",
        "subject": subject,
        "internet_message_id": "<a@b>",
        "body_text": "",
        "internal_date_ms": int(run_row.created_at.timestamp() * 1000),
        "label_ids": ["Label_krowolf"],
    }


def test_delivery_truncated_gmail_list_correlation_failure(db, run_row, live_eval_env):
    from app.integrations.google.mail_client import GmailMessageListResult

    db.add(run_row)
    db.commit()
    adapter = MagicMock()
    adapter.client.list_messages_page.return_value = GmailMessageListResult(
        message_ids=["m1"], truncated=True
    )
    adapter.execute_action.return_value = {
        "labels": [{"name": "krowolf-live-eval", "id": "Label_krowolf"}],
    }
    with patch(
        "app.evaluation.live.delivery.get_integration_connection_config",
        return_value={},
    ), patch(
        "app.evaluation.live.delivery.get_integration_adapter",
        return_value=adapter,
    ):
        result = observe_delivery_candidates(db, run_row)
    assert result.truncated is True
    assert result.duplicate_detected is True
    assert result.confirmed is None


def test_delivery_one_valid_candidate(db, run_row, live_eval_env):
    from app.integrations.google.mail_client import GmailMessageListResult

    db.add(run_row)
    db.commit()
    msg = _valid_msg(run_row)
    adapter = MagicMock()
    adapter.client.list_messages_page.return_value = GmailMessageListResult(
        message_ids=["m1"], truncated=False
    )
    adapter.execute_action.side_effect = [
        {"labels": [{"name": "krowolf-live-eval", "id": "Label_krowolf"}]},
        {"message": msg},
    ]
    with patch(
        "app.evaluation.live.delivery.get_integration_connection_config",
        return_value={},
    ), patch(
        "app.evaluation.live.delivery.get_integration_adapter",
        return_value=adapter,
    ):
        result = observe_delivery_candidates(db, run_row)
    assert result.valid_count == 1
    assert result.confirmed is not None
