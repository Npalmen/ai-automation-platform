"""Contractual expected outcomes for semi-automatic campaign scenarios."""

from __future__ import annotations

from dataclasses import dataclass

from app.evaluation.live.assertions import (
    OBSERVE_DECISION_SUBSEQUENCE_NO_DECISIONING,
    REQUIRED_DECISION_SUBSEQUENCE,
)
from app.evaluation.live.campaign.schemas import CampaignScenario

_APPROVAL_FIRST_PRE = frozenset({"awaiting_approval"})
_SAFE_HOLD_PRE = frozenset({"manual_review"})
_APPROVE_FINAL = frozenset({"completed"})
_REJECT_FINAL = frozenset({"manual_review"})


@dataclass(frozen=True)
class SemiAutomaticExpectedOutcome:
    operator_action: str
    expected_reply: bool
    test_variant: str
    pre_action_job_status: str
    final_job_status: str
    expect_pending_approval_pre: bool
    policy_authorization: str
    allow_operator_action: bool
    pre_action_success_statuses: frozenset[str]
    final_success_statuses: frozenset[str]
    decision_subsequence: tuple[str, ...]
    expect_approval_resolution: bool
    expect_duplicate_idempotent: bool
    expect_stale_conflict: bool

    @property
    def is_negative_hold(self) -> bool:
        return self.test_variant == "negative_hold"


def _approval_block(scenario: CampaignScenario) -> dict:
    return dict(scenario.expected_approval or {})


def resolve_semi_automatic_expected_outcome(
    scenario: CampaignScenario,
) -> SemiAutomaticExpectedOutcome:
    """Derive operator, poll, and assertion expectations from scenario YAML."""
    approval = _approval_block(scenario)
    routing = scenario.expected_routing or {}

    operator_action = str(approval.get("operator_action") or "none").strip().lower()
    expected_reply = bool(approval.get("expected_reply"))
    test_variant = str(approval.get("test_variant") or "normal").strip().lower()

    policy_authorization = str(routing.get("policy_authorization") or "").strip()
    pre_status = str(routing.get("job_status") or "").strip()

    if test_variant == "negative_hold":
        pre_status = pre_status or "manual_review"
        policy_authorization = policy_authorization or "hold_for_review"
        operator_action = "none"
        expected_reply = False
        allow_operator = False
        pre_statuses = _SAFE_HOLD_PRE
        final_statuses = _SAFE_HOLD_PRE
        expect_pending_pre = False
        decision_subsequence = OBSERVE_DECISION_SUBSEQUENCE_NO_DECISIONING
        expect_resolution = False
        expect_dup = False
        expect_stale = False
    elif operator_action == "approve":
        pre_status = pre_status or "awaiting_approval"
        policy_authorization = policy_authorization or "approval_required"
        allow_operator = True
        pre_statuses = _APPROVAL_FIRST_PRE
        final_statuses = _APPROVE_FINAL
        expect_pending_pre = True
        decision_subsequence = REQUIRED_DECISION_SUBSEQUENCE
        expect_resolution = True
        expect_dup = test_variant == "duplicate_approve"
        expect_stale = False
    elif operator_action == "reject":
        pre_status = pre_status or "awaiting_approval"
        policy_authorization = policy_authorization or "approval_required"
        allow_operator = True
        pre_statuses = _APPROVAL_FIRST_PRE
        final_statuses = _REJECT_FINAL
        expect_pending_pre = True
        decision_subsequence = REQUIRED_DECISION_SUBSEQUENCE
        expect_resolution = True
        expect_dup = False
        expect_stale = test_variant == "stale_action"
    else:
        pre_status = pre_status or "awaiting_approval"
        policy_authorization = policy_authorization or "approval_required"
        allow_operator = False
        pre_statuses = _APPROVAL_FIRST_PRE
        final_statuses = _REJECT_FINAL
        expect_pending_pre = True
        decision_subsequence = REQUIRED_DECISION_SUBSEQUENCE
        expect_resolution = False
        expect_dup = False
        expect_stale = False

    return SemiAutomaticExpectedOutcome(
        operator_action=operator_action,
        expected_reply=expected_reply,
        test_variant=test_variant,
        pre_action_job_status=pre_status,
        final_job_status=str(routing.get("final_job_status") or (
            "completed" if operator_action == "approve" and test_variant != "negative_hold"
            else "manual_review"
        )),
        expect_pending_approval_pre=expect_pending_pre,
        policy_authorization=policy_authorization,
        allow_operator_action=allow_operator,
        pre_action_success_statuses=pre_statuses,
        final_success_statuses=final_statuses,
        decision_subsequence=decision_subsequence,
        expect_approval_resolution=expect_resolution,
        expect_duplicate_idempotent=expect_dup,
        expect_stale_conflict=expect_stale,
    )
