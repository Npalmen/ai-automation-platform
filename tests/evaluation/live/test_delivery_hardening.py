"""Delivery hardening edge-case tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.evaluation.live.delivery import validate_delivery_candidate
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
