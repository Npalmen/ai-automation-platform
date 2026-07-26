"""Campaign runner counter and observation trace regression tests."""

from __future__ import annotations

from app.evaluation.live.observation import _summarize_execution_trace


def test_summarize_execution_trace_exposes_resolution_and_outcome():
    summary = _summarize_execution_trace(
        [
            {
                "record_type": "action_approval_resolution",
                "action_operation_id": "op-1",
                "metadata": {"approval_id": "appr-1", "resolution": "approved"},
            },
            {
                "record_type": "execution_intent",
                "action_operation_id": "op-1",
                "execution_status": "pending",
            },
            {
                "record_type": "execution_outcome",
                "action_operation_id": "op-1",
                "execution_status": "succeeded",
            },
        ]
    )
    assert summary["action_operation_id"] == "op-1"
    assert summary["approval_resolution"]["resolution"] == "approved"
    assert summary["execution_intent"]["execution_status"] == "pending"
    assert summary["execution_outcome"]["execution_status"] == "succeeded"
