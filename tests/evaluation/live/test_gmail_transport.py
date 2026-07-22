"""Contract tests for duplicate-safe delivery observation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.delivery import (
    build_delivery_query,
    observe_delivery_candidates,
    validate_delivery_candidate,
)
from app.integrations.google.mail_client import GmailMessageListResult
from app.evaluation.live.subject_parser import build_subject_with_token
from app.repositories.postgres.live_eval_models import LiveEvalRunRow


@pytest.fixture
def run_row():
    now = datetime.now(timezone.utc)
    return LiveEvalRunRow(
        evaluation_run_id="run-delivery-1",
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


def test_build_delivery_query_contains_run_token(run_row):
    query = build_delivery_query(
        evaluation_run_id=run_row.evaluation_run_id,
        intake_label="krowolf-live-eval",
        run_created_at=run_row.created_at,
    )
    assert "KROWOLF-EVAL/run-delivery-1" in query
    assert "label:krowolf-live-eval" in query


def test_validate_delivery_candidate_accepts_matching_message(run_row, live_eval_env):
    subject = build_subject_with_token(
        evaluation_run_id=run_row.evaluation_run_id,
        scenario_id=run_row.scenario_id,
        attempt_id=run_row.attempt_id,
        base_subject="Test",
    )
    msg = {
        "subject": subject,
        "from": "Sender <sender@eval.test>",
        "to": "recipient@eval.test",
        "body_text": f"<!-- KROWOLF_EVAL:evaluation_run_id={run_row.evaluation_run_id} -->",
        "internal_date_ms": int(run_row.created_at.timestamp() * 1000),
        "label_ids": ["Label_1"],
    }
    ok, reason = validate_delivery_candidate(msg, row=run_row, config=None)
    assert ok, reason


def test_observe_delivery_duplicate_detected(db, run_row, live_eval_env):
    db.add(run_row)
    db.commit()
    subject = build_subject_with_token(
        evaluation_run_id=run_row.evaluation_run_id,
        scenario_id=run_row.scenario_id,
        attempt_id=run_row.attempt_id,
        base_subject="Dup",
    )
    msg = {
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

    adapter = MagicMock()
    adapter.client.list_messages_page.return_value = GmailMessageListResult(
        message_ids=["m1", "m2"],
        truncated=False,
    )
    adapter.execute_action.side_effect = [
        {"labels": [{"name": "krowolf-live-eval", "id": "Label_krowolf"}]},
        {"message": msg},
        {"message": {**msg, "message_id": "m2"}},
    ]

    with patch(
        "app.evaluation.live.delivery.get_integration_connection_config",
        return_value={},
    ), patch(
        "app.evaluation.live.delivery.get_integration_adapter",
        return_value=adapter,
    ):
        result = observe_delivery_candidates(db, run_row)
    assert result.duplicate_detected is True
    assert result.valid_count == 2
