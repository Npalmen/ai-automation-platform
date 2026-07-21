"""Thread continuation trusted snapshot contract tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.evaluation.live.continuation import enforce_live_eval_thread_continuation
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.subject_parser import build_subject_with_token
from app.repositories.postgres.live_eval_models import LiveEvalRunRow


def _trusted_snapshot_dict(run_id: str = "run-001-aaaa") -> dict:
    return {
        "evaluation_run_id": run_id,
        "tenant_id": "TENANT_LIVE_EVAL",
        "scenario_id": "S01_lead_laddbox_quality",
        "attempt_id": 1,
        "transport_mode": "live_gmail",
        "ai_mode": "fixture_ai",
        "fixture_bundle_id": "k2f_bundle_s01",
        "expected_sender": "sender@eval.test",
        "expected_recipient": "recipient@eval.test",
        "trusted": True,
    }


def _active_run(db, run_id: str = "run-001-aaaa") -> None:
    now = datetime.now(timezone.utc)
    db.add(
        LiveEvalRunRow(
            evaluation_run_id=run_id,
            tenant_id="TENANT_LIVE_EVAL",
            scenario_id="S01_lead_laddbox_quality",
            attempt_id=1,
            transport_mode="live_gmail",
            ai_mode="fixture_ai",
            fixture_bundle_id="k2f_bundle_s01",
            expected_sender="sender@eval.test",
            expected_recipient="recipient@eval.test",
            status="active",
            root_gmail_message_id="msg-root",
            root_job_id="job-root",
            created_by="test",
            created_at=now,
            expires_at=now + timedelta(hours=2),
            config_hash="hash",
        )
    )
    db.commit()


def test_valid_continuation_reuses_immutable_snapshot(db, live_eval_env):
    _active_run(db)
    root = {"live_eval": _trusted_snapshot_dict()}
    result = enforce_live_eval_thread_continuation(
        db,
        root_input_data=root,
        subject="Re: follow up without token",
        tenant_id="TENANT_LIVE_EVAL",
    )
    assert result == root["live_eval"]


def test_manipulated_continuation_token_rejected(db, live_eval_env):
    _active_run(db)
    root = {"live_eval": _trusted_snapshot_dict()}
    bad_subject = build_subject_with_token(
        evaluation_run_id="run-other-999",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        base_subject="evil",
    )
    with pytest.raises(LiveEvalSafetyError, match="mismatch"):
        enforce_live_eval_thread_continuation(
            db,
            root_input_data=root,
            subject=bad_subject,
            tenant_id="TENANT_LIVE_EVAL",
        )


def test_expired_run_continuation_rejected(db, live_eval_env):
    now = datetime.now(timezone.utc)
    db.add(
        LiveEvalRunRow(
            evaluation_run_id="run-expired-1",
            tenant_id="TENANT_LIVE_EVAL",
            scenario_id="S01_lead_laddbox_quality",
            attempt_id=1,
            transport_mode="live_gmail",
            ai_mode="fixture_ai",
            fixture_bundle_id="k2f_bundle_s01",
            expected_sender="sender@eval.test",
            expected_recipient="recipient@eval.test",
            status="expired",
            created_by="test",
            created_at=now,
            expires_at=now - timedelta(minutes=1),
            config_hash="hash",
        )
    )
    db.commit()
    root = {"live_eval": _trusted_snapshot_dict("run-expired-1")}
    with pytest.raises(LiveEvalSafetyError, match="not active"):
        enforce_live_eval_thread_continuation(
            db,
            root_input_data=root,
            subject="Re:",
            tenant_id="TENANT_LIVE_EVAL",
        )


def test_non_live_customer_continuation_unaffected(db, live_eval_env):
    root = {"subject": "normal"}
    assert (
        enforce_live_eval_thread_continuation(
            db,
            root_input_data=root,
            subject="Re: customer reply",
            tenant_id="TENANT_1001",
        )
        is None
    )
