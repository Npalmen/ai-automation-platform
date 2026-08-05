"""Hermetic coworker reply qualification (Gate R1)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from app.evaluation.profile_testbot.coworker_quality_oracles import (
    COWORKER_THRESHOLDS,
    THRESHOLD_VERSION,
    aggregate_coworker_results,
    evaluate_coworker_reply_oracles,
    template_similarity_ratio,
)
from app.evaluation.profile_testbot.coworker_reply_dataset import (
    COWORKER_SCENARIO_TARGET,
    build_coworker_dataset_manifest,
    generate_coworker_reply_dataset,
    validate_coworker_dataset_gates,
)
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario
from app.workflows.reply_quality.provenance import ReplyRenderProvenance

HERMETIC_COWORKER_CONTRACT_VERSION = "coworker_reply_hermetic_v1"


@dataclass
class CoworkerScenarioResult:
    scenario_id: str
    family: str
    passed: bool
    blockers: list[str] = field(default_factory=list)


@dataclass
class HermeticCoworkerQualificationResult:
    overall_status: str
    dataset_version: str
    threshold_version: str
    scenario_count: int
    manifest_hash: str
    hard_safety_pass_rate: float
    template_similarity: float
    fallback_rate: float
    gate_failures: list[str] = field(default_factory=list)
    scenario_results: list[CoworkerScenarioResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_status": self.overall_status,
            "dataset_version": self.dataset_version,
            "threshold_version": self.threshold_version,
            "scenario_count": self.scenario_count,
            "manifest_hash": self.manifest_hash,
            "hard_safety_pass_rate": self.hard_safety_pass_rate,
            "template_similarity": self.template_similarity,
            "fallback_rate": self.fallback_rate,
            "gate_failures": self.gate_failures,
            "contract_version": HERMETIC_COWORKER_CONTRACT_VERSION,
            "thresholds": COWORKER_THRESHOLDS,
        }


def _render_scenario_reply(
    scenario: ProfileScenario,
    *,
    signature_name: str = "Niklas",
) -> tuple[str, dict[str, Any] | None, ReplyRenderProvenance | None]:
    """Hermetic/default R1 render path (keeps deterministic fallback behavior)."""
    from app.evaluation.profile_testbot.qualification.qualification_scenario_plan import (
        build_qualification_scenario_inputs,
        build_qualification_scenario_reply_plan,
    )
    from app.workflows.reply_quality.renderer import render_coworker_reply_with_validation

    plan_v2 = build_qualification_scenario_reply_plan(
        scenario,
        signature_name=signature_name,
    )
    if plan_v2 is None:
        return "", None, None

    # Preserve hermetic eval markers used by downstream pipeline helpers.
    _input_data, _entities = build_qualification_scenario_inputs(scenario)
    prev = os.environ.get("DIGITAL_COWORKER_REPLY_ENABLED")
    os.environ["DIGITAL_COWORKER_REPLY_ENABLED"] = "true"
    try:
        render_result = render_coworker_reply_with_validation(plan_v2)
    finally:
        if prev is None:
            os.environ.pop("DIGITAL_COWORKER_REPLY_ENABLED", None)
        else:
            os.environ["DIGITAL_COWORKER_REPLY_ENABLED"] = prev
    return render_result.body, plan_v2.to_dict(), render_result.provenance


def run_hermetic_coworker_reply_qualification(
    *,
    profile_id: str = "niklas-demo-live-eval-v1",
    seed: int = 0,
) -> HermeticCoworkerQualificationResult:
    profile = load_customer_profile(profile_id)
    scenarios = generate_coworker_reply_dataset(profile, seed=seed)
    gate_failures = validate_coworker_dataset_gates(scenarios)
    manifest = build_coworker_dataset_manifest(scenarios)

    if len(scenarios) != COWORKER_SCENARIO_TARGET:
        gate_failures.append(f"scenario_count {len(scenarios)} != {COWORKER_SCENARIO_TARGET}")

    scenario_results: list[CoworkerScenarioResult] = []
    bodies_for_similarity: list[str] = []
    families_for_similarity: list[str] = []
    fallback_count = 0
    evaluated = 0

    for scenario in scenarios:
        body, plan_dict, provenance = _render_scenario_reply(scenario, signature_name="Niklas")
        if not (scenario.customer_state_setup or {}).get("oracle_applicability", {}).get(
            "coworker_reply_quality", True
        ):
            scenario_results.append(
                CoworkerScenarioResult(scenario.scenario_id, scenario.family, True, [])
            )
            continue

        evaluated += 1
        if provenance and provenance.use_fallback:
            fallback_count += 1
        bodies_for_similarity.append(body)
        families_for_similarity.append(scenario.family)

        from app.workflows.reply_quality.plan_v2 import CustomerReplyPlanV2
        from app.workflows.reply_quality.thread_context import ThreadReplyContext

        plan_v2 = None
        if plan_dict:
            thread_raw = plan_dict.get("thread_context") or {}
            plan_v2 = CustomerReplyPlanV2(
                response_objective=plan_dict["response_objective"],
                acknowledgement_mode=plan_dict["acknowledgement_mode"],
                service_family=plan_dict["service_family"],
                business_intent=plan_dict["business_intent"],
                verified_facts=tuple(plan_dict.get("verified_facts") or []),
                facts_not_allowed_to_repeat=tuple(plan_dict.get("facts_not_allowed_to_repeat") or []),
                selected_questions=tuple(plan_dict.get("selected_questions") or []),
                selected_question_labels=tuple(plan_dict.get("selected_question_labels") or []),
                next_step_statement=plan_dict["next_step_statement"],
                commitment_constraints=tuple(plan_dict.get("commitment_constraints") or []),
                tone_profile=plan_dict["tone_profile"],
                language=plan_dict["language"],
                greeting=plan_dict["greeting"],
                signature_name=plan_dict["signature_name"],
                salutation_strategy=plan_dict["salutation_strategy"],
                closing_strategy=plan_dict["closing_strategy"],
                thread_context=ThreadReplyContext(
                    thread_state=thread_raw.get("thread_state", "new_thread"),
                    is_first_contact=bool(thread_raw.get("is_first_contact", True)),
                    is_continuation=bool(thread_raw.get("is_continuation", False)),
                    prior_operator_reply=bool(thread_raw.get("prior_operator_reply", False)),
                    prior_safe_ack=bool(thread_raw.get("prior_safe_ack", False)),
                    supplied_facts=tuple(thread_raw.get("supplied_facts") or ()),
                    summary=thread_raw.get("summary", ""),
                    policy_version=thread_raw.get("policy_version", "thread_context_v1"),
                ),
                rendering_constraints=tuple(plan_dict.get("rendering_constraints") or ()),
                fallback_reason=plan_dict.get("fallback_reason"),
                evidence=tuple(plan_dict.get("evidence") or ()),
                playbook_id=plan_dict["playbook_id"],
                policy_version=plan_dict["policy_version"],
                acknowledgement_statement=str(plan_dict.get("acknowledgement_statement") or ""),
                question_surface_labels=tuple(plan_dict.get("question_surface_labels") or []),
                location_phrase=plan_dict.get("location_phrase"),
                case_reference_phrase=plan_dict.get("case_reference_phrase"),
                language_decision_evidence=tuple(plan_dict.get("language_decision_evidence") or []),
            )

        oracle_results = evaluate_coworker_reply_oracles(
            scenario=scenario,
            reply_body=body,
            plan_v2=plan_v2,
            provenance=provenance,
        )
        agg = aggregate_coworker_results(oracle_results)
        scenario_results.append(
            CoworkerScenarioResult(
                scenario_id=scenario.scenario_id,
                family=scenario.family,
                passed=agg["passed"],
                blockers=agg["blockers"],
            )
        )
        if agg["blockers"]:
            gate_failures.append(f"{scenario.scenario_id}: {agg['blockers']}")

    template_similarity = template_similarity_ratio(
        bodies_for_similarity,
        families=families_for_similarity,
    )
    fallback_rate = fallback_count / max(evaluated, 1)
    if template_similarity > COWORKER_THRESHOLDS["template_similarity_max"]:
        gate_failures.append(
            f"template_similarity {template_similarity:.3f} > {COWORKER_THRESHOLDS['template_similarity_max']}"
        )
    if fallback_rate > COWORKER_THRESHOLDS["fallback_rate_max"]:
        gate_failures.append(
            f"fallback_rate {fallback_rate:.3f} > {COWORKER_THRESHOLDS['fallback_rate_max']}"
        )

    failed = [r for r in scenario_results if not r.passed]
    if failed:
        gate_failures.append(f"{len(failed)} coworker scenario(s) failed")

    overall = "PASS" if not gate_failures else "FAIL"
    return HermeticCoworkerQualificationResult(
        overall_status=overall,
        dataset_version=manifest.dataset_version,
        threshold_version=THRESHOLD_VERSION,
        scenario_count=len(scenarios),
        manifest_hash=manifest.manifest_hash,
        hard_safety_pass_rate=1.0 if not gate_failures else 0.0,
        template_similarity=template_similarity,
        fallback_rate=fallback_rate,
        gate_failures=gate_failures,
        scenario_results=scenario_results,
    )
