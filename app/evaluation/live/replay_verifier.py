"""Kapitel 2F.4C — deterministic offline replay verifier (no network)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.evaluation.dataset_manifest import canonical_json_bytes
from app.evaluation.live.final_evidence import (
    CANONICALIZATION_VERSION,
    FORBIDDEN_EVIDENCE_KEYS,
    EvidenceSourcesDocument,
    _compute_payload_hash,
    _scan_forbidden_content,
    build_evidence_manifest,
    build_final_report,
    compute_evidence_source_descriptor_hash,
    load_evidence_sources,
)
from app.evaluation.live.llm_report import _summarize_llm_events

REPLAY_SCHEMA_VERSION = "2f.4.replay-report"
REPLAY_SOURCE_DESCRIPTOR_VERSION = "replay-sources-v1"
CLOSURE_CHAPTER = "2F.4C"

ALLOWED_REPLAY_TYPES = frozenset(
    {
        "artifact_reference",
        "observation_report",
        "contract_smoke",
        "historical_failure",
    }
)
ALLOWED_STEP_STATUSES = frozenset({"passed", "failed", "not_applicable"})
ALLOWED_PROVENANCE = frozenset(
    {
        "verified_from_local_artifact",
        "derived_from_verified_artifact",
        "derived_from_verified_ci_log",
        "sanitized_verified_telemetry",
        "synthetic_contract_fixture",
    }
)

_SHA256_HEX_RE = re.compile(r"^[a-f0-9]{64}$")

_ZERO_SIDE_EFFECTS = {
    "gmail_sends": 0,
    "gmail_reads": 0,
    "gmail_mutations": 0,
    "llm_provider_calls": 0,
    "app_replies": 0,
    "approval_resolutions": 0,
    "external_action_writes": 0,
}


class ArtifactReference(BaseModel):
    workflow_run_id: str
    evaluation_run_id: str
    artifact_schema: str
    artifact_name: str
    artifact_file_sha256: str
    final_status: str
    provenance: str

    @field_validator("artifact_file_sha256")
    @classmethod
    def _hash_format(cls, value: str) -> str:
        if not _SHA256_HEX_RE.match(value):
            raise ValueError("artifact_file_sha256 must be 64-char lowercase hex")
        return value

    @field_validator("provenance")
    @classmethod
    def _provenance_allowed(cls, value: str) -> str:
        if value not in ALLOWED_PROVENANCE:
            raise ValueError(f"unknown provenance: {value!r}")
        return value


class GmailArtifactReference(ArtifactReference):
    job_status: str
    pending_approval_count: int
    gmail_sends: int
    gmail_mutations: int
    llm_provider_calls: int
    external_action_writes: int


class LlmArtifactReference(ArtifactReference):
    original_run_head_sha: str
    job_status: str
    pending_approval_count: int
    provider_calls: int
    succeeded: int
    retries: int
    fallbacks: int
    external_action_writes: int
    original_artifact_pre_fix_report_semantics: bool = True


class HistoricalFailureReference(BaseModel):
    workflow_run_id: str
    evaluation_run_id: str
    classification: Literal["historical_harness_failure"]
    provider_outcome: Literal["unknown"]
    never_rerun: bool = True
    never_resume: bool = True
    never_valid_as_success: bool = True
    provenance: str

    @field_validator("provenance")
    @classmethod
    def _provenance_allowed(cls, value: str) -> str:
        if value not in ALLOWED_PROVENANCE:
            raise ValueError(f"unknown provenance: {value!r}")
        return value


class LlmRegenerationExpectation(BaseModel):
    attempted: int
    succeeded: int
    failed: int
    outcome_unknown: int
    operations_length: int
    input_tokens: int
    output_tokens: int
    total_tokens: int
    latency_ms: int
    output_hashes: list[str]

    @field_validator("output_hashes")
    @classmethod
    def _output_hashes(cls, value: list[str]) -> list[str]:
        for item in value:
            if not _SHA256_HEX_RE.match(item):
                raise ValueError("output_hashes must be full SHA-256 hex")
        return value


class ReplaySourcesDocument(BaseModel):
    source_descriptor_version: str
    evidence_source_descriptor_hash: str
    gmail_artifact_reference: GmailArtifactReference
    llm_artifact_reference: LlmArtifactReference
    llm_telemetry_events: list[dict[str, Any]]
    historical_failure_reference: HistoricalFailureReference
    expected_replay_results: dict[str, Any]
    provenance: dict[str, str]
    limitations: list[str] = Field(default_factory=list)

    @field_validator("evidence_source_descriptor_hash")
    @classmethod
    def _hash_format(cls, value: str) -> str:
        if not _SHA256_HEX_RE.match(value):
            raise ValueError("evidence_source_descriptor_hash must be 64-char lowercase hex")
        return value

    @model_validator(mode="after")
    def _validate_provenance(self) -> ReplaySourcesDocument:
        if self.provenance.get("llm_telemetry_events") == "synthetic_contract_fixture":
            raise ValueError(
                "authoritative live llm replay cannot use synthetic_contract_fixture"
            )
        return self


@dataclass(frozen=True)
class OfflineReplayResult:
    manifest: dict[str, Any]
    replay_report: dict[str, Any]
    final_report: dict[str, Any]
    evidence_payload_hash: str
    evidence_source_descriptor_hash: str
    replay_payload_hash: str


def _validate_replay_bindings(
    manifest: dict[str, Any],
    replay_report: dict[str, Any],
    *,
    baseline_git_sha: str,
) -> None:
    if manifest["baseline_git_sha"] != baseline_git_sha:
        raise ValueError("manifest baseline_git_sha does not match CLI baseline")
    if manifest["baseline_git_sha"] != replay_report["baseline_git_sha"]:
        raise ValueError("manifest baseline_git_sha does not match replay report")
    if manifest["evidence_payload_hash"] != replay_report["evidence_manifest_payload_hash"]:
        raise ValueError("manifest evidence_payload_hash does not match replay report")


def _authoritative_side_effects_known(manifest: dict[str, Any]) -> bool:
    for run in manifest.get("runs", []):
        if run.get("classification") not in {
            "authoritative_success",
            "release_gate_support",
        }:
            continue
        effects = run.get("external_side_effects") or {}
        for counter in effects.values():
            if not counter.get("known"):
                return False
            if counter.get("value") == "unknown":
                return False
    return True


def _historical_unknowns_classified(manifest: dict[str, Any]) -> bool:
    for failure in manifest.get("historical_failures", []):
        if failure.get("classification") != "historical_harness_failure":
            return False
        if failure.get("provider_outcome") != "unknown":
            return False
        if not failure.get("never_rerun"):
            return False
        if not failure.get("never_resume"):
            return False
        if not failure.get("never_valid_as_success"):
            return False
        llm_calls = (failure.get("external_side_effects") or {}).get("llm_provider_calls") or {}
        if llm_calls.get("known") or llm_calls.get("value") != "unknown":
            return False
    return True


def load_replay_sources(path: Path) -> ReplaySourcesDocument:
    raw = json.loads(path.read_text(encoding="utf-8"))
    doc = ReplaySourcesDocument.model_validate(raw)
    issues = _scan_forbidden_content(raw)
    if issues:
        raise ValueError(
            "replay sources contain forbidden keys or patterns: " + "; ".join(issues)
        )
    return doc


def _hash_payload(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _find_manifest_run(manifest: dict[str, Any], workflow_run_id: str) -> dict[str, Any]:
    for run in manifest.get("runs", []):
        if run.get("workflow_run_id") == workflow_run_id:
            return run
    raise ValueError(f"workflow_run_id {workflow_run_id!r} not found in manifest")


def _find_manifest_failure(manifest: dict[str, Any], workflow_run_id: str) -> dict[str, Any]:
    for failure in manifest.get("historical_failures", []):
        if failure.get("workflow_run_id") == workflow_run_id:
            return failure
    raise ValueError(f"historical failure {workflow_run_id!r} not found in manifest")


def _counter_value(run: dict[str, Any], field: str) -> int:
    counter = (run.get("external_side_effects") or {}).get(field) or {}
    if not counter.get("known"):
        raise ValueError(f"{field} is not known for run {run.get('workflow_run_id')}")
    value = counter.get("value")
    if not isinstance(value, int):
        raise ValueError(f"{field} must be a known integer")
    return value


def _make_step(
    *,
    step_id: str,
    replay_type: str,
    source_reference: str,
    input_hash: str,
    output_hash: str,
    status: str,
    assertions: dict[str, Any],
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    if replay_type not in ALLOWED_REPLAY_TYPES:
        raise ValueError(f"unknown replay_type: {replay_type!r}")
    if status not in ALLOWED_STEP_STATUSES:
        raise ValueError(f"unknown replay step status: {status!r}")
    return {
        "step_id": step_id,
        "replay_type": replay_type,
        "source_reference": source_reference,
        "input_hash": input_hash,
        "output_hash": output_hash,
        "status": status,
        "assertions": assertions,
        "limitations": sorted(limitations or []),
    }


def _normalize_regeneration_summary(
    operations: list[dict[str, Any]],
    token_usage: dict[str, Any],
) -> dict[str, Any]:
    normalized_operations: list[dict[str, Any]] = []
    for operation in operations:
        normalized_operations.append(
            {
                "operation_key": operation.get("operation_key"),
                "ordinal": operation.get("ordinal"),
                "prompt_name": operation.get("prompt_name"),
                "state": operation.get("state"),
                "provider": operation.get("provider"),
                "requested_model": operation.get("requested_model"),
                "returned_model": operation.get("returned_model"),
                "finish_reason": operation.get("finish_reason"),
                "schema_validation_status": operation.get("schema_validation_status"),
                "retry_count": operation.get("retry_count"),
                "used_fallback": operation.get("used_fallback"),
                "input_tokens": operation.get("input_tokens"),
                "output_tokens": operation.get("output_tokens"),
                "total_tokens": operation.get("total_tokens"),
                "latency_ms": operation.get("latency_ms"),
                "output_hash": operation.get("output_hash"),
            }
        )
    return {
        "regeneration_kind": "current_main_report_semantics",
        "token_usage": {
            "attempted": token_usage.get("attempted"),
            "succeeded": token_usage.get("succeeded"),
            "failed": token_usage.get("failed"),
            "outcome_unknown": token_usage.get("outcome_unknown"),
            "input_tokens": token_usage.get("input_tokens"),
            "output_tokens": token_usage.get("output_tokens"),
            "total_tokens": token_usage.get("total_tokens"),
            "latency_ms": token_usage.get("latency_ms"),
        },
        "operations": normalized_operations,
    }


def _verify_gmail_artifact_contract(
    manifest: dict[str, Any],
    sources: ReplaySourcesDocument,
) -> dict[str, Any]:
    ref = sources.gmail_artifact_reference
    run = _find_manifest_run(manifest, ref.workflow_run_id)
    assertions: dict[str, Any] = {}
    status = "passed"
    limitations = [
        "artifact reference replay does not assert pre-fix llm semantics on gmail artifact"
    ]

    checks = [
        ("evaluation_run_id", ref.evaluation_run_id, run.get("evaluation_run_id")),
        ("artifact_schema", ref.artifact_schema, run.get("artifact_schema")),
        ("artifact_name", ref.artifact_name, run.get("artifact_name")),
        ("artifact_file_sha256", ref.artifact_file_sha256, run.get("artifact_file_sha256")),
        ("final_status", ref.final_status, run.get("final_status")),
        ("gmail_sends", ref.gmail_sends, _counter_value(run, "gmail_sends")),
        ("gmail_mutations", ref.gmail_mutations, _counter_value(run, "gmail_mutations")),
        ("llm_provider_calls", ref.llm_provider_calls, _counter_value(run, "llm_provider_calls")),
        (
            "external_action_writes",
            ref.external_action_writes,
            _counter_value(run, "external_action_writes"),
        ),
    ]
    for key, expected, actual in checks:
        assertions[key] = {"expected": expected, "actual": actual, "passed": expected == actual}
        if expected != actual:
            status = "failed"

    manifest_hash = manifest.get("artifact_hashes", {}).get(ref.artifact_name)
    assertions["manifest_artifact_hash"] = {
        "expected": ref.artifact_file_sha256,
        "actual": manifest_hash,
        "passed": manifest_hash == ref.artifact_file_sha256,
    }
    if manifest_hash != ref.artifact_file_sha256:
        status = "failed"

    input_hash = _hash_payload(ref.model_dump(mode="json"))
    output_hash = _hash_payload({"assertions": assertions, "status": status})
    return _make_step(
        step_id="gmail_artifact_contract",
        replay_type="artifact_reference",
        source_reference=ref.workflow_run_id,
        input_hash=input_hash,
        output_hash=output_hash,
        status=status,
        assertions=assertions,
        limitations=limitations,
    )


def _verify_llm_artifact_contract(
    manifest: dict[str, Any],
    sources: ReplaySourcesDocument,
) -> dict[str, Any]:
    ref = sources.llm_artifact_reference
    run = _find_manifest_run(manifest, ref.workflow_run_id)
    assertions: dict[str, Any] = {}
    status = "passed"
    limitations = [
        "artifact reference replay does not claim original pre-fix artifact had corrected semantics"
    ]

    checks = [
        ("evaluation_run_id", ref.evaluation_run_id, run.get("evaluation_run_id")),
        ("artifact_schema", ref.artifact_schema, run.get("artifact_schema")),
        ("artifact_name", ref.artifact_name, run.get("artifact_name")),
        ("artifact_file_sha256", ref.artifact_file_sha256, run.get("artifact_file_sha256")),
        ("final_status", ref.final_status, run.get("final_status")),
        ("provider_calls", ref.provider_calls, _counter_value(run, "llm_provider_calls")),
        (
            "external_action_writes",
            ref.external_action_writes,
            _counter_value(run, "external_action_writes"),
        ),
    ]
    for key, expected, actual in checks:
        assertions[key] = {"expected": expected, "actual": actual, "passed": expected == actual}
        if expected != actual:
            status = "failed"

    manifest_hash = manifest.get("artifact_hashes", {}).get(ref.artifact_name)
    assertions["manifest_artifact_hash"] = {
        "expected": ref.artifact_file_sha256,
        "actual": manifest_hash,
        "passed": manifest_hash == ref.artifact_file_sha256,
    }
    if manifest_hash != ref.artifact_file_sha256:
        status = "failed"

    assertions["original_artifact_pre_fix_report_semantics"] = {
        "expected": True,
        "actual": ref.original_artifact_pre_fix_report_semantics,
        "passed": ref.original_artifact_pre_fix_report_semantics is True,
    }

    input_hash = _hash_payload(ref.model_dump(mode="json"))
    output_hash = _hash_payload({"assertions": assertions, "status": status})
    return _make_step(
        step_id="llm_artifact_contract",
        replay_type="artifact_reference",
        source_reference=ref.workflow_run_id,
        input_hash=input_hash,
        output_hash=output_hash,
        status=status,
        assertions=assertions,
        limitations=limitations,
    )


def _verify_llm_observation_regeneration(
    sources: ReplaySourcesDocument,
) -> dict[str, Any]:
    expected = LlmRegenerationExpectation.model_validate(
        sources.expected_replay_results["llm_regeneration"]
    )
    operations, token_usage = _summarize_llm_events(sources.llm_telemetry_events)
    summary = _normalize_regeneration_summary(operations, token_usage)

    assertions: dict[str, Any] = {
        "attempted": {
            "expected": expected.attempted,
            "actual": token_usage.get("attempted"),
            "passed": token_usage.get("attempted") == expected.attempted,
        },
        "succeeded": {
            "expected": expected.succeeded,
            "actual": token_usage.get("succeeded"),
            "passed": token_usage.get("succeeded") == expected.succeeded,
        },
        "operations_length": {
            "expected": expected.operations_length,
            "actual": len(operations),
            "passed": len(operations) == expected.operations_length,
        },
        "input_tokens": {
            "expected": expected.input_tokens,
            "actual": token_usage.get("input_tokens"),
            "passed": token_usage.get("input_tokens") == expected.input_tokens,
        },
        "output_tokens": {
            "expected": expected.output_tokens,
            "actual": token_usage.get("output_tokens"),
            "passed": token_usage.get("output_tokens") == expected.output_tokens,
        },
        "total_tokens": {
            "expected": expected.total_tokens,
            "actual": token_usage.get("total_tokens"),
            "passed": token_usage.get("total_tokens") == expected.total_tokens,
        },
        "latency_ms": {
            "expected": expected.latency_ms,
            "actual": token_usage.get("latency_ms"),
            "passed": token_usage.get("latency_ms") == expected.latency_ms,
        },
    }

    actual_hashes = [op.get("output_hash") for op in operations]
    assertions["output_hashes"] = {
        "expected": expected.output_hashes,
        "actual": actual_hashes,
        "passed": actual_hashes == expected.output_hashes,
    }

    for index, operation in enumerate(operations, start=1):
        assertions[f"operation_{index}_provider"] = {
            "expected": "openai",
            "actual": operation.get("provider"),
            "passed": operation.get("provider") == "openai",
        }
        assertions[f"operation_{index}_requested_model"] = {
            "expected": "gpt-4o-mini",
            "actual": operation.get("requested_model"),
            "passed": operation.get("requested_model") == "gpt-4o-mini",
        }
        assertions[f"operation_{index}_returned_model"] = {
            "expected": "gpt-4o-mini-2024-07-18",
            "actual": operation.get("returned_model"),
            "passed": operation.get("returned_model") == "gpt-4o-mini-2024-07-18",
        }
        assertions[f"operation_{index}_finish_reason"] = {
            "expected": "stop",
            "actual": operation.get("finish_reason"),
            "passed": operation.get("finish_reason") == "stop",
        }
        assertions[f"operation_{index}_schema_validation_status"] = {
            "expected": "passed",
            "actual": operation.get("schema_validation_status"),
            "passed": operation.get("schema_validation_status") == "passed",
        }
        assertions[f"operation_{index}_retry_count"] = {
            "expected": 0,
            "actual": operation.get("retry_count"),
            "passed": operation.get("retry_count") == 0,
        }
        assertions[f"operation_{index}_used_fallback"] = {
            "expected": False,
            "actual": operation.get("used_fallback"),
            "passed": operation.get("used_fallback") is False,
        }

    operation_keys = [op.get("operation_key") for op in operations]
    assertions["unique_operation_keys"] = {
        "expected": expected.operations_length,
        "actual": len(set(operation_keys)),
        "passed": len(set(operation_keys)) == expected.operations_length,
    }

    status = "passed"
    if not all(item.get("passed") for item in assertions.values()):
        status = "failed"

    input_hash = _hash_payload({"events_count": len(sources.llm_telemetry_events)})
    output_hash = _hash_payload(summary)
    return _make_step(
        step_id="llm_observation_report_regeneration",
        replay_type="observation_report",
        source_reference=sources.llm_artifact_reference.evaluation_run_id,
        input_hash=input_hash,
        output_hash=output_hash,
        status=status,
        assertions=assertions,
        limitations=[
            "regenerated summary represents current-main semantics, not historical artifact file contents"
        ],
    )


def _verify_historical_failure(
    manifest: dict[str, Any],
    sources: ReplaySourcesDocument,
) -> dict[str, Any]:
    ref = sources.historical_failure_reference
    failure = _find_manifest_failure(manifest, ref.workflow_run_id)
    assertions: dict[str, Any] = {}
    status = "passed"

    checks = [
        ("classification", ref.classification, failure.get("classification")),
        ("provider_outcome", ref.provider_outcome, failure.get("provider_outcome")),
        ("never_rerun", ref.never_rerun, failure.get("never_rerun")),
        ("never_resume", ref.never_resume, failure.get("never_resume")),
        (
            "never_valid_as_success",
            ref.never_valid_as_success,
            failure.get("never_valid_as_success"),
        ),
        ("evaluation_run_id", ref.evaluation_run_id, failure.get("evaluation_run_id")),
    ]
    for key, expected, actual in checks:
        assertions[key] = {"expected": expected, "actual": actual, "passed": expected == actual}
        if expected != actual:
            status = "failed"

    authoritative = {
        run_id
        for chapter in manifest.get("chapters", {}).values()
        for run_id in chapter.get("authoritative_evidence", [])
    }
    assertions["not_authoritative_success"] = {
        "expected": False,
        "actual": ref.workflow_run_id in authoritative,
        "passed": ref.workflow_run_id not in authoritative,
    }
    if ref.workflow_run_id in authoritative:
        status = "failed"

    llm_calls = (failure.get("external_side_effects") or {}).get("llm_provider_calls") or {}
    assertions["provider_calls_not_zero_guess"] = {
        "expected": "unknown",
        "actual": llm_calls.get("value"),
        "passed": llm_calls.get("known") is False and llm_calls.get("value") == "unknown",
    }
    if llm_calls.get("known") or llm_calls.get("value") != "unknown":
        status = "failed"

    input_hash = _hash_payload(ref.model_dump(mode="json"))
    output_hash = _hash_payload({"assertions": assertions, "status": status})
    return _make_step(
        step_id="historical_failure_classification",
        replay_type="historical_failure",
        source_reference=ref.workflow_run_id,
        input_hash=input_hash,
        output_hash=output_hash,
        status=status,
        assertions=assertions,
        limitations=["provider outcome remains unknown; never counted in verified totals"],
    )


def _verify_final_evidence_contract_smoke(
    manifest: dict[str, Any],
    *,
    evidence_sources: EvidenceSourcesDocument,
    replay_sources: ReplaySourcesDocument,
    baseline_git_sha: str,
) -> dict[str, Any]:
    computed_descriptor_hash = compute_evidence_source_descriptor_hash(evidence_sources)
    assertions: dict[str, Any] = {
        "manifest_schema": {
            "expected": "2f.4.evidence-manifest",
            "actual": manifest.get("manifest_schema_version"),
            "passed": manifest.get("manifest_schema_version") == "2f.4.evidence-manifest",
        },
        "evidence_source_descriptor_hash": {
            "expected": replay_sources.evidence_source_descriptor_hash,
            "actual": computed_descriptor_hash,
            "passed": computed_descriptor_hash
            == replay_sources.evidence_source_descriptor_hash,
        },
        "runtime_manifest_baseline_git_sha": {
            "expected": baseline_git_sha,
            "actual": manifest.get("baseline_git_sha"),
            "passed": manifest.get("baseline_git_sha") == baseline_git_sha,
        },
        "canonicalization_version": {
            "expected": CANONICALIZATION_VERSION,
            "actual": manifest.get("canonicalization_version"),
            "passed": manifest.get("canonicalization_version") == CANONICALIZATION_VERSION,
        },
    }
    status = "passed" if all(item["passed"] for item in assertions.values()) else "failed"
    input_hash = _hash_payload(
        {
            "evidence_source_descriptor_hash": replay_sources.evidence_source_descriptor_hash,
            "baseline_git_sha": baseline_git_sha,
        }
    )
    output_hash = _hash_payload({"assertions": assertions, "status": status})
    return _make_step(
        step_id="final_evidence_contract_smoke",
        replay_type="contract_smoke",
        source_reference="evidence_manifest",
        input_hash=input_hash,
        output_hash=output_hash,
        status=status,
        assertions=assertions,
        limitations=[],
    )


def _replay_hash_payload(report_without_hash: dict[str, Any]) -> dict[str, Any]:
    payload = dict(report_without_hash)
    payload.pop("replay_payload_hash", None)
    payload.pop("generated_at", None)
    return payload


def build_replay_report(
    *,
    manifest: dict[str, Any],
    evidence_sources: EvidenceSourcesDocument,
    sources: ReplaySourcesDocument,
    baseline_git_sha: str,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    computed_descriptor_hash = compute_evidence_source_descriptor_hash(evidence_sources)
    if computed_descriptor_hash != sources.evidence_source_descriptor_hash:
        raise ValueError(
            "replay sources evidence_source_descriptor_hash does not match evidence sources"
        )
    if manifest.get("baseline_git_sha") != baseline_git_sha:
        raise ValueError("manifest baseline_git_sha does not match CLI baseline")

    steps = [
        _verify_gmail_artifact_contract(manifest, sources),
        _verify_llm_artifact_contract(manifest, sources),
        _verify_llm_observation_regeneration(sources),
        _verify_historical_failure(manifest, sources),
        _verify_final_evidence_contract_smoke(
            manifest,
            evidence_sources=evidence_sources,
            replay_sources=sources,
            baseline_git_sha=baseline_git_sha,
        ),
    ]
    steps = sorted(steps, key=lambda step: step["step_id"])
    overall_status = (
        "passed" if all(step["status"] == "passed" for step in steps) else "failed"
    )

    report_without_hash: dict[str, Any] = {
        "replay_schema_version": REPLAY_SCHEMA_VERSION,
        "closure_chapter": CLOSURE_CHAPTER,
        "baseline_git_sha": baseline_git_sha,
        "evidence_source_descriptor_hash": computed_descriptor_hash,
        "evidence_manifest_payload_hash": manifest["evidence_payload_hash"],
        "source_descriptor_version": sources.source_descriptor_version,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "overall_status": overall_status,
        "no_network": True,
        "steps": steps,
        "external_side_effects": dict(_ZERO_SIDE_EFFECTS),
        "limitations": sorted(sources.limitations),
    }
    payload_hash = _compute_payload_hash(_replay_hash_payload(report_without_hash))
    report = dict(report_without_hash)
    report["replay_payload_hash"] = payload_hash
    if generated_at is not None:
        report["generated_at"] = generated_at.astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    return report


def build_final_report_with_replay(
    manifest: dict[str, Any],
    replay_report: dict[str, Any],
    *,
    baseline_git_sha: str,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    _validate_replay_bindings(manifest, replay_report, baseline_git_sha=baseline_git_sha)
    report = build_final_report(manifest, generated_at=generated_at)
    report["replay_report_schema"] = replay_report["replay_schema_version"]
    report["replay_report_payload_hash"] = replay_report["replay_payload_hash"]
    report["evidence_source_descriptor_hash"] = replay_report[
        "evidence_source_descriptor_hash"
    ]

    if replay_report.get("overall_status") == "passed":
        authoritative_known = _authoritative_side_effects_known(manifest)
        historical_classified = _historical_unknowns_classified(manifest)
        report["replay_status"] = "passed"
        report["overall_status"] = (
            "pending_closure"
            if authoritative_known and historical_classified
            else "pending_replay"
        )
        report["closure_criteria"]["observation_replay"] = "passed"
        report["closure_criteria"]["offline_smoke"] = "passed"
        report["closure_criteria"]["replay_determinism"] = "passed"
        report["closure_criteria"]["final_ci_delivery"] = "pending"
        report["closure_criteria"]["formal_documentation_closure"] = "pending"
        report["closure_criteria"][
            "no_unknown_external_side_effects_in_authoritative_evidence"
        ] = "passed" if authoritative_known else "failed"
        report["closure_criteria"]["historical_unknowns_classified_and_excluded"] = (
            "passed" if historical_classified else "failed"
        )
    else:
        report["replay_status"] = "failed"
        report["overall_status"] = "pending_replay"

    return report


def run_offline_replay(
    *,
    evidence_sources_path: Path,
    replay_sources_path: Path,
    baseline_git_sha: str,
    generated_at: datetime | None = None,
) -> OfflineReplayResult:
    evidence_sources = load_evidence_sources(evidence_sources_path)
    if baseline_git_sha:
        evidence_sources = evidence_sources.model_copy(
            update={"baseline_git_sha": baseline_git_sha}
        )
    replay_sources = load_replay_sources(replay_sources_path)
    manifest = build_evidence_manifest(evidence_sources, generated_at=generated_at)
    replay_report = build_replay_report(
        manifest=manifest,
        evidence_sources=evidence_sources,
        sources=replay_sources,
        baseline_git_sha=baseline_git_sha,
        generated_at=generated_at,
    )
    final_report = build_final_report_with_replay(
        manifest,
        replay_report,
        baseline_git_sha=baseline_git_sha,
        generated_at=generated_at,
    )
    return OfflineReplayResult(
        manifest=manifest,
        replay_report=replay_report,
        final_report=final_report,
        evidence_payload_hash=manifest["evidence_payload_hash"],
        evidence_source_descriptor_hash=replay_report["evidence_source_descriptor_hash"],
        replay_payload_hash=replay_report["replay_payload_hash"],
    )
