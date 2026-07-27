"""Tests for target-scoped approval observation."""

from __future__ import annotations

from app.evaluation.live.assertions import REQUIRED_DECISION_SUBSEQUENCE
from app.evaluation.live.campaign.approval_observation import (
    count_contract_pending_external_write_approvals,
    is_legacy_job_level_approval,
)
from app.evaluation.live.campaign.operator_contract import SecondaryApprovalExpectation
from app.evaluation.live.campaign.semi_automatic_expected_outcomes import (
    SemiAutomaticExpectedOutcome,
)
from app.evaluation.live.campaign.test_operator import PendingApproval


def _row(**kwargs) -> PendingApproval:
    defaults = {
        "approval_id": "appr-1",
        "state": "pending",
        "next_on_approve": "action_execute",
        "action_type": "send_customer_auto_reply",
        "delivery_type": "send_customer_auto_reply",
        "action_operation_id": "op-1",
        "recipient_redacted": "se***@eval.test",
        "created_at": None,
    }
    defaults.update(kwargs)
    return PendingApproval(**defaults)


def _reject_outcome(
    *,
    secondary_approvals: tuple[SecondaryApprovalExpectation, ...] = (),
) -> SemiAutomaticExpectedOutcome:
    return SemiAutomaticExpectedOutcome(
        operator_action="reject",
        expected_reply=False,
        test_variant="normal",
        pre_action_job_status="awaiting_approval",
        final_job_status="awaiting_approval",
        expect_pending_approval_pre=True,
        policy_authorization="approval_required",
        allow_operator_action=True,
        pre_action_success_statuses=frozenset({"awaiting_approval"}),
        final_success_statuses=frozenset({"awaiting_approval"}),
        decision_subsequence=REQUIRED_DECISION_SUBSEQUENCE,
        expect_approval_resolution=False,
        expect_duplicate_idempotent=False,
        expect_stale_conflict=False,
        operator_plan=(),
        secondary_approvals=secondary_approvals,
        uses_legacy_operator_action=False,
    )


def test_legacy_job_level_detection():
    assert is_legacy_job_level_approval(
        _row(next_on_approve="action_dispatch", action_operation_id=None)
    )
    assert not is_legacy_job_level_approval(_row(next_on_approve="action_execute"))


def test_reject_scenario_ignores_legacy_pending():
    outcome = _reject_outcome()
    approvals = [
        _row(approval_id="legacy", next_on_approve="action_dispatch", action_operation_id=None),
        _row(approval_id="target", state="rejected"),
    ]
    assert count_contract_pending_external_write_approvals(approvals, outcome) == 0


def test_unexpected_target_still_pending():
    outcome = _reject_outcome()
    approvals = [_row(state="pending", action_type="send_customer_auto_reply")]
    assert count_contract_pending_external_write_approvals(approvals, outcome) == 1


def test_secondary_remain_pending_allowed():
    outcome = _reject_outcome(
        secondary_approvals=(
            SecondaryApprovalExpectation(
                action_type="send_internal_handoff",
                expected_final_state="remain_pending",
            ),
        ),
    )
    outcome = SemiAutomaticExpectedOutcome(
        operator_action="approve",
        expected_reply=True,
        test_variant="normal",
        pre_action_job_status="awaiting_approval",
        final_job_status="awaiting_approval",
        expect_pending_approval_pre=True,
        policy_authorization="approval_required",
        allow_operator_action=True,
        pre_action_success_statuses=frozenset({"awaiting_approval"}),
        final_success_statuses=frozenset({"awaiting_approval"}),
        decision_subsequence=REQUIRED_DECISION_SUBSEQUENCE,
        expect_approval_resolution=True,
        expect_duplicate_idempotent=False,
        expect_stale_conflict=False,
        operator_plan=(),
        secondary_approvals=outcome.secondary_approvals,
        uses_legacy_operator_action=False,
    )
    approvals = [
        _row(action_type="send_internal_handoff", delivery_type="send_internal_handoff"),
    ]
    assert count_contract_pending_external_write_approvals(approvals, outcome) == 0
