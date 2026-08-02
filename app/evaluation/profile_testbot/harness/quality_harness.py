"""Harness decision for live inbox quality campaigns."""

from __future__ import annotations

from dataclasses import dataclass

from app.evaluation.profile_testbot.oracles.quality_result import QualityOracleEvaluation
from app.evaluation.profile_testbot.qualification.constants import SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario


@dataclass(frozen=True)
class QualityHarnessDecision:
    decision: str
    reason: str
    approved: bool


def evaluate_quality_harness_decision(
    *,
    scenario: ProfileScenario,
    evaluation: QualityOracleEvaluation,
    approval_state: str,
    send_budget_remaining: int,
    recipient_allowlisted: bool,
) -> QualityHarnessDecision:
    if scenario.expected_send_behavior not in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND:
        return QualityHarnessDecision(
            decision="hold",
            reason=f"expected behavior {scenario.expected_send_behavior}",
            approved=False,
        )
    if not recipient_allowlisted:
        return QualityHarnessDecision(
            decision="reject",
            reason="recipient not allowlisted",
            approved=False,
        )
    if send_budget_remaining < 1:
        return QualityHarnessDecision(
            decision="reject",
            reason="send budget exhausted",
            approved=False,
        )
    if approval_state != "pending":
        return QualityHarnessDecision(
            decision="reject",
            reason=f"unexpected approval_state={approval_state}",
            approved=False,
        )
    if not evaluation.passed:
        return QualityHarnessDecision(
            decision="reject",
            reason=f"quality oracle failures: {evaluation.blockers}",
            approved=False,
        )
    return QualityHarnessDecision(decision="approve", reason="quality oracle pass", approved=True)
