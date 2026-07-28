"""Regression tests for semi-auto phase-aware observation (canary 30308440030)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.evaluation.live.campaign.registry import clear_campaign_registry_cache, get_campaign_scenario
from app.evaluation.live.campaign.semi_automatic_expected_outcomes import (
    resolve_semi_automatic_expected_outcome,
)
from app.evaluation.live.campaign.test_operator import PendingApproval
from app.evaluation.live.errors import LiveEvalPipelinePollError, LiveEvalSafetyError
from app.evaluation.live.pipeline_poll import poll_pipeline_observation
from app.evaluation.live.semi_auto_phase import (
    SemiAutoPhaseProvenance,
    assert_phase_monotonicity,
    classify_pre_operator_readiness,
    poll_post_operator_observation,
    poll_pre_operator_readiness,
    resolve_post_operator_success_statuses,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    clear_campaign_registry_cache()
    yield
    clear_campaign_registry_cache()


def _observation(
    *,
    status: str = "awaiting_approval",
    pending: int = 1,
    resolution: int = 0,
    intent: int = 0,
    outcome: int = 0,
    evaluation_run_id: str = "run-1",
    job_id: str = "job-1",
) -> dict:
    records = []
    for _ in range(resolution):
        records.append({"record_type": "action_approval_resolution"})
    for _ in range(intent):
        records.append({"record_type": "execution_intent"})
    for _ in range(outcome):
        records.append({"record_type": "execution_outcome"})
    return {
        "run": {
            "tenant_id": "TENANT_LIVE_EVAL",
            "root_job_id": job_id,
            "evaluation_run_id": evaluation_run_id,
        },
        "job": {
            "job_id": job_id,
            "job_status": status,
            "pending_approval_count": pending,
            "decision_records": records,
        },
    }


def _pending_target(*, approval_id: str = "appr-1", operation_id: str = "op-1") -> PendingApproval:
    return PendingApproval(
        approval_id=approval_id,
        state="pending",
        next_on_approve="action_execute",
        action_type="send_customer_auto_reply",
        delivery_type="send_customer_auto_reply",
        action_operation_id=operation_id,
        recipient_redacted="te***@eval.test",
    )


def test_pre_operator_requires_target_pending():
    outcome = resolve_semi_automatic_expected_outcome(
        get_campaign_scenario("TBSM01_lead_approve_reply")
    )
    reason = classify_pre_operator_readiness(
        _observation(status="processing", pending=0),
        outcome=outcome,
        pending_approvals=[],
        operator_started=False,
    )
    assert reason is None


def test_pre_operator_ready_when_target_pending():
    outcome = resolve_semi_automatic_expected_outcome(
        get_campaign_scenario("TBSM01_lead_approve_reply")
    )
    reason = classify_pre_operator_readiness(
        _observation(),
        outcome=outcome,
        pending_approvals=[_pending_target()],
        operator_started=False,
    )
    assert reason == "ready"


def test_resolution_before_operator_is_bypass():
    outcome = resolve_semi_automatic_expected_outcome(
        get_campaign_scenario("TBSM01_lead_approve_reply")
    )
    reason = classify_pre_operator_readiness(
        _observation(status="completed", pending=0, resolution=1, intent=1, outcome=1),
        outcome=outcome,
        pending_approvals=[],
        operator_started=False,
    )
    assert reason == "resolution_or_execution_before_operator_request"


def test_post_operator_poll_allows_manual_review_after_reject():
    outcome = resolve_semi_automatic_expected_outcome(
        get_campaign_scenario("TBSM04_lead_reject")
    )
    statuses = resolve_post_operator_success_statuses(outcome)
    assert "manual_review" in statuses

    provenance = SemiAutoPhaseProvenance(
        evaluation_run_id="run-1",
        operator_completed_at=datetime.now(timezone.utc).isoformat(),
    )
    result = poll_post_operator_observation(
        lambda: _observation(status="manual_review", pending=0, resolution=1),
        outcome=outcome,
        evaluation_run_id="run-1",
        timeout_seconds=5,
        provenance=provenance,
    )
    assert result.observation["job"]["job_status"] == "manual_review"


def test_post_operator_poll_allows_completed_after_approve():
    outcome = resolve_semi_automatic_expected_outcome(
        get_campaign_scenario("TBSM01_lead_approve_reply")
    )
    statuses = resolve_post_operator_success_statuses(outcome)
    assert "completed" in statuses

    provenance = SemiAutoPhaseProvenance(
        evaluation_run_id="run-1",
        operator_completed_at=datetime.now(timezone.utc).isoformat(),
    )
    result = poll_post_operator_observation(
        lambda: _observation(status="completed", pending=0, resolution=1, intent=1, outcome=1),
        outcome=outcome,
        evaluation_run_id="run-1",
        timeout_seconds=5,
        provenance=provenance,
    )
    assert result.observation["job"]["job_status"] == "completed"


def test_pre_operator_poll_fail_fast_on_terminal_before_operator():
    outcome = resolve_semi_automatic_expected_outcome(
        get_campaign_scenario("TBSM04_lead_reject")
    )
    provenance = SemiAutoPhaseProvenance(evaluation_run_id="run-1")
    with pytest.raises(LiveEvalSafetyError) as exc_info:
        poll_pre_operator_readiness(
            lambda: _observation(status="manual_review", pending=0, resolution=1),
            lambda _job_id: [],
            outcome=outcome,
            evaluation_run_id="run-1",
            timeout_seconds=1,
            provenance=provenance,
        )
    assert "approval_bypass_or_phase_order_violation" in str(exc_info.value)


def test_pre_operator_poll_passes_on_first_pending_snapshot():
    outcome = resolve_semi_automatic_expected_outcome(
        get_campaign_scenario("TBSM01_lead_approve_reply")
    )
    provenance = SemiAutoPhaseProvenance(evaluation_run_id="run-1")
    observation, target = poll_pre_operator_readiness(
        lambda: _observation(),
        lambda _job_id: [_pending_target()],
        outcome=outcome,
        evaluation_run_id="run-1",
        timeout_seconds=5,
        provenance=provenance,
    )
    assert observation["job"]["job_id"] == "job-1"
    assert target.approval_id == "appr-1"
    assert provenance.pre_operator_gate_passed_at is not None


def test_post_operator_poll_rejects_completed_without_operator_marker():
    outcome = resolve_semi_automatic_expected_outcome(
        get_campaign_scenario("TBSM01_lead_approve_reply")
    )
    provenance = SemiAutoPhaseProvenance(evaluation_run_id="run-1")
    with pytest.raises(LiveEvalSafetyError):
        poll_post_operator_observation(
            lambda: _observation(status="completed", pending=0, resolution=1),
            outcome=outcome,
            evaluation_run_id="run-1",
            timeout_seconds=5,
            provenance=provenance,
        )


def test_pre_operator_does_not_use_terminal_status_contract():
    outcome = resolve_semi_automatic_expected_outcome(
        get_campaign_scenario("TBSM01_lead_approve_reply")
    )
    with pytest.raises(LiveEvalPipelinePollError) as exc_info:
        poll_pipeline_observation(
            lambda: _observation(status="completed", pending=0, resolution=1),
            timeout_seconds=1,
            success_statuses=outcome.pre_action_success_statuses,
        )
    assert exc_info.value.timeout_reason == "unexpected_terminal_status"


def test_phase_timestamps_monotonic():
    provenance = SemiAutoPhaseProvenance(
        evaluation_run_id="run-1",
        pre_operator_gate_started_at="2026-07-27T22:17:51+00:00",
        pre_operator_gate_passed_at="2026-07-27T22:17:52+00:00",
        operator_started_at="2026-07-27T22:17:53+00:00",
        operator_completed_at="2026-07-27T22:17:54+00:00",
        post_operator_poll_started_at="2026-07-27T22:17:55+00:00",
        post_operator_completed_at="2026-07-27T22:17:56+00:00",
    )
    assert assert_phase_monotonicity(provenance) == []


def test_phase_violation_when_operator_before_pre_operator_pass():
    provenance = SemiAutoPhaseProvenance(
        evaluation_run_id="run-1",
        operator_started_at="2026-07-27T22:17:51+00:00",
    )
    violations = assert_phase_monotonicity(provenance)
    assert "operator_started_before_pre_operator_gate_pass" in violations
