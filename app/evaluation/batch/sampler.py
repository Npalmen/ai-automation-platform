"""Batch scenario sampling for Kapitel 2G."""

from __future__ import annotations

from dataclasses import dataclass

from app.evaluation.errors import ScenarioValidationError
from app.evaluation.generation.parent_loader import load_canonical_parents
from app.evaluation.generation.provenance import GeneratedScenarioRecord
from app.evaluation.mutations.batch import MAIN_BATCH_SIZE, build_main_batch_records
from app.evaluation.mutations.engine import generate_mutated_scenario
from app.evaluation.mutations.registry import GENERAL_MUTATION_IDS, SECURITY_MUTATION_IDS

PR_BATCH_SIZE = 60
PR_CANONICAL_COUNT = 20
PR_SECURITY_COUNT = 20
PR_MUTATION_COUNT = 20


@dataclass(frozen=True)
class PrBatchResult:
    records: list[GeneratedScenarioRecord]
    parent_hashes: dict[str, str]


def _balanced_general_ids(count: int) -> list[str]:
    by_category: dict[str, list[str]] = {}
    from app.evaluation.mutations.registry import MUTATION_REGISTRY

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


def build_pr_batch_records() -> PrBatchResult:
    _, parents = load_canonical_parents()
    records: list[GeneratedScenarioRecord] = []
    seen: set[str] = set()

    def _add(record: GeneratedScenarioRecord) -> None:
        if record.scenario.scenario_id in seen:
            raise ScenarioValidationError(f"Duplicate scenario_id: {record.scenario.scenario_id}")
        seen.add(record.scenario.scenario_id)
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

    for index in range(PR_SECURITY_COUNT):
        parent = parents[index % len(parents)]
        mutation_id = SECURITY_MUTATION_IDS[index % len(SECURITY_MUTATION_IDS)]
        _add(
            generate_mutated_scenario(
                parent,
                mutation_ids=[mutation_id],
                seed=4000 + index,
                template_id="tpl_pr_security_v1",
            )
        )

    general_ids = _balanced_general_ids(PR_MUTATION_COUNT)
    for index, mutation_id in enumerate(general_ids):
        parent = parents[index % len(parents)]
        _add(
            generate_mutated_scenario(
                parent,
                mutation_ids=[mutation_id],
                seed=5000 + index,
                template_id="tpl_pr_mutation_v1",
            )
        )

    if len(records) != PR_BATCH_SIZE:
        raise ScenarioValidationError(f"PR batch size must be {PR_BATCH_SIZE}, got {len(records)}")
    parent_hashes = {parent.scenario_id: parent.content_hash for parent in parents}
    return PrBatchResult(records=records, parent_hashes=parent_hashes)


def build_main_batch_for_eval() -> list[GeneratedScenarioRecord]:
    return build_main_batch_records().records
