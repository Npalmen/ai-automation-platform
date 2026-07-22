"""Session-safe idempotency for live-eval repository writes."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.evaluation.live.telemetry import (
    build_event_key,
    build_operation_key,
    record_live_eval_external_event,
)
from app.evaluation.live.schemas import TrustedLiveEvalSnapshot
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.live_eval_models import LiveEvalExternalEventRow, LiveEvalRunRow
from app.repositories.postgres.live_eval_repository import (
    LiveEvalRunConflictError,
    LiveEvalExternalEventRepository,
    LiveEvalRunRepository,
)


def _snapshot(run_id: str = "run-session") -> TrustedLiveEvalSnapshot:
    return TrustedLiveEvalSnapshot(
        evaluation_run_id=run_id,
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        config_hash="abc123",
        trusted=True,
    )


def _sibling_job() -> JobRecord:
    now = datetime.now(timezone.utc)
    return JobRecord(
        job_id="sibling-job-1",
        tenant_id="TENANT_LIVE_EVAL",
        job_type="lead",
        status="created",
        input_data={},
        result=None,
        created_at=now,
        updated_at=now,
        created_by=None,
    )


def test_record_event_duplicate_preserves_sibling_and_commits(db, live_eval_env, sample_run_row):
    sample_run_row.evaluation_run_id = "run-session"
    sample_run_row.status = "active"
    db.add(sample_run_row)
    db.add(_sibling_job())
    db.flush()

    snap = _snapshot()
    op_key = build_operation_key(
        evaluation_run_id=snap.evaluation_run_id,
        category="app_external_write_blocked",
        operation="send_email",
        action_operation_id="op-1",
    )
    assert (
        record_live_eval_external_event(
            db,
            operation_key=op_key,
            outcome="blocked",
            category="app_external_write_blocked",
            operation="send_email",
            integration_type="google_mail",
            snapshot=snap,
            attempt=1,
        )
        is True
    )
    assert (
        record_live_eval_external_event(
            db,
            operation_key=op_key,
            outcome="blocked",
            category="app_external_write_blocked",
            operation="send_email",
            integration_type="google_mail",
            snapshot=snap,
            attempt=1,
        )
        is False
    )

    db.commit()
    assert db.get(JobRecord, "sibling-job-1") is not None
    events = LiveEvalExternalEventRepository.list_for_run(
        db, "run-session", tenant_id="TENANT_LIVE_EVAL"
    )
    assert len(events) == 1


def test_register_run_duplicate_preserves_sibling_and_commits(db, live_eval_env, sample_run_row):
    db.add(sample_run_row)
    db.add(_sibling_job())
    db.flush()

    duplicate = LiveEvalRunRow(
        evaluation_run_id=sample_run_row.evaluation_run_id,
        tenant_id=sample_run_row.tenant_id,
        scenario_id=sample_run_row.scenario_id,
        attempt_id=sample_run_row.attempt_id,
        transport_mode=sample_run_row.transport_mode,
        ai_mode=sample_run_row.ai_mode,
        fixture_bundle_id=sample_run_row.fixture_bundle_id,
        expected_sender=sample_run_row.expected_sender,
        expected_recipient=sample_run_row.expected_recipient,
        status="registered",
        created_by=sample_run_row.created_by,
        created_at=sample_run_row.created_at,
        expires_at=sample_run_row.expires_at,
        config_hash=sample_run_row.config_hash,
    )

    with pytest.raises(LiveEvalRunConflictError, match="already exists"):
        LiveEvalRunRepository.register_run(db, duplicate)

    db.commit()
    assert db.get(JobRecord, "sibling-job-1") is not None


def test_record_event_duplicate_returns_false(db, live_eval_env, sample_run_row):
    sample_run_row.evaluation_run_id = "run-dup-event"
    sample_run_row.status = "active"
    db.add(sample_run_row)
    db.commit()

    event = LiveEvalExternalEventRow(
        event_key="run-dup-event:cat:op:1:blocked:1",
        operation_key="run-dup-event:cat:op:1",
        evaluation_run_id="run-dup-event",
        tenant_id="TENANT_LIVE_EVAL",
        integration_type="google_mail",
        category="cat",
        operation="op",
        outcome="blocked",
        started_at=datetime.now(timezone.utc),
        redacted_metadata={},
    )
    assert LiveEvalExternalEventRepository.record_event(db, event) is True
    duplicate = LiveEvalExternalEventRow(
        event_key=event.event_key,
        operation_key=event.operation_key,
        evaluation_run_id=event.evaluation_run_id,
        tenant_id=event.tenant_id,
        integration_type=event.integration_type,
        category=event.category,
        operation=event.operation,
        outcome=event.outcome,
        started_at=event.started_at,
        redacted_metadata={},
    )
    assert LiveEvalExternalEventRepository.record_event(db, duplicate) is False
