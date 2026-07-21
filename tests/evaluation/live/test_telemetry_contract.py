"""External event operation_key / event_key idempotency contract tests."""

from __future__ import annotations

import pytest

from app.evaluation.live.constants import EVENT_OUTCOME_FAILED, EVENT_OUTCOME_SUCCEEDED
from app.evaluation.live.schemas import TrustedLiveEvalSnapshot
from app.evaluation.live.telemetry import (
    build_event_key,
    build_operation_key,
    operation_already_succeeded,
    record_live_eval_external_event,
)
from app.repositories.postgres.live_eval_repository import LiveEvalExternalEventRepository


def _snapshot() -> TrustedLiveEvalSnapshot:
    return TrustedLiveEvalSnapshot(
        evaluation_run_id="run-telemetry",
        tenant_id="TENANT_LIVE_EVAL",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        transport_mode="live_gmail",
        ai_mode="fixture_ai",
        fixture_bundle_id="k2f_bundle_s01",
        expected_sender="sender@eval.test",
        expected_recipient="recipient@eval.test",
        trusted=True,
    )


def test_failed_then_succeeded_allowed(db, live_eval_env, sample_run_row):
    sample_run_row.evaluation_run_id = "run-telemetry"
    sample_run_row.status = "active"
    db.add(sample_run_row)
    db.commit()

    snap = _snapshot()
    op_key = build_operation_key(
        evaluation_run_id=snap.evaluation_run_id,
        category="app_gmail_reply",
        operation="send_customer_auto_reply",
        action_operation_id="op-1",
    )
    assert (
        record_live_eval_external_event(
            db,
            operation_key=op_key,
            outcome=EVENT_OUTCOME_FAILED,
            category="app_gmail_reply",
            operation="send_customer_auto_reply",
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
            outcome=EVENT_OUTCOME_SUCCEEDED,
            category="app_gmail_reply",
            operation="send_customer_auto_reply",
            integration_type="google_mail",
            snapshot=snap,
        )
        is True
    )
    assert operation_already_succeeded(db, op_key) is True
    events = LiveEvalExternalEventRepository.list_for_run(
        db, "run-telemetry", tenant_id="TENANT_LIVE_EVAL"
    )
    assert len(events) == 2
    assert {e.outcome for e in events} == {"failed", "succeeded"}


def test_retry_after_success_is_idempotent_event_key(db, live_eval_env, sample_run_row):
    sample_run_row.evaluation_run_id = "run-telemetry-2"
    sample_run_row.status = "active"
    db.add(sample_run_row)
    db.commit()

    snap = _snapshot()
    snap = snap.model_copy(update={"evaluation_run_id": "run-telemetry-2"})
    op_key = build_operation_key(
        evaluation_run_id="run-telemetry-2",
        category="app_gmail_reply",
        operation="send_customer_auto_reply",
        action_operation_id="op-2",
    )
    event_key = build_event_key(operation_key=op_key, outcome=EVENT_OUTCOME_SUCCEEDED)
    assert event_key.endswith(":succeeded")

    assert (
        record_live_eval_external_event(
            db,
            operation_key=op_key,
            outcome=EVENT_OUTCOME_SUCCEEDED,
            category="app_gmail_reply",
            operation="send_customer_auto_reply",
            integration_type="google_mail",
            snapshot=snap,
        )
        is True
    )
    assert (
        record_live_eval_external_event(
            db,
            operation_key=op_key,
            outcome=EVENT_OUTCOME_SUCCEEDED,
            category="app_gmail_reply",
            operation="send_customer_auto_reply",
            integration_type="google_mail",
            snapshot=snap,
        )
        is False
    )
