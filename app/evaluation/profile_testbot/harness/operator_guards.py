"""Operator guards requiring oracle PASS before approval."""

from __future__ import annotations

from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.profile_testbot.oracles.runner import OracleEvaluation
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario


def require_oracle_pass_for_operator_action(
    *,
    scenario: ProfileScenario,
    evaluation: OracleEvaluation,
) -> None:
    if scenario.expected_send_behavior != "send_after_approval":
        raise LiveEvalSafetyError(
            f"operator action blocked: scenario {scenario.scenario_id} expects {scenario.expected_send_behavior}"
        )
    if not evaluation.passed:
        raise LiveEvalSafetyError(
            f"operator action blocked: oracle failures {evaluation.blockers}"
        )
