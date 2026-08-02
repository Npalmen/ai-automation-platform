"""Hard invariants for CustomerReplyPlanV2 before rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.workflows.reply_quality.fact_evidence import (
    ADDRESS_STATE_PROPERTY_ADDRESS,
    FactEvidenceSnapshot,
    build_fact_evidence,
)
from app.workflows.reply_quality.semantic_fact_predicates import existing_solar_verified

POLICY_VERSION = "plan_invariants_v2"

_EXCLUSION_ONLY_REASONS = frozenset(
    {
        "no_verified_solar",
        "battery_retrofit",
        "consultation_intent",
        "conditional_dependency",
        "question_budget",
        "deferred_question",
        "not_applicable",
    }
)


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


def validate_evidence_based_known_facts(
    *,
    already_known_facts: tuple[str, ...],
    evidence: FactEvidenceSnapshot,
    selection_reasons: tuple[str, ...] = (),
) -> PlanInvariantResult:
    violations: list[str] = []
    evidenced = set(evidence.evidenced_question_fields)
    for field in already_known_facts:
        if field not in evidenced:
            violations.append(f"verified_fact_requires_positive_evidence:{field}")

    for reason in selection_reasons:
        if not reason.startswith("exclude:"):
            continue
        parts = reason.split(":")
        if len(parts) < 3:
            continue
        field, cause = parts[1], parts[2]
        if cause in _EXCLUSION_ONLY_REASONS and field in already_known_facts:
            violations.append(f"excluded_question_does_not_imply_known_fact:{field}:{cause}")

    if (
        evidence.address_state.state != ADDRESS_STATE_PROPERTY_ADDRESS
        and "address" in already_known_facts
    ):
        violations.append("city_address_granularity:city_treated_as_address")

    solar_fields = {"existing_solar_system", "current_inverter"}
    if solar_fields.intersection(already_known_facts) and not existing_solar_verified(
        set(evidence.fact_ids), evidenced
    ):
        violations.append("verified_fact_requires_positive_evidence:solar_without_confirmation")

    return PlanInvariantResult(
        passed=not violations,
        violations=tuple(violations),
        policy_version=POLICY_VERSION,
    )


def validate_pipeline_playbook_consistency(
    *,
    playbook_id: str,
    service_family: str,
    next_step_service_family: str,
    information_plan_playbook_id: str | None = None,
) -> PlanInvariantResult:
    violations: list[str] = []
    if next_step_service_family != service_family:
        violations.append(
            f"pipeline_playbook_consistency:next_step_family:{next_step_service_family}!={service_family}"
        )
    if information_plan_playbook_id and information_plan_playbook_id != playbook_id:
        violations.append(
            f"pipeline_playbook_consistency:info_plan:{information_plan_playbook_id}!={playbook_id}"
        )
    return PlanInvariantResult(
        passed=not violations,
        violations=tuple(violations),
        policy_version=POLICY_VERSION,
    )


def build_plan_evidence_snapshot(
    *,
    input_data: dict[str, Any],
    entities: dict[str, Any] | None = None,
    known_fact_fields: tuple[str, ...] = (),
) -> FactEvidenceSnapshot:
    return build_fact_evidence(
        input_data=input_data,
        entities=entities,
        known_fact_fields=known_fact_fields,
    )
