"""Mutation application engine."""

from __future__ import annotations

import copy

from app.evaluation.errors import ScenarioValidationError
from app.evaluation.generation.id_builder import build_scenario_id, build_variation_id
from app.evaluation.generation.parent_loader import CanonicalParent
from app.evaluation.generation.provenance import GeneratedScenarioRecord, provenance_to_generation_contract
from app.evaluation.mutations.invariants import (
    assert_injection_is_data_only,
    assert_job_type_unchanged,
    assert_no_external_writes,
)
from app.evaluation.mutations.registry import MUTATION_VERSION, get_mutation
from app.evaluation.schema.scenario import ScenarioContract


def apply_mutations(
    parent: ScenarioContract,
    mutation_ids: list[str],
    seed: int,
) -> tuple[ScenarioContract, list[str]]:
    current = copy.deepcopy(parent)
    applied: list[str] = []
    for mutation_id in mutation_ids:
        before = copy.deepcopy(current)
        definition = get_mutation(mutation_id)
        current = definition.apply(current, seed)
        if definition.preserves_job_type:
            assert_job_type_unchanged(before, current)
        assert_no_external_writes(current)
        if definition.category == "injection_attempt":
            assert_injection_is_data_only(current)
        applied.append(mutation_id)
    return current, applied


def generate_mutated_scenario(
    parent: CanonicalParent,
    *,
    mutation_ids: list[str],
    seed: int,
    category_override: str | None = None,
    template_id: str = "mut_v1",
) -> GeneratedScenarioRecord:
    if not mutation_ids:
        scenario = copy.deepcopy(parent.scenario)
        scenario.category = category_override or "canonical"
        tags = list(scenario.tags)
        for tag in ("generated", "canonical"):
            if tag not in tags:
                tags.append(tag)
        scenario.tags = tags
        applied: list[str] = []
    else:
        scenario, applied = apply_mutations(parent.scenario, mutation_ids, seed)
        if category_override:
            scenario.category = category_override
    scenario_id = build_scenario_id(
        parent.scenario_id,
        f"{template_id}_{'_'.join(applied) if applied else 'canonical'}",
        seed,
    )
    variation_id = build_variation_id(template_id, seed)
    scenario.scenario_id = scenario_id
    scenario.source_mode = "generated"
    scenario.source = "generated"
    record = GeneratedScenarioRecord.from_scenario(
        scenario,
        parent_scenario_id=parent.scenario_id,
        template_id=template_id,
        template_version="v1",
        seed=seed,
        variation_id=variation_id,
        mutation_types=applied,
        mutation_parameters={"mutation_version": MUTATION_VERSION},
        generator_type="mutation" if applied else "template",
    )
    scenario.generation = provenance_to_generation_contract(record.provenance)
    return GeneratedScenarioRecord.from_scenario(
        scenario,
        parent_scenario_id=parent.scenario_id,
        template_id=template_id,
        template_version="v1",
        seed=seed,
        variation_id=variation_id,
        mutation_types=applied,
        mutation_parameters=record.provenance.mutation_parameters,
        generator_type="mutation" if applied else "template",
        generated_at=record.provenance.generated_at,
    )
