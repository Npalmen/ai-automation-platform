"""160-scenario main batch smoke tests."""

from __future__ import annotations

import socket

from app.evaluation.mutations.batch import (
    ADVERSARIAL_COUNT,
    BOUNDARY_COUNT,
    CANONICAL_COUNT,
    GENERAL_COUNT,
    MAIN_BATCH_SIZE,
    build_main_batch_records,
)
from app.evaluation.mutations.registry import ALL_SCENARIO_CATEGORIES, MUTATION_REGISTRY


def test_main_batch_exact_size_and_composition():
    result = build_main_batch_records()
    assert len(result.records) == MAIN_BATCH_SIZE
    assert CANONICAL_COUNT + GENERAL_COUNT + ADVERSARIAL_COUNT + BOUNDARY_COUNT == MAIN_BATCH_SIZE


def test_main_batch_category_and_mutation_coverage():
    result = build_main_batch_records()
    assert set(result.category_counts) == set(ALL_SCENARIO_CATEGORIES)
    assert set(result.mutation_counts) == set(MUTATION_REGISTRY)


def test_main_batch_parent_descendants_minimum_four():
    result = build_main_batch_records()
    for parent_id, count in result.parent_hashes.items():
        descendants = [r for r in result.records if r.provenance.parent_scenario_id == parent_id]
        assert len(descendants) >= 4, parent_id


def test_main_batch_no_category_exceeds_twenty_percent():
    result = build_main_batch_records()
    for category, count in result.category_counts.items():
        assert count <= 33, f"{category}={count}"


def test_main_batch_deterministic():
    first = build_main_batch_records()
    second = build_main_batch_records()
    assert [r.provenance.scenario_hash for r in first.records] == [
        r.provenance.scenario_hash for r in second.records
    ]


def test_main_batch_no_network(monkeypatch):
    def _blocked(*_args, **_kwargs):
        raise OSError("network blocked")

    monkeypatch.setattr(socket, "socket", _blocked)
    result = build_main_batch_records()
    assert len(result.records) == MAIN_BATCH_SIZE
