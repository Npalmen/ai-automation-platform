"""Determinism tests for 2G scenario generation."""

from __future__ import annotations

import copy

from app.evaluation.dataset_manifest import compute_scenario_content_hash
from app.evaluation.generation.generator import GenerationRequest, generate_batch, generate_scenario
from app.evaluation.generation.manifest import build_generation_manifest, compute_generation_payload_hash
from app.evaluation.generation.parent_loader import load_canonical_parents
from app.evaluation.generation.provenance import GeneratedScenarioRecord


def test_same_seed_produces_identical_scenario_and_hash():
    _, parents = load_canonical_parents()
    parent = parents[0]
    request = GenerationRequest(
        parent_scenario_id=parent.scenario_id,
        template_id="tpl_paraphrase_opener_v1",
        seed=42,
    )
    first = generate_scenario(parent, request)
    second = generate_scenario(parent, request)
    assert first.provenance.scenario_hash == second.provenance.scenario_hash
    assert first.scenario.model_dump() == second.scenario.model_dump()


def test_different_seed_produces_different_hash():
    _, parents = load_canonical_parents()
    parent = parents[0]
    first = generate_scenario(
        parent,
        GenerationRequest(parent.scenario_id, "tpl_paraphrase_opener_v1", seed=1),
    )
    second = generate_scenario(
        parent,
        GenerationRequest(parent.scenario_id, "tpl_paraphrase_opener_v1", seed=2),
    )
    assert first.provenance.scenario_hash != second.provenance.scenario_hash


def test_different_template_produces_different_hash():
    _, parents = load_canonical_parents()
    parent = parents[0]
    first = generate_scenario(
        parent,
        GenerationRequest(parent.scenario_id, "tpl_paraphrase_opener_v1", seed=7),
    )
    second = generate_scenario(
        parent,
        GenerationRequest(parent.scenario_id, "tpl_paraphrase_subject_v1", seed=7),
    )
    assert first.provenance.scenario_hash != second.provenance.scenario_hash


def test_input_order_does_not_affect_manifest_hash():
    result_a = generate_batch(templates_per_parent=2, base_seed=0)
    requests_reversed = list(reversed(result_a.records))
    rebuilt_requests = [
        GenerationRequest(
            record.provenance.parent_scenario_id,
            record.provenance.template_id,
            record.provenance.template_version,
            record.provenance.seed,
        )
        for record in requests_reversed
    ]
    result_b = generate_batch(rebuilt_requests)
    manifest_a = build_generation_manifest(result_a)
    manifest_b = build_generation_manifest(result_b)
    assert manifest_a["generation_payload_hash"] == manifest_b["generation_payload_hash"]


def test_generated_at_does_not_affect_scenario_hash():
    _, parents = load_canonical_parents()
    parent = parents[0]
    request = GenerationRequest(parent.scenario_id, "tpl_paraphrase_opener_v1", seed=11)
    record = generate_scenario(parent, request)
    mutated = copy.deepcopy(record.scenario)
    duplicate = GeneratedScenarioRecord.from_scenario(
        mutated,
        parent_scenario_id=record.provenance.parent_scenario_id,
        template_id=record.provenance.template_id,
        template_version=record.provenance.template_version,
        seed=record.provenance.seed,
        variation_id=record.provenance.variation_id,
        generated_at="2099-01-01T00:00:00Z",
    )
    assert record.provenance.scenario_hash == duplicate.provenance.scenario_hash
    assert compute_scenario_content_hash(record.scenario) == compute_scenario_content_hash(duplicate.scenario)


def test_manifest_hash_is_stable_for_same_batch():
    result = generate_batch(templates_per_parent=2, base_seed=0)
    manifest_a = build_generation_manifest(result)
    manifest_b = build_generation_manifest(result)
    assert manifest_a["generation_payload_hash"] == manifest_b["generation_payload_hash"]
    payload = {k: v for k, v in manifest_a.items() if k != "generation_payload_hash"}
    assert compute_generation_payload_hash(payload) == manifest_a["generation_payload_hash"]
