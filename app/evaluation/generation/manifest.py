"""Generation manifest builder for Kapitel 2G."""

from __future__ import annotations

import hashlib
from typing import Any

from app.evaluation.dataset_manifest import canonical_json_bytes
from app.evaluation.generation.generator import GenerationResult
from app.evaluation.generation.provenance import CANONICALIZATION_VERSION, GENERATOR_VERSION

MANIFEST_SCHEMA_VERSION = "2g.generation-manifest.v1"


def _manifest_payload(
    result: GenerationResult,
    *,
    baseline_git_sha: str | None = None,
) -> dict[str, Any]:
    scenarios = []
    for record in sorted(result.records, key=lambda item: item.provenance.scenario_id):
        prov = record.provenance
        scenarios.append(
            {
                "scenario_id": prov.scenario_id,
                "scenario_hash": prov.scenario_hash,
                "expected_outcome_hash": prov.expected_outcome_hash,
                "parent_scenario_id": prov.parent_scenario_id,
                "template_id": prov.template_id,
                "template_version": prov.template_version,
                "seed": prov.seed,
                "variation_id": prov.variation_id,
                "generator_type": prov.generator_type,
                "generator_version": prov.generator_version,
                "mutation_types": prov.mutation_types,
                "mutation_parameters": prov.mutation_parameters,
                "source_mode": prov.source_mode,
            }
        )
    return {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "generator_version": GENERATOR_VERSION,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "baseline_git_sha": baseline_git_sha,
        "canonical_parent_count": len(result.parent_hashes),
        "canonical_parent_hashes": dict(sorted(result.parent_hashes.items())),
        "generated_scenario_count": len(scenarios),
        "scenarios": scenarios,
    }


def compute_generation_payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_generation_manifest(
    result: GenerationResult,
    *,
    baseline_git_sha: str | None = None,
) -> dict[str, Any]:
    payload = _manifest_payload(result, baseline_git_sha=baseline_git_sha)
    payload_hash = compute_generation_payload_hash(payload)
    return {
        **payload,
        "generation_payload_hash": payload_hash,
    }
