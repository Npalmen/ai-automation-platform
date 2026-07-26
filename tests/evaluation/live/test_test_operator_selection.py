"""Test operator approval selection for semi-auto campaigns."""

from app.evaluation.live.campaign.operator_contract import OperatorPlanStep
from app.evaluation.live.campaign.test_operator import (
    PendingApproval,
    match_target_approval,
)


def _row(
    *,
    approval_id: str,
    next_on_approve: str,
    action_type: str = "send_customer_auto_reply",
    operation_id: str = "op-1",
) -> PendingApproval:
    return PendingApproval(
        approval_id=approval_id,
        state="pending",
        next_on_approve=next_on_approve,
        action_type=action_type,
        delivery_type=action_type,
        action_operation_id=operation_id,
        recipient_redacted="te***@eval.test",
    )


def test_prefers_action_execute_over_job_level_dispatch():
    pending = [
        _row(approval_id="job-level", next_on_approve="action_dispatch", action_type="unknown", operation_id="op-job"),
        _row(approval_id="per-action", next_on_approve="action_execute"),
    ]
    step = OperatorPlanStep(action_type="send_customer_auto_reply", decision="approve")
    selected = match_target_approval(pending, step)
    assert selected.approval_id == "per-action"
