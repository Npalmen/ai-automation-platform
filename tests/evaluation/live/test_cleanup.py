"""Cleanup contract tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.evaluation.live.cleanup import cleanup_recipient_message
from app.evaluation.live.errors import LiveEvalSafetyError
from app.repositories.postgres.live_eval_models import LiveEvalRunRow


@pytest.fixture
def active_run(db):
    now = datetime.now(timezone.utc)
    row = LiveEvalRunRow(
        evaluation_run_id="run-clean-1",
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        status="active",
        created_by="test",
        created_at=now,
        expires_at=now + timedelta(hours=2),
        config_hash="abc",
        root_gmail_message_id="msg-recipient-1",
        root_job_id="job-1",
    )
    db.add(row)
    db.commit()
    return row


def test_post_claim_cleanup_requires_registry_match(db, active_run, live_eval_env, monkeypatch):
    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    with pytest.raises(LiveEvalSafetyError, match="does not match registry root"):
        cleanup_recipient_message(
            db,
            evaluation_run_id=active_run.evaluation_run_id,
            tenant_id=active_run.tenant_id,
            recipient_gmail_message_id="other-id",
            phase="post_claim",
        )


def test_post_claim_cleanup_archives_matching_message(db, active_run, live_eval_env, monkeypatch):
    monkeypatch.setenv("EXTERNAL_SIDE_EFFECT_TESTS", "yes")
    from app.evaluation.live.config import get_live_eval_config

    get_live_eval_config.cache_clear()
    adapter = MagicMock()
    adapter.execute_action.return_value = {
        "message": {
            "message_id": "msg-recipient-1",
            "subject": "KROWOLF-EVAL/run-clean-1/S01_lead_laddbox_quality/1 | Test",
            "from": "sender@eval.test",
            "to": "recipient@eval.test",
            "internal_date_ms": int(active_run.created_at.timestamp() * 1000),
            "label_ids": ["x"],
            "body_text": "",
        }
    }
    with patch(
        "app.evaluation.live.cleanup.get_integration_connection_config",
        return_value={},
    ), patch(
        "app.evaluation.live.cleanup.get_integration_adapter",
        return_value=adapter,
    ):
        result = cleanup_recipient_message(
            db,
            evaluation_run_id=active_run.evaluation_run_id,
            tenant_id=active_run.tenant_id,
            recipient_gmail_message_id="msg-recipient-1",
            phase="post_claim",
        )
    assert result["result"] == "archived"
    adapter.client.archive_from_inbox.assert_called_once_with("msg-recipient-1")
