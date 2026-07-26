"""Test operator approval selection for semi-auto campaigns."""

from app.evaluation.live.campaign.test_operator import (
    PendingApproval,
    _select_operator_pending_approvals,
)


def test_prefers_action_execute_over_job_level_dispatch():
    pending = [
        PendingApproval(
            approval_id="job-level",
            state="pending",
            next_on_approve="action_dispatch",
        ),
        PendingApproval(
            approval_id="per-action",
            state="pending",
            next_on_approve="action_execute",
        ),
    ]
    selected = _select_operator_pending_approvals(pending)
    assert len(selected) == 1
    assert selected[0].approval_id == "per-action"
