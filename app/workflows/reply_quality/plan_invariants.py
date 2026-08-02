"""Hard invariants for CustomerReplyPlanV2 before rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

POLICY_VERSION = "plan_invariants_v1"


@dataclass(frozen=True)
class PlanInvariantResult:
    passed: bool
    violations: tuple[str, ...]
    policy_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "violations": list(self.violations),
            "policy_version": self.policy_version,
        }


def validate_selected_known_invariant(
    *,
    selected_questions: tuple[str, ...],
    already_known_facts: tuple[str, ...],
    extracted_known_fields: tuple[str, ...] = (),
) -> PlanInvariantResult:
    known = set(already_known_facts) | set(extracted_known_fields)
    conflicts = tuple(sorted(q for q in selected_questions if q in known))
    return PlanInvariantResult(
        passed=not conflicts,
        violations=tuple(f"selected_known_conflict:{c}" for c in conflicts),
        policy_version=POLICY_VERSION,
    )
