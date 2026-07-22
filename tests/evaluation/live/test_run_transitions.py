"""Run transition state machine tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.evaluation.live.constants import RUN_STATUS_ACTIVE, RUN_STATUS_REGISTERED
from app.repositories.postgres.live_eval_models import LiveEvalRunRow
from app.repositories.postgres.live_eval_repository import (
    LiveEvalRunNotFoundError,
    LiveEvalRunRepository,
)


def _row(run_id: str, *, status: str = RUN_STATUS_REGISTERED) -> LiveEvalRunRow:
    now = datetime.now(timezone.utc)
    return LiveEvalRunRow(
        evaluation_run_id=run_id,
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        status=status,
        created_by="test",
        created_at=now,
        expires_at=now + timedelta(hours=2),
        config_hash="hash",
    )


def test_terminal_run_cannot_transition(db, live_eval_env):
    db.add(_row("run-term-1", status="completed"))
    db.commit()
    with pytest.raises(LiveEvalRunNotFoundError):
        LiveEvalRunRepository.transition_status(
            db,
            "run-term-1",
            tenant_id="TENANT_LIVE_EVAL",
            to_status=RUN_STATUS_ACTIVE,
        )


def test_wrong_tenant_transition_fails(db, live_eval_env):
    db.add(_row("run-tenant-1"))
    db.commit()
    with pytest.raises(LiveEvalRunNotFoundError):
        LiveEvalRunRepository.transition_status(
            db,
            "run-tenant-1",
            tenant_id="OTHER_TENANT",
            to_status=RUN_STATUS_ACTIVE,
        )


def test_concurrent_claim_only_one_wins(db, live_eval_env):
    db.add(_row("run-race-1"))
    db.commit()

    first = LiveEvalRunRepository.claim_root_job(
        db,
        evaluation_run_id="run-race-1",
        tenant_id="TENANT_LIVE_EVAL",
        root_gmail_message_id="msg-1",
        root_job_id="job-1",
    )
    assert first.status == RUN_STATUS_ACTIVE

    with pytest.raises(Exception):
        LiveEvalRunRepository.claim_root_job(
            db,
            evaluation_run_id="run-race-1",
            tenant_id="TENANT_LIVE_EVAL",
            root_gmail_message_id="msg-2",
            root_job_id="job-2",
        )
