"""2G provenance envelope for generated scenarios."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.evaluation.dataset_manifest import canonical_json_bytes, compute_scenario_content_hash
from app.evaluation.schema.scenario import GenerationContract, ScenarioContract

GENERATOR_VERSION = "2g-generator-v1"
SCENARIO_SCHEMA_VERSION = "2g.scenario.v1"
CANONICALIZATION_VERSION = "semantic-json-v2"


class ScenarioProvenance(BaseModel):
    scenario_id: str
    scenario_schema_version: str = SCENARIO_SCHEMA_VERSION
    parent_scenario_id: str
    template_id: str
    template_version: str
    seed: int
    variation_id: str
    mutation_types: list[str] = Field(default_factory=list)
    mutation_parameters: dict[str, Any] = Field(default_factory=dict)
    generator_type: Literal["template", "mutation"] = "template"
    generator_version: str = GENERATOR_VERSION
    generator_model: str | None = None
    generator_prompt_version: str | None = None
    source_mode: Literal["generated"] = "generated"
    generated_at: str = ""
    scenario_hash: str = ""
    expected_outcome_hash: str = ""


class GeneratedScenarioRecord(BaseModel):
    scenario: ScenarioContract
    provenance: ScenarioProvenance

    @classmethod
    def from_scenario(
        cls,
        scenario: ScenarioContract,
        *,
        parent_scenario_id: str,
        template_id: str,
        template_version: str,
        seed: int,
        variation_id: str,
        mutation_types: list[str] | None = None,
        mutation_parameters: dict[str, Any] | None = None,
        generator_type: Literal["template", "mutation"] = "template",
        generated_at: str | None = None,
    ) -> GeneratedScenarioRecord:
        scenario_hash = compute_scenario_content_hash(scenario)
        expected_outcome_hash = compute_expected_outcome_hash(scenario)
        provenance = ScenarioProvenance(
            scenario_id=scenario.scenario_id,
            parent_scenario_id=parent_scenario_id,
            template_id=template_id,
            template_version=template_version,
            seed=seed,
            variation_id=variation_id,
            mutation_types=mutation_types or [],
            mutation_parameters=mutation_parameters or {},
            generator_type=generator_type,
            generated_at=generated_at
            or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            scenario_hash=scenario_hash,
            expected_outcome_hash=expected_outcome_hash,
        )
        return cls(scenario=scenario, provenance=provenance)


def compute_expected_outcome_hash(scenario: ScenarioContract) -> str:
    payload = scenario.expect.model_dump(mode="json")
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def provenance_to_generation_contract(provenance: ScenarioProvenance) -> GenerationContract:
    return GenerationContract(
        parent_scenario_id=provenance.parent_scenario_id,
        template_id=provenance.template_id,
        seed=provenance.seed,
        variation_id=provenance.variation_id,
        generator_model=provenance.generator_model,
        generator_prompt_version=provenance.generator_prompt_version,
        mutation_types=list(provenance.mutation_types),
    )
