"""Contractual expected outcomes for automatic Gmail canary scenarios."""

from __future__ import annotations

from dataclasses import dataclass

from app.evaluation.live.assertions import (
    AUTOMATIC_HOLD_INTERLEAVED,
    AUTOMATIC_HOLD_WITH_DECISIONING_SUBSEQUENCE,
    OBSERVE_DECISION_SUBSEQUENCE_NO_DECISIONING,
    REQUIRED_DECISION_SUBSEQUENCE,
)
from app.evaluation.live.campaign.schemas import CampaignScenario

_AUTOMATIC_SAFE_TERMINAL = frozenset({"completed"})
_AUTOMATIC_HOLD_TERMINAL = frozenset({"manual_review"})


@dataclass(frozen=True)
class AutomaticExpectedOutcome:
    expected_reply: bool
    test_variant: str
    policy_authorization: str
    final_job_status: str
    expect_pending_approval: bool
    decision_subsequence: tuple[str, ...]
    interleaved_decision_types: frozenset[str]
    expect_execution_intent: bool
    expect_approval_resolution: bool
    automation_authorization: str
    success_terminal_statuses: frozenset[str]

    @property
    def is_negative_hold(self) -> bool:
        return self.test_variant == "negative_hold"


def _approval_block(scenario: CampaignScenario) -> dict:
    return dict(scenario.expected_approval or {})


def _automation_block(scenario: CampaignScenario) -> dict:
    approval = _approval_block(scenario)
    automation = approval.get("expected_automation") or {}
    if not isinstance(automation, dict):
        return {}
    return automation


def resolve_automatic_expected_outcome(
    scenario: CampaignScenario,
) -> AutomaticExpectedOutcome:
    """Derive automatic campaign poll and assertion expectations from scenario YAML."""
    approval = _approval_block(scenario)
    routing = scenario.expected_routing or {}
    automation = _automation_block(scenario)

    test_variant = str(approval.get("test_variant") or "automatic_safe").strip().lower()
    expected_reply = bool(approval.get("expected_reply"))
    automation_authorization = str(
        automation.get("authorization") or "auto_execute"
    ).strip()

    if test_variant == "negative_hold":
        job_type = str(scenario.job_type or "").strip().lower()
        if job_type in ("lead", "customer_inquiry"):
            decision_subsequence = AUTOMATIC_HOLD_WITH_DECISIONING_SUBSEQUENCE
            interleaved_decision_types = AUTOMATIC_HOLD_INTERLEAVED
        else:
            decision_subsequence = OBSERVE_DECISION_SUBSEQUENCE_NO_DECISIONING
            interleaved_decision_types = frozenset()
        return AutomaticExpectedOutcome(
            expected_reply=False,
            test_variant=test_variant,
            policy_authorization=str(
                routing.get("policy_authorization") or "hold_for_review"
            ),
            final_job_status=str(routing.get("final_job_status") or "manual_review"),
            expect_pending_approval=False,
            decision_subsequence=decision_subsequence,
            interleaved_decision_types=interleaved_decision_types,
            expect_execution_intent=False,
            expect_approval_resolution=False,
            automation_authorization=automation_authorization,
            success_terminal_statuses=_AUTOMATIC_HOLD_TERMINAL,
        )

    return AutomaticExpectedOutcome(
        expected_reply=expected_reply,
        test_variant=test_variant,
        policy_authorization=str(
            routing.get("policy_authorization") or "execution_allowed"
        ),
        final_job_status=str(routing.get("final_job_status") or "completed"),
        expect_pending_approval=False,
        decision_subsequence=REQUIRED_DECISION_SUBSEQUENCE,
        interleaved_decision_types=frozenset(),
        expect_execution_intent=True,
        expect_approval_resolution=False,
        automation_authorization=automation_authorization,
        success_terminal_statuses=_AUTOMATIC_SAFE_TERMINAL,
    )
