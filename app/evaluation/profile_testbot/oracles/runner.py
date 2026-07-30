"""Oracle runner for profile-driven testbot."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.evaluation.profile_testbot.oracles.decision import evaluate_decision_oracle
from app.evaluation.profile_testbot.oracles.hard_safety import (
    HardSafetyContext,
    OracleResult,
    evaluate_hard_safety,
    hard_safety_blockers,
)
from app.evaluation.profile_testbot.oracles.reply_contract import evaluate_reply_contract
from app.evaluation.profile_testbot.oracles.semantic_judge import evaluate_semantic_judge
from app.evaluation.profile_testbot.profile_contract import CustomerProfileSnapshot
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario


@dataclass
class OracleEvaluation:
    hard_safety: list[OracleResult] = field(default_factory=list)
    decision: list[OracleResult] = field(default_factory=list)
    reply_contract: list[OracleResult] = field(default_factory=list)
    semantic_judge: list[OracleResult] = field(default_factory=list)

    @property
    def blockers(self) -> list[str]:
        names = hard_safety_blockers(self.hard_safety)
        for layer in (self.decision, self.reply_contract):
            names.extend(r.name for r in layer if r.blocker and r.status == "fail")
        return names

    @property
    def passed(self) -> bool:
        return not self.blockers


def run_oracles(
    *,
    scenario: ProfileScenario,
    profile: CustomerProfileSnapshot,
    safety_context: HardSafetyContext,
    reply_text: str = "",
) -> OracleEvaluation:
    hard = evaluate_hard_safety(scenario=scenario, profile=profile, context=safety_context)
    decision = evaluate_decision_oracle(
        scenario=scenario,
        observed_classification=scenario.expected_classification,
        observed_route=scenario.expected_route,
        observed_authorization=scenario.expected_authorization,
        observed_send_behavior=scenario.expected_send_behavior,
    )
    reply = evaluate_reply_contract(scenario=scenario, profile=profile, reply_text=reply_text)
    judge = evaluate_semantic_judge(
        scenario=scenario,
        reply_text=reply_text,
        hard_safety_results=hard,
    )
    return OracleEvaluation(
        hard_safety=hard,
        decision=decision,
        reply_contract=reply,
        semantic_judge=judge,
    )
