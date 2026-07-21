"""Registry, claim, and transition tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.registry import (
    claim_live_eval_root_job,
    complete_live_eval_run,
    register_live_eval_run,
    trusted_snapshot_from_row,
)
from app.evaluation.live.schemas import LiveEvalRunRegisterRequest
from app.repositories.postgres.live_eval_repository import LiveEvalRunRepository


def test_register_and_claim_root_job(db, live_eval_env):
    request = LiveEvalRunRegisterRequest(
        evaluation_run_id="run-abc-001",
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        ai_mode="fixture_ai",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
    )
    with patch("app.evaluation.live.registry.emit_live_eval_audit"):
        created = register_live_eval_run(db, request, created_by="test")
    assert created.status == "registered"

    with patch("app.evaluation.live.registry.emit_live_eval_audit"):
        claimed = claim_live_eval_root_job(
            db,
            evaluation_run_id="run-abc-001",
            tenant_id="TENANT_LIVE_EVAL",
            root_gmail_message_id="msg-root-1",
            root_job_id="job-root-1",
        )
    assert claimed.status == "active"
    assert claimed.fixture_bundle_id == "k2f_bundle_s01"

    row = LiveEvalRunRepository.get_run(db, "run-abc-001", tenant_id="TENANT_LIVE_EVAL")
    snapshot = trusted_snapshot_from_row(row)
    assert snapshot.trusted is True
    assert not hasattr(snapshot, "gmail_message_id")


def test_duplicate_root_claim_rejected(db, live_eval_env, sample_run_row):
    sample_run_row.evaluation_run_id = "run-dup-001"
    sample_run_row.status = "active"
    sample_run_row.root_gmail_message_id = "msg-a"
    sample_run_row.root_job_id = "job-a"
    db.add(sample_run_row)
    db.commit()

    with pytest.raises(LiveEvalSafetyError, match="already claimed"):
        claim_live_eval_root_job(
            db,
            evaluation_run_id="run-dup-001",
            tenant_id="TENANT_LIVE_EVAL",
            root_gmail_message_id="msg-b",
            root_job_id="job-b",
        )


def test_complete_requires_tenant_and_active(db, live_eval_env, sample_run_row):
    sample_run_row.evaluation_run_id = "run-complete-1"
    sample_run_row.status = "active"
    sample_run_row.root_gmail_message_id = "msg-1"
    sample_run_row.root_job_id = "job-1"
    db.add(sample_run_row)
    db.commit()

    with patch("app.evaluation.live.registry.emit_live_eval_audit"):
        done = complete_live_eval_run(
            db,
            "run-complete-1",
            tenant_id="TENANT_LIVE_EVAL",
            status="completed",
        )
    assert done.status == "completed"

    with pytest.raises(LiveEvalSafetyError):
        complete_live_eval_run(
            db,
            "run-complete-1",
            tenant_id="TENANT_LIVE_EVAL",
            status="aborted",
        )


def test_intake_rejects_expired_run(db, live_eval_env, sample_run_row):
    sample_run_row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.add(sample_run_row)
    db.commit()

    from app.evaluation.live.config import get_live_eval_config
    from app.evaluation.live.safety import validate_run_row_for_intake

    with pytest.raises(LiveEvalSafetyError, match="expired"):
        validate_run_row_for_intake(
            sample_run_row,
            tenant_id="TENANT_LIVE_EVAL",
            scenario_id="S01_lead_laddbox_quality",
            attempt_id=1,
            sender_email="sender@eval.test",
            recipient_email="recipient@eval.test",
            query="label:krowolf-live-eval is:unread",
            config=get_live_eval_config(),
            require_registered=True,
        )
