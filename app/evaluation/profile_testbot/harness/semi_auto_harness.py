"""Operator harness for profile semi-auto live execution."""

from __future__ import annotations

from dataclasses import dataclass

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.profile_testbot.harness.operator_guards import require_oracle_pass_for_operator_action
from app.evaluation.profile_testbot.oracles.runner import OracleEvaluation
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario


@dataclass(frozen=True)
class HarnessDecision:
    decision: str
    reason: str
    approved: bool


def evaluate_harness_decision(
    *,
    scenario: ProfileScenario,
    evaluation: OracleEvaluation,
    approval_state: str,
    send_budget_remaining: int,
    operation_id_valid: bool,
    recipient_allowlisted: bool,
) -> HarnessDecision:
    if scenario.expected_send_behavior != "send_after_approval":
        return HarnessDecision(
            decision="hold",
            reason=f"expected behavior {scenario.expected_send_behavior}",
            approved=False,
        )
    if not operation_id_valid:
        return HarnessDecision(decision="reject", reason="invalid operation id", approved=False)
    if not recipient_allowlisted:
        return HarnessDecision(decision="reject", reason="recipient not allowlisted", approved=False)
    if send_budget_remaining < 1:
        return HarnessDecision(decision="reject", reason="send budget exhausted", approved=False)
    if approval_state != "pending":
        return HarnessDecision(
            decision="reject",
            reason=f"unexpected approval_state={approval_state}",
            approved=False,
        )
    if not evaluation.passed:
        return HarnessDecision(
            decision="reject",
            reason=f"oracle failures: {evaluation.blockers}",
            approved=False,
        )
    try:
        require_oracle_pass_for_operator_action(scenario=scenario, evaluation=evaluation)
    except LiveEvalSafetyError as exc:
        return HarnessDecision(decision="reject", reason=str(exc), approved=False)
    return HarnessDecision(decision="approve", reason="oracle pass", approved=True)
