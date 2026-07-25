"""Contractual expected outcomes for observe-mode campaign scenarios."""

from __future__ import annotations

from dataclasses import dataclass

from app.evaluation.live.assertions import (
    OBSERVE_DECISION_SUBSEQUENCE_NO_DECISIONING,
    REQUIRED_DECISION_SUBSEQUENCE,
)
from app.evaluation.live.campaign.schemas import CampaignScenario

_APPROVAL_FIRST_TERMINAL = frozenset({"awaiting_approval"})
_SAFE_HOLD_TERMINAL = frozenset({"manual_review"})


@dataclass(frozen=True)
class ObserveExpectedOutcome:
    job_status: str
    policy_authorization: str
    expect_pending_approval: bool
    success_terminal_statuses: frozenset[str]
    decision_subsequence: tuple[str, ...]

    @property
    def is_safe_hold(self) -> bool:
        return self.job_status == "manual_review"


def resolve_observe_expected_outcome(scenario: CampaignScenario) -> ObserveExpectedOutcome:
    """Derive poll/assertion expectations from scenario YAML contract."""
    routing = scenario.expected_routing or {}
    approval = scenario.expected_approval or {}

    job_status = str(routing.get("job_status") or "").strip()
    policy_authorization = str(routing.get("policy_authorization") or "").strip()

    if approval.get("expected") is True or approval.get("pending") is True:
        expect_pending_approval = True
    elif approval.get("expected") is False or approval.get("pending") is False:
        expect_pending_approval = False
    else:
        expect_pending_approval = job_status == "awaiting_approval"

    if not job_status:
        if scenario.job_type in ("unknown",):
            job_status = "manual_review"
            policy_authorization = policy_authorization or "hold_for_review"
            expect_pending_approval = False
        elif scenario.job_type == "invoice":
            job_status = "manual_review"
            policy_authorization = policy_authorization or "hold_for_review"
            expect_pending_approval = False
        else:
            job_status = "awaiting_approval"
            policy_authorization = policy_authorization or "approval_required"
            expect_pending_approval = True

    if not policy_authorization:
        policy_authorization = (
            "hold_for_review" if job_status == "manual_review" else "approval_required"
        )

    success_statuses = (
        _SAFE_HOLD_TERMINAL if job_status == "manual_review" else _APPROVAL_FIRST_TERMINAL
    )

    if scenario.job_type in ("invoice", "unknown"):
        decision_subsequence = OBSERVE_DECISION_SUBSEQUENCE_NO_DECISIONING
    else:
        decision_subsequence = REQUIRED_DECISION_SUBSEQUENCE

    return ObserveExpectedOutcome(
        job_status=job_status,
        policy_authorization=policy_authorization,
        expect_pending_approval=expect_pending_approval,
        success_terminal_statuses=success_statuses,
        decision_subsequence=decision_subsequence,
    )
