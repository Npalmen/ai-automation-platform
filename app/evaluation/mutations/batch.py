"""Deterministic 160-scenario main batch builder."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.evaluation.errors import ScenarioValidationError
from app.evaluation.generation.parent_loader import load_canonical_parents
from app.evaluation.generation.provenance import GeneratedScenarioRecord
from app.evaluation.mutations.engine import generate_mutated_scenario
from app.evaluation.mutations.registry import (
    ALL_SCENARIO_CATEGORIES,
    BOUNDARY_MUTATION_IDS,
    GENERAL_MUTATION_IDS,
    MUTATION_REGISTRY,
    SECURITY_MUTATION_IDS,
)

MAIN_BATCH_SIZE = 160
CANONICAL_COUNT = 20
GENERAL_COUNT = 100
ADVERSARIAL_COUNT = 20
BOUNDARY_COUNT = 20


@dataclass(frozen=True)
class MainBatchResult:
    records: list[GeneratedScenarioRecord]
    parent_hashes: dict[str, str]
    category_counts: dict[str, int]
    mutation_counts: dict[str, int]


def _balanced_general_mutation_ids(count: int) -> list[str]:
    """Round-robin mutation IDs by category to keep category share under 20%."""
    by_category: dict[str, list[str]] = {}
    for mutation_id in GENERAL_MUTATION_IDS:
        category = MUTATION_REGISTRY[mutation_id].category
        by_category.setdefault(category, []).append(mutation_id)
    categories = sorted(by_category)
    ordered: list[str] = []
    index = 0
    while len(ordered) < count:
        category = categories[index % len(categories)]
        pool = by_category[category]
        ordered.append(pool[(len(ordered) // len(categories)) % len(pool)])
        index += 1
    return ordered


def _validate_batch_size(records: list[GeneratedScenarioRecord]) -> None:
    if len(records) != MAIN_BATCH_SIZE:
        raise ScenarioValidationError(
            f"Main batch must contain {MAIN_BATCH_SIZE} scenarios, got {len(records)}"
        )


def build_main_batch_records(
    manifest_path: Path | None = None,
) -> MainBatchResult:
    _, parents = load_canonical_parents(manifest_path)
    if len(parents) != CANONICAL_COUNT:
        raise ScenarioValidationError(f"Expected {CANONICAL_COUNT} canonical parents, got {len(parents)}")
    records: list[GeneratedScenarioRecord] = []
    seen_ids: set[str] = set()

    def _add(record: GeneratedScenarioRecord) -> None:
        if record.scenario.scenario_id in seen_ids:
            raise ScenarioValidationError(f"Duplicate scenario_id: {record.scenario.scenario_id}")
        seen_ids.add(record.scenario.scenario_id)
        records.append(record)

    for index, parent in enumerate(parents):
        _add(
            generate_mutated_scenario(
                parent,
                mutation_ids=[],
                seed=index,
                category_override="canonical",
                template_id="tpl_canonical_v1",
            )
        )

    general_mutations = _balanced_general_mutation_ids(GENERAL_COUNT)
    for index in range(GENERAL_COUNT):
        parent = parents[index % len(parents)]
        mutation_id = general_mutations[index]
        _add(
            generate_mutated_scenario(
                parent,
                mutation_ids=[mutation_id],
                seed=1000 + index,
                template_id="tpl_mutation_v1",
            )
        )

    for index in range(ADVERSARIAL_COUNT):
        parent = parents[index % len(parents)]
        mutation_id = SECURITY_MUTATION_IDS[index % len(SECURITY_MUTATION_IDS)]
        _add(
            generate_mutated_scenario(
                parent,
                mutation_ids=[mutation_id],
                seed=2000 + index,
                template_id="tpl_security_v1",
            )
        )

    for index in range(BOUNDARY_COUNT):
        parent = parents[index % len(parents)]
        mutation_id = BOUNDARY_MUTATION_IDS[index % len(BOUNDARY_MUTATION_IDS)]
        _add(
            generate_mutated_scenario(
                parent,
                mutation_ids=[mutation_id],
                seed=3000 + index,
                template_id="tpl_boundary_v1",
            )
        )

    _validate_batch_size(records)
    category_counts: dict[str, int] = {}
    mutation_counts: dict[str, int] = {}
    parent_descendants: dict[str, int] = {parent.scenario_id: 0 for parent in parents}
    for record in records:
        category = record.scenario.category
        category_counts[category] = category_counts.get(category, 0) + 1
        parent_descendants[record.provenance.parent_scenario_id] = (
            parent_descendants.get(record.provenance.parent_scenario_id, 0) + 1
        )
        for mutation_id in record.provenance.mutation_types:
            mutation_counts[mutation_id] = mutation_counts.get(mutation_id, 0) + 1

    missing_categories = ALL_SCENARIO_CATEGORIES - set(category_counts)
    if missing_categories:
        raise ScenarioValidationError(f"Main batch missing categories: {sorted(missing_categories)}")

    missing_mutations = set(MUTATION_REGISTRY) - set(mutation_counts)
    if missing_mutations:
        raise ScenarioValidationError(f"Main batch missing mutation families: {sorted(missing_mutations)}")

    for parent_id, count in parent_descendants.items():
        if count < 4:
            raise ScenarioValidationError(
                f"Parent {parent_id} has only {count} descendants; minimum is 4"
            )

    max_category = max(category_counts.values())
    if max_category > int(MAIN_BATCH_SIZE * 0.2) + 1:
        over = {category: count for category, count in category_counts.items() if count > 32}
        raise ScenarioValidationError(
            f"Category exceeds 20% without justification: {over}; counts={category_counts}"
        )

    parent_hashes = {parent.scenario_id: parent.content_hash for parent in parents}
    return MainBatchResult(
        records=records,
        parent_hashes=parent_hashes,
        category_counts=category_counts,
        mutation_counts=mutation_counts,
    )


def build_main_batch(manifest_path: Path | None = None) -> list[GeneratedScenarioRecord]:
    return build_main_batch_records(manifest_path).records
