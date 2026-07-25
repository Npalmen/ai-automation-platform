"""Mutation determinism tests."""

from __future__ import annotations

from app.evaluation.generation.parent_loader import load_canonical_parents
from app.evaluation.mutations.engine import apply_mutations, generate_mutated_scenario
from app.evaluation.mutations.registry import MUTATION_REGISTRY


def test_mutation_determinism():
    _, parents = load_canonical_parents()
    parent = parents[0]
    first = generate_mutated_scenario(parent, mutation_ids=["typo"], seed=7)
    second = generate_mutated_scenario(parent, mutation_ids=["typo"], seed=7)
    assert first.provenance.scenario_hash == second.provenance.scenario_hash


def test_mutation_order_is_deterministic():
    _, parents = load_canonical_parents()
    parent = parents[0].scenario
    first, _ = apply_mutations(parent, ["typo", "missing_punctuation"], 3)
    second, _ = apply_mutations(parent, ["typo", "missing_punctuation"], 3)
    assert first.model_dump() == second.model_dump()


def test_all_mutations_registered():
    assert len(MUTATION_REGISTRY) >= 29
