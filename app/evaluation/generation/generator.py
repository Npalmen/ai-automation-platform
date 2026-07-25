"""Seeded deterministic scenario generator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.evaluation.errors import ScenarioValidationError
from app.evaluation.generation.id_builder import build_scenario_id, build_variation_id
from app.evaluation.generation.parent_loader import CanonicalParent, get_parent_by_id, load_canonical_parents
from app.evaluation.generation.provenance import (
    GeneratedScenarioRecord,
    provenance_to_generation_contract,
)
from app.evaluation.generation.template_registry import (
    DEFAULT_TEMPLATE_IDS,
    assert_parent_compatible,
    get_template,
)
from app.evaluation.schema.scenario import ScenarioContract


@dataclass(frozen=True)
class GenerationRequest:
    parent_scenario_id: str
    template_id: str
    template_version: str = "v1"
    seed: int = 0


@dataclass(frozen=True)
class GenerationResult:
    records: list[GeneratedScenarioRecord]
    parent_hashes: dict[str, str]


def generate_scenario(
    parent: CanonicalParent,
    request: GenerationRequest,
) -> GeneratedScenarioRecord:
    if request.parent_scenario_id != parent.scenario_id:
        raise ScenarioValidationError(
            f"Unknown parent_scenario_id: {request.parent_scenario_id}"
        )
    template = get_template(request.template_id, request.template_version)
    assert_parent_compatible(template, parent.scenario)
    transformed = template.apply(parent.scenario, request.seed)
    scenario_id = build_scenario_id(parent.scenario_id, request.template_id, request.seed)
    variation_id = build_variation_id(request.template_id, request.seed)
    transformed.scenario_id = scenario_id
    transformed.source_mode = "generated"
    transformed.source = "generated"
    record = GeneratedScenarioRecord.from_scenario(
        transformed,
        parent_scenario_id=parent.scenario_id,
        template_id=request.template_id,
        template_version=request.template_version,
        seed=request.seed,
        variation_id=variation_id,
        mutation_parameters={
            "template_category": template.category,
            "variable_schema": dict(template.variable_schema),
        },
    )
    transformed.generation = provenance_to_generation_contract(record.provenance)
    record = GeneratedScenarioRecord.from_scenario(
        transformed,
        parent_scenario_id=parent.scenario_id,
        template_id=request.template_id,
        template_version=request.template_version,
        seed=request.seed,
        variation_id=variation_id,
        mutation_parameters=record.provenance.mutation_parameters,
        generated_at=record.provenance.generated_at,
    )
    return record


def build_default_requests(
    parents: list[CanonicalParent],
    *,
    templates_per_parent: int = 2,
    base_seed: int = 0,
) -> list[GenerationRequest]:
    if templates_per_parent > len(DEFAULT_TEMPLATE_IDS):
        raise ScenarioValidationError("templates_per_parent exceeds available templates")
    requests: list[GenerationRequest] = []
    for parent_index, parent in enumerate(parents):
        for template_index in range(templates_per_parent):
            template_id = DEFAULT_TEMPLATE_IDS[template_index]
            seed = base_seed + parent_index * 100 + template_index
            requests.append(
                GenerationRequest(
                    parent_scenario_id=parent.scenario_id,
                    template_id=template_id,
                    seed=seed,
                )
            )
    return requests


def generate_batch(
    requests: list[GenerationRequest] | None = None,
    *,
    manifest_path: Path | None = None,
    templates_per_parent: int = 2,
    base_seed: int = 0,
) -> GenerationResult:
    _, parents = load_canonical_parents(manifest_path)
    parent_map = {parent.scenario_id: parent for parent in parents}
    parent_hashes = {parent.scenario_id: parent.content_hash for parent in parents}
    effective_requests = requests or build_default_requests(
        parents,
        templates_per_parent=templates_per_parent,
        base_seed=base_seed,
    )
    records: list[GeneratedScenarioRecord] = []
    seen_ids: set[str] = set()
    for request in effective_requests:
        parent = parent_map.get(request.parent_scenario_id)
        if parent is None:
            parent = get_parent_by_id(parents, request.parent_scenario_id)
        record = generate_scenario(parent, request)
        if record.scenario.scenario_id in seen_ids:
            raise ScenarioValidationError(
                f"Duplicate generated scenario_id: {record.scenario.scenario_id}"
            )
        seen_ids.add(record.scenario.scenario_id)
        records.append(record)
    return GenerationResult(records=records, parent_hashes=parent_hashes)


def record_to_scenario(record: GeneratedScenarioRecord) -> ScenarioContract:
    return record.scenario
