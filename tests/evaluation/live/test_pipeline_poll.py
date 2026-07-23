"""Pipeline poll fail-fast and timeout snapshot tests."""

from __future__ import annotations

import pytest

from app.evaluation.live.errors import LiveEvalPipelinePollError
from app.evaluation.live.pipeline_poll import (
    build_redacted_job_snapshot,
    classify_poll_outcome,
    poll_pipeline_observation,
)


def _observation(*, status: str = "processing", root_job_id: str = "job-1") -> dict:
    return {
        "run": {"tenant_id": "TENANT_LIVE_EVAL", "root_job_id": root_job_id},
        "job": {
            "job_id": "job-1",
            "job_status": status,
            "pending_approval_count": 0,
            "policy": {"policy_authorization": "hold_for_review", "decision": "hold_for_review"},
            "classification": {"detected_job_type": "lead"},
            "decision_records": [],
        },
    }


def test_classify_unexpected_terminal_status():
    reason = classify_poll_outcome(
        _observation(status="manual_review"),
        poll_attempts=1,
        previous_status=None,
    )
    assert reason == "unexpected_terminal_status"


def test_build_redacted_job_snapshot_omits_sensitive_fields():
    snapshot = build_redacted_job_snapshot(_observation(status="manual_review"))
    assert snapshot["observed_status"] == "manual_review"
    assert "message_text" not in snapshot
    assert "subject" not in snapshot


def test_classify_failed_status():
    from app.evaluation.live.pipeline_poll import classify_poll_outcome

    reason = classify_poll_outcome(
        {
            "run": {"root_job_id": "job-1"},
            "job": {"job_status": "failed"},
        },
        poll_attempts=1,
        previous_status=None,
    )
    assert reason == "pipeline_failed"


def test_poll_fail_fast_on_manual_review():
    calls = {"count": 0}

    def fetch() -> dict:
        calls["count"] += 1
        return _observation(status="manual_review")

    with pytest.raises(LiveEvalPipelinePollError) as exc_info:
        poll_pipeline_observation(fetch, timeout_seconds=30)

    assert exc_info.value.timeout_reason == "unexpected_terminal_status"
    assert exc_info.value.job_snapshot["observed_status"] == "manual_review"
    assert calls["count"] == 1


def test_poll_fail_fast_on_failed_status():
    with pytest.raises(LiveEvalPipelinePollError) as exc_info:
        poll_pipeline_observation(
            lambda: _observation(status="failed"),
            timeout_seconds=30,
        )
    assert exc_info.value.timeout_reason == "pipeline_failed"


def test_poll_succeeds_on_awaiting_approval():
    state = {"status": "processing"}

    def fetch() -> dict:
        return _observation(status=state["status"])

    state["status"] = "awaiting_approval"
    result = poll_pipeline_observation(fetch, timeout_seconds=5)
    assert result.observation["job"]["job_status"] == "awaiting_approval"
