"""Report builders for Kapitel 2G batch evaluation."""

from __future__ import annotations

import hashlib
from typing import Any

from app.evaluation.batch.failures import FAILURE_SCHEMA_VERSION, build_failure_corpus
from app.evaluation.batch.gates import GateEvaluation, evaluate_gates
from app.evaluation.batch.metrics import compute_batch_metrics
from app.evaluation.batch.runner import BatchRunResult
from app.evaluation.dataset_manifest import canonical_json_bytes
from app.evaluation.generation.manifest import MANIFEST_SCHEMA_VERSION, build_generation_manifest
from app.evaluation.generation.provenance import GENERATOR_VERSION
from app.evaluation.mutations.registry import MUTATION_VERSION

BATCH_REPORT_SCHEMA = "2g.batch-report.v1"
COVERAGE_REPORT_SCHEMA = "2g.coverage-report.v1"


def _hash_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def build_coverage_report(batch: BatchRunResult) -> dict[str, Any]:
    category_counts: dict[str, int] = {}
    mutation_counts: dict[str, int] = {}
    parent_counts: dict[str, int] = {}
    for outcome in batch.outcomes:
        category = outcome.record.scenario.category
        category_counts[category] = category_counts.get(category, 0) + 1
        parent = outcome.record.provenance.parent_scenario_id
        parent_counts[parent] = parent_counts.get(parent, 0) + 1
        for mutation_id in outcome.record.provenance.mutation_types:
            mutation_counts[mutation_id] = mutation_counts.get(mutation_id, 0) + 1
    payload = {
        "coverage_schema_version": COVERAGE_REPORT_SCHEMA,
        "mode": batch.mode,
        "scenario_count": len(batch.outcomes),
        "category_counts": dict(sorted(category_counts.items())),
        "mutation_counts": dict(sorted(mutation_counts.items())),
        "parent_descendant_counts": dict(sorted(parent_counts.items())),
    }
    payload["coverage_payload_hash"] = _hash_payload(
        {k: v for k, v in payload.items() if k != "coverage_payload_hash"}
    )
    return payload


def build_batch_report(
    batch: BatchRunResult,
    *,
    baseline_git_sha: str | None = None,
    generation_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = compute_batch_metrics(batch)
    failures = build_failure_corpus(batch)
    gates = evaluate_gates(metrics, failures)
    coverage = build_coverage_report(batch)
    generation_hash = (generation_manifest or {}).get("generation_payload_hash")
    payload = {
        "batch_schema_version": BATCH_REPORT_SCHEMA,
        "baseline_git_sha": baseline_git_sha,
        "generator_version": GENERATOR_VERSION,
        "mutation_version": MUTATION_VERSION,
        "generation_manifest_schema": MANIFEST_SCHEMA_VERSION,
        "generation_manifest_payload_hash": generation_hash,
        "mode": batch.mode,
        "run_id": batch.run_id,
        "scenario_count": len(batch.outcomes),
        "overall_status": "passed" if gates.passed else "failed",
        "metrics": metrics,
        "blocking_gates": gates.blocking_gates,
        "quality_gates": gates.quality_gates,
        "failures_payload_hash": failures["failures_payload_hash"],
        "coverage_payload_hash": coverage["coverage_payload_hash"],
        "no_network": metrics["no_network"],
        "external_side_effects": {
            "openai_calls": metrics["openai_calls"],
            "gmail_calls": metrics["gmail_calls"],
            "external_action_writes": metrics["external_action_writes"],
        },
    }
    payload["batch_payload_hash"] = _hash_payload(
        {k: v for k, v in payload.items() if k != "batch_payload_hash"}
    )
    return payload


def build_generation_manifest_for_records(records, *, baseline_git_sha: str | None = None) -> dict[str, Any]:
    from app.evaluation.generation.generator import GenerationResult

    parent_hashes = {record.provenance.parent_scenario_id: "" for record in records}
    for record in records:
        parent_hashes[record.provenance.parent_scenario_id] = parent_hashes.get(
            record.provenance.parent_scenario_id, ""
        )
    from app.evaluation.generation.parent_loader import load_canonical_parents

    _, parents = load_canonical_parents()
    parent_hashes = {parent.scenario_id: parent.content_hash for parent in parents}
    result = GenerationResult(records=records, parent_hashes=parent_hashes)
    return build_generation_manifest(result, baseline_git_sha=baseline_git_sha)
