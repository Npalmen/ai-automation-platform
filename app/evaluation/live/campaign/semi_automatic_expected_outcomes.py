"""Contractual expected outcomes for semi-automatic campaign scenarios."""

from __future__ import annotations

from dataclasses import dataclass

from app.evaluation.live.assertions import (
    OBSERVE_DECISION_SUBSEQUENCE_NO_DECISIONING,
    REQUIRED_DECISION_SUBSEQUENCE,
)
from app.evaluation.live.campaign.operator_contract import (
    OperatorPlanStep,
    SecondaryApprovalExpectation,
    parse_semi_auto_operator_contract,
)
from app.evaluation.live.campaign.schemas import CampaignScenario

_APPROVAL_FIRST_PRE = frozenset({"awaiting_approval"})
_SAFE_HOLD_PRE = frozenset({"manual_review"})
_TERMINAL_WITH_SECONDARY_PENDING = frozenset({"awaiting_approval"})


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
    operator_plan: tuple[OperatorPlanStep, ...]
    secondary_approvals: tuple[SecondaryApprovalExpectation, ...]
    uses_legacy_operator_action: bool

    @property
    def is_negative_hold(self) -> bool:
        return self.test_variant == "negative_hold"

    @property
    def target_action_type(self) -> str | None:
        if not self.operator_plan:
            return None
        return self.operator_plan[0].action_type


def _approval_block(scenario: CampaignScenario) -> dict:
    return dict(scenario.expected_approval or {})


def _derive_legacy_operator_action(plan: tuple[OperatorPlanStep, ...]) -> str:
    if not plan:
        return "none"
    first = plan[0].decision
    if first == "approve":
        return "approve"
    if first == "reject":
        return "reject"
    return "none"


def resolve_semi_automatic_expected_outcome(
    scenario: CampaignScenario,
) -> SemiAutomaticExpectedOutcome:
    """Derive operator, poll, and assertion expectations from scenario YAML."""
    approval = _approval_block(scenario)
    routing = scenario.expected_routing or {}
    contract = parse_semi_auto_operator_contract(scenario)

    expected_reply = bool(approval.get("expected_reply"))
    test_variant = str(approval.get("test_variant") or "normal").strip().lower()
    operator_action = _derive_legacy_operator_action(contract.operator_plan)
    if approval.get("operator_action") and contract.uses_legacy_operator_action:
        operator_action = str(approval.get("operator_action")).strip().lower()

    policy_authorization = str(routing.get("policy_authorization") or "").strip()
    pre_status = str(routing.get("job_status") or "").strip()
    has_secondary_pending = any(
        sec.expected_final_state == "remain_pending"
        for sec in contract.secondary_approvals
    )

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
        final_status = str(routing.get("final_job_status") or "manual_review")
    elif contract.operator_plan:
        pre_status = pre_status or "awaiting_approval"
        policy_authorization = policy_authorization or "approval_required"
        allow_operator = True
        pre_statuses = _APPROVAL_FIRST_PRE
        final_status = str(routing.get("final_job_status") or "awaiting_approval")
        final_statuses = (
            _TERMINAL_WITH_SECONDARY_PENDING
            if has_secondary_pending
            else frozenset({final_status})
        )
        expect_pending_pre = True
        decision_subsequence = REQUIRED_DECISION_SUBSEQUENCE
        expect_resolution = True
        expect_dup = any(step.expected_result == "idempotent" for step in contract.operator_plan)
        expect_stale = any(
            step.decision == "approve" and step.expected_http_status == 409
            for step in contract.operator_plan[1:]
        )
    else:
        pre_status = pre_status or "awaiting_approval"
        policy_authorization = policy_authorization or "approval_required"
        allow_operator = False
        pre_statuses = _APPROVAL_FIRST_PRE
        final_status = str(routing.get("final_job_status") or "manual_review")
        final_statuses = frozenset({final_status})
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
        final_job_status=final_status,
        expect_pending_approval_pre=expect_pending_pre,
        policy_authorization=policy_authorization,
        allow_operator_action=allow_operator,
        pre_action_success_statuses=pre_statuses,
        final_success_statuses=final_statuses,
        decision_subsequence=decision_subsequence,
        expect_approval_resolution=expect_resolution,
        expect_duplicate_idempotent=expect_dup,
        expect_stale_conflict=expect_stale,
        operator_plan=contract.operator_plan,
        secondary_approvals=contract.secondary_approvals,
        uses_legacy_operator_action=contract.uses_legacy_operator_action,
    )
