"""Provenance and validation tests for 2G generation."""

from __future__ import annotations

import pytest

from app.evaluation.errors import ScenarioValidationError
from app.evaluation.generation.generator import GenerationRequest, generate_batch, generate_scenario
from app.evaluation.generation.parent_loader import load_canonical_parents
from app.evaluation.generation.provenance import GENERATOR_VERSION, SCENARIO_SCHEMA_VERSION


def test_parent_reference_required_in_provenance():
    result = generate_batch(templates_per_parent=2, base_seed=0)
    for record in result.records:
        assert record.provenance.parent_scenario_id
        assert record.scenario.generation.parent_scenario_id == record.provenance.parent_scenario_id


def test_unknown_parent_denied():
    _, parents = load_canonical_parents()
    with pytest.raises(ScenarioValidationError, match="Unknown parent_scenario_id"):
        generate_scenario(
            parents[0],
            GenerationRequest("S99_missing_parent", "tpl_paraphrase_opener_v1", seed=0),
        )


def test_unknown_template_denied():
    _, parents = load_canonical_parents()
    with pytest.raises(ScenarioValidationError, match="Unknown template_id"):
        generate_scenario(
            parents[0],
            GenerationRequest(parents[0].scenario_id, "tpl_missing_v1", seed=0),
        )


def test_unknown_template_version_denied():
    _, parents = load_canonical_parents()
    with pytest.raises(ScenarioValidationError, match="Unknown template_version"):
        generate_scenario(
            parents[0],
            GenerationRequest(parents[0].scenario_id, "tpl_paraphrase_opener_v1", template_version="v9", seed=0),
        )


def test_generated_scenarios_use_source_mode_generated():
    result = generate_batch(templates_per_parent=2, base_seed=0)
    for record in result.records:
        assert record.scenario.source_mode == "generated"
        assert record.provenance.source_mode == "generated"


def test_provenance_envelope_fields():
    result = generate_batch(templates_per_parent=2, base_seed=0)
    record = result.records[0]
    prov = record.provenance
    assert prov.scenario_schema_version == SCENARIO_SCHEMA_VERSION
    assert prov.generator_version == GENERATOR_VERSION
    assert prov.generator_type == "template"
    assert prov.generator_model is None
    assert prov.template_version == "v1"
    assert prov.scenario_hash
    assert prov.expected_outcome_hash
    assert len(prov.scenario_hash) == 64
    assert len(prov.expected_outcome_hash) == 64


def test_minimum_generated_volume():
    result = generate_batch(templates_per_parent=2, base_seed=0)
    _, parents = load_canonical_parents()
    assert len(parents) == 20
    assert len(result.records) == 40
    parent_ids = {record.provenance.parent_scenario_id for record in result.records}
    assert len(parent_ids) == 20
    for parent in parents:
        parent_records = [r for r in result.records if r.provenance.parent_scenario_id == parent.scenario_id]
        assert len(parent_records) == 2
        template_ids = {r.provenance.template_id for r in parent_records}
        assert len(template_ids) == 2


def test_scenario_hashes_unique():
    result = generate_batch(templates_per_parent=2, base_seed=0)
    hashes = [record.provenance.scenario_hash for record in result.records]
    assert len(hashes) == len(set(hashes))
