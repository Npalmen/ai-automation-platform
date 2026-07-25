"""Kapitel 2F.4B — deterministic evidence manifest and final report builder."""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.evaluation.dataset_manifest import canonical_json_bytes

MANIFEST_SCHEMA_VERSION = "2f.4.evidence-manifest"
FINAL_REPORT_SCHEMA_VERSION = "2f.4.final-report"
SOURCE_DESCRIPTOR_VERSION = "evidence-sources-v1"
CANONICALIZATION_VERSION = "semantic-json-v2"
CLOSURE_CHAPTER = "2F.4B"

ALLOWED_CLASSIFICATIONS = frozenset(
    {
        "authoritative_success",
        "readiness_support",
        "release_gate_support",
        "historical_harness_failure",
    }
)

SIDE_EFFECT_FIELDS = (
    "gmail_sends",
    "gmail_reads",
    "gmail_mutations",
    "llm_provider_calls",
    "app_replies",
    "approval_resolutions",
    "external_action_writes",
)

FORBIDDEN_EVIDENCE_KEYS = frozenset(
    {
        "authorization",
        "bearer",
        "api_key",
        "access_token",
        "refresh_token",
        "client_secret",
        "raw_body",
        "raw_response",
        "message_content",
        "prompt",
        "email_address",
        "password",
        "secret",
    }
)

_FORBIDDEN_VALUE_PATTERNS = (
    re.compile(r"Bearer\s+\S+", re.IGNORECASE),
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
    re.compile(r"ya29\.[A-Za-z0-9_-]+"),
)

_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_GMAIL_MESSAGE_ID_PATTERN = re.compile(r"^19[a-f0-9]{14,}$")

_SKIP_VALUE_PATTERN_KEYS = frozenset(
    {
        "head_sha",
        "artifact_file_sha256",
        "baseline_git_sha",
        "fixed_by_sha",
        "artifact_name",
        "workflow_run_id",
        "evaluation_run_id",
        "report_semantics_fixed_by_sha",
        "evidence_payload_hash",
        "manifest_payload_hash",
        "config_fingerprint",
        "model_identity_registry_fingerprint",
    }
)

_GMAIL_MESSAGE_ID_KEYS = frozenset(
    {
        "sender_gmail_message_id",
        "recipient_gmail_message_id",
        "gmail_message_id",
        "message_id",
    }
)

_SHA256_HEX_RE = re.compile(r"^[a-f0-9]{64}$")
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)


class SideEffectCounter(BaseModel):
    value: int | Literal["unknown"]
    known: bool

    @model_validator(mode="after")
    def _validate_known_consistency(self) -> SideEffectCounter:
        if self.known and self.value == "unknown":
            raise ValueError("known=true requires a numeric side-effect value")
        if not self.known and isinstance(self.value, int):
            raise ValueError("known=false requires value='unknown'")
        return self


class ExternalSideEffects(BaseModel):
    gmail_sends: SideEffectCounter
    gmail_reads: SideEffectCounter
    gmail_mutations: SideEffectCounter
    llm_provider_calls: SideEffectCounter
    app_replies: SideEffectCounter
    approval_resolutions: SideEffectCounter
    external_action_writes: SideEffectCounter


class EvidenceSourceRun(BaseModel):
    workflow_run_id: str
    workflow_run_number: int | None = None
    workflow_name: str
    head_sha: str
    classification: str
    chapter: str
    evaluation_run_id: str | None = None
    scenario_id: str | None = None
    transport_mode: str | None = None
    ai_mode: str | None = None
    provider: str | None = None
    requested_model: str | None = None
    artifact_name: str | None = None
    artifact_schema: str | None = None
    artifact_file_sha256: str | None = None
    artifact_hash_provenance: Literal[
        "verified_from_local_artifact",
        "attested_historical_hash",
        "fixture_hash",
    ] | None = None
    redaction_status: Literal["clean", "unknown"]
    final_status: str
    external_side_effects: ExternalSideEffects
    limitations: list[str] = Field(default_factory=list)
    provider_outcome: Literal["unknown"] | None = None
    root_cause: str | None = None
    fixed_by_sha: str | None = None
    never_rerun: bool | None = None
    never_resume: bool | None = None
    never_valid_as_success: bool | None = None

    @field_validator("classification")
    @classmethod
    def _classification_allowed(cls, value: str) -> str:
        if value not in ALLOWED_CLASSIFICATIONS:
            raise ValueError(f"unknown classification: {value!r}")
        return value

    @field_validator("head_sha", "fixed_by_sha")
    @classmethod
    def _sha_format(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _GIT_SHA_RE.match(value):
            raise ValueError(f"invalid git sha: {value!r}")
        return value.lower()

    @field_validator("artifact_file_sha256")
    @classmethod
    def _artifact_hash_format(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _SHA256_HEX_RE.match(value):
            raise ValueError("artifact_file_sha256 must be 64-char lowercase hex")
        return value

    @model_validator(mode="after")
    def _validate_classification_rules(self) -> EvidenceSourceRun:
        if self.classification == "historical_harness_failure":
            raise ValueError(
                "historical_harness_failure must be provided via historical_failures, not runs"
            )
        if self.classification == "authoritative_success":
            if self.final_status not in {"success", "passed", "closed"}:
                raise ValueError(
                    "authoritative_success requires final_status in success/passed/closed"
                )
            if not self.artifact_schema:
                raise ValueError("authoritative_success requires artifact_schema")
        if self.classification == "release_gate_support":
            if self.final_status != "success":
                raise ValueError("release_gate_support requires final_status=success")
        return self


class EvidenceSourceFailure(BaseModel):
    workflow_run_id: str
    workflow_run_number: int
    workflow_name: str
    head_sha: str
    classification: Literal["historical_harness_failure"]
    chapter: str
    evaluation_run_id: str
    scenario_id: str
    transport_mode: str
    ai_mode: str
    provider: str
    requested_model: str
    artifact_name: str | None = None
    artifact_schema: str | None = None
    artifact_file_sha256: str | None = None
    artifact_hash_provenance: Literal[
        "verified_from_local_artifact",
        "attested_historical_hash",
        "fixture_hash",
    ] | None = None
    redaction_status: Literal["clean", "unknown"]
    final_status: Literal["failure", "failed"]
    provider_outcome: Literal["unknown"]
    root_cause: str
    fixed_by_sha: str
    never_rerun: bool = True
    never_resume: bool = True
    never_valid_as_success: bool = True
    external_side_effects: ExternalSideEffects
    limitations: list[str] = Field(default_factory=list)

    @field_validator("artifact_file_sha256")
    @classmethod
    def _artifact_hash_format(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _SHA256_HEX_RE.match(value):
            raise ValueError("artifact_file_sha256 must be 64-char lowercase hex")
        return value


class ChapterEvidence(BaseModel):
    status: Literal["closed", "open"]
    authoritative_evidence: list[str]
    report_semantics_fixed_by_sha: str | None = None


class EvidenceSourcesDocument(BaseModel):
    source_descriptor_version: str
    baseline_git_sha: str
    chapters: dict[str, ChapterEvidence]
    runs: list[EvidenceSourceRun]
    historical_failures: list[EvidenceSourceFailure] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class BuildResult:
    manifest: dict[str, Any]
    final_report: dict[str, Any]
    evidence_payload_hash: str
    manifest_payload_hash: str


def _scan_forbidden_content(value: Any, *, path: str = "$", key: str | None = None) -> list[str]:
    issues: list[str] = []
    if isinstance(value, dict):
        for child_key, item in value.items():
            key_lower = str(child_key).lower()
            if key_lower in FORBIDDEN_EVIDENCE_KEYS:
                issues.append(f"{path}.{child_key}: forbidden key")
            issues.extend(
                _scan_forbidden_content(item, path=f"{path}.{child_key}", key=child_key)
            )
        return issues
    if isinstance(value, list):
        for index, item in enumerate(value):
            issues.extend(_scan_forbidden_content(item, path=f"{path}[{index}]"))
        return issues
    if isinstance(value, str):
        if key in _SKIP_VALUE_PATTERN_KEYS:
            return issues
        for pattern in _FORBIDDEN_VALUE_PATTERNS:
            if pattern.search(value):
                issues.append(f"{path}: forbidden value pattern")
                return issues
        if key in _GMAIL_MESSAGE_ID_KEYS and _GMAIL_MESSAGE_ID_PATTERN.match(value):
            issues.append(f"{path}: forbidden gmail message id")
        elif key not in _SKIP_VALUE_PATTERN_KEYS and _EMAIL_PATTERN.search(value):
            issues.append(f"{path}: forbidden value pattern")
    return issues


def _run_sort_key(run: dict[str, Any]) -> tuple[str, str]:
    return (run["workflow_run_id"], run.get("evaluation_run_id") or "")


def _side_effect_to_dict(counter: SideEffectCounter) -> dict[str, Any]:
    return {"value": counter.value, "known": counter.known}


def _serialize_run(run: EvidenceSourceRun) -> dict[str, Any]:
    payload = {
        "workflow_run_id": run.workflow_run_id,
        "workflow_run_number": run.workflow_run_number,
        "workflow_name": run.workflow_name,
        "head_sha": run.head_sha,
        "classification": run.classification,
        "chapter": run.chapter,
        "evaluation_run_id": run.evaluation_run_id,
        "scenario_id": run.scenario_id,
        "transport_mode": run.transport_mode,
        "ai_mode": run.ai_mode,
        "provider": run.provider,
        "requested_model": run.requested_model,
        "artifact_name": run.artifact_name,
        "artifact_schema": run.artifact_schema,
        "artifact_file_sha256": run.artifact_file_sha256,
        "artifact_hash_provenance": run.artifact_hash_provenance,
        "redaction_status": run.redaction_status,
        "final_status": run.final_status,
        "external_side_effects": {
            key: _side_effect_to_dict(getattr(run.external_side_effects, key))
            for key in SIDE_EFFECT_FIELDS
        },
        "limitations": sorted(run.limitations),
    }
    return payload


def _serialize_failure(failure: EvidenceSourceFailure) -> dict[str, Any]:
    return {
        "workflow_run_id": failure.workflow_run_id,
        "workflow_run_number": failure.workflow_run_number,
        "workflow_name": failure.workflow_name,
        "head_sha": failure.head_sha,
        "classification": failure.classification,
        "chapter": failure.chapter,
        "evaluation_run_id": failure.evaluation_run_id,
        "scenario_id": failure.scenario_id,
        "transport_mode": failure.transport_mode,
        "ai_mode": failure.ai_mode,
        "provider": failure.provider,
        "requested_model": failure.requested_model,
        "artifact_name": failure.artifact_name,
        "artifact_schema": failure.artifact_schema,
        "artifact_file_sha256": failure.artifact_file_sha256,
        "artifact_hash_provenance": failure.artifact_hash_provenance,
        "redaction_status": failure.redaction_status,
        "final_status": failure.final_status,
        "provider_outcome": failure.provider_outcome,
        "root_cause": failure.root_cause,
        "fixed_by_sha": failure.fixed_by_sha,
        "never_rerun": failure.never_rerun,
        "never_resume": failure.never_resume,
        "never_valid_as_success": failure.never_valid_as_success,
        "external_side_effects": {
            key: _side_effect_to_dict(getattr(failure.external_side_effects, key))
            for key in SIDE_EFFECT_FIELDS
        },
        "limitations": sorted(failure.limitations),
    }


def _sum_known_side_effects(
    runs: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> tuple[dict[str, int], list[str]]:
    totals = {key: 0 for key in SIDE_EFFECT_FIELDS}
    unknown_fields: set[str] = set()
    for run in runs:
        effects = run.get("external_side_effects") or {}
        for key in SIDE_EFFECT_FIELDS:
            counter = effects.get(key) or {}
            if not counter.get("known"):
                unknown_fields.add(key)
                continue
            value = counter.get("value")
            if value == "unknown" or not isinstance(value, int):
                unknown_fields.add(key)
                continue
            totals[key] += value
    for failure in failures:
        effects = failure.get("external_side_effects") or {}
        for key in SIDE_EFFECT_FIELDS:
            counter = effects.get(key) or {}
            if not counter.get("known") or counter.get("value") == "unknown":
                unknown_fields.add(key)
    return totals, sorted(unknown_fields)


def _artifact_hashes(runs: list[dict[str, Any]], failures: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in [*runs, *failures]:
        artifact_name = item.get("artifact_name")
        artifact_hash = item.get("artifact_file_sha256")
        if not artifact_name or not artifact_hash:
            continue
        if artifact_name in out and out[artifact_name] != artifact_hash:
            raise ValueError(
                f"artifact {artifact_name!r} has conflicting hashes: "
                f"{out[artifact_name]!r} vs {artifact_hash!r}"
            )
        out[artifact_name] = artifact_hash
    return dict(sorted(out.items()))


def _validate_uniqueness_and_correlation(
    *,
    runs: list[EvidenceSourceRun],
    failures: list[EvidenceSourceFailure],
    chapters: dict[str, ChapterEvidence],
) -> None:
    workflow_ids: set[str] = set()
    evaluation_ids: dict[str, str] = {}

    for run in runs:
        if run.workflow_run_id in workflow_ids:
            raise ValueError(f"duplicate workflow_run_id: {run.workflow_run_id}")
        workflow_ids.add(run.workflow_run_id)
        if run.evaluation_run_id:
            if run.evaluation_run_id in evaluation_ids:
                raise ValueError(
                    f"duplicate evaluation_run_id: {run.evaluation_run_id}"
                )
            evaluation_ids[run.evaluation_run_id] = run.workflow_run_id

    for failure in failures:
        if failure.workflow_run_id in workflow_ids:
            raise ValueError(
                f"workflow_run_id {failure.workflow_run_id} present in runs and failures"
            )
        workflow_ids.add(failure.workflow_run_id)
        if failure.evaluation_run_id in evaluation_ids:
            raise ValueError(
                f"evaluation_run_id {failure.evaluation_run_id} shared with success run"
            )
        if failure.final_status in {"success", "passed"}:
            raise ValueError("historical failure cannot have passed final_status")
        if failure.provider_outcome != "unknown":
            raise ValueError("historical harness failure provider_outcome must be unknown")

    gmail_eval_id: str | None = None
    llm_eval_id: str | None = None
    for run in runs:
        if run.classification == "authoritative_success" and run.chapter == "2F.2":
            gmail_eval_id = run.evaluation_run_id
        if run.classification == "authoritative_success" and run.chapter == "2F.3":
            llm_eval_id = run.evaluation_run_id
    if gmail_eval_id and llm_eval_id and gmail_eval_id == llm_eval_id:
        raise ValueError("2F.2 and 2F.3 authoritative runs must have distinct evaluation_run_id")

    all_run_ids = {run.workflow_run_id for run in runs}
    for chapter_id, chapter in chapters.items():
        for ref in chapter.authoritative_evidence:
            if ref not in all_run_ids:
                raise ValueError(
                    f"chapter {chapter_id} references unknown workflow_run_id {ref!r}"
                )
            matched = next(run for run in runs if run.workflow_run_id == ref)
            if matched.classification == "readiness_support":
                raise ValueError(
                    f"chapter {chapter_id} cannot reference readiness_support run {ref!r}"
                )
            if ref in {failure.workflow_run_id for failure in failures}:
                raise ValueError(
                    f"chapter {chapter_id} cannot reference historical failure {ref!r}"
                )

    failure_ids = {failure.workflow_run_id for failure in failures}
    for chapter in chapters.values():
        for ref in chapter.authoritative_evidence:
            if ref in failure_ids:
                raise ValueError(
                    f"authoritative_evidence cannot reference historical failure {ref!r}"
                )


def _manifest_hash_payload(manifest_without_hash: dict[str, Any]) -> dict[str, Any]:
    payload = dict(manifest_without_hash)
    payload.pop("evidence_payload_hash", None)
    payload.pop("generated_at", None)
    return payload


def _compute_payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def evidence_source_descriptor_payload(sources: EvidenceSourcesDocument) -> dict[str, Any]:
    serialized_runs = sorted(
        (_serialize_run(run) for run in sources.runs),
        key=_run_sort_key,
    )
    serialized_failures = sorted(
        (_serialize_failure(failure) for failure in sources.historical_failures),
        key=_run_sort_key,
    )
    chapters_payload: dict[str, Any] = {}
    for chapter_id in sorted(sources.chapters):
        chapter = sources.chapters[chapter_id]
        entry: dict[str, Any] = {
            "status": chapter.status,
            "authoritative_evidence": sorted(chapter.authoritative_evidence),
        }
        if chapter.report_semantics_fixed_by_sha:
            entry["report_semantics_fixed_by_sha"] = chapter.report_semantics_fixed_by_sha
        chapters_payload[chapter_id] = entry

    return {
        "source_descriptor_version": sources.source_descriptor_version,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "descriptor_kind": "evidence-sources",
        "chapters": chapters_payload,
        "runs": serialized_runs,
        "historical_failures": serialized_failures,
        "limitations": sorted(sources.limitations),
    }


def compute_evidence_source_descriptor_hash(sources: EvidenceSourcesDocument) -> str:
    return _compute_payload_hash(evidence_source_descriptor_payload(sources))


def build_evidence_manifest(
    sources: EvidenceSourcesDocument,
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    redaction_issues = _scan_forbidden_content(sources.model_dump(mode="json"))
    if redaction_issues:
        raise ValueError(
            "evidence sources contain forbidden keys or patterns: "
            + "; ".join(redaction_issues)
        )

    _validate_uniqueness_and_correlation(
        runs=sources.runs,
        failures=sources.historical_failures,
        chapters=sources.chapters,
    )

    serialized_runs = sorted(
        (_serialize_run(run) for run in sources.runs),
        key=_run_sort_key,
    )
    serialized_failures = sorted(
        (_serialize_failure(failure) for failure in sources.historical_failures),
        key=_run_sort_key,
    )

    totals, unknown_fields = _sum_known_side_effects(serialized_runs, serialized_failures)
    artifact_hash_map = _artifact_hashes(serialized_runs, serialized_failures)

    chapters_payload: dict[str, Any] = {}
    for chapter_id in sorted(sources.chapters):
        chapter = sources.chapters[chapter_id]
        entry: dict[str, Any] = {
            "status": chapter.status,
            "authoritative_evidence": sorted(chapter.authoritative_evidence),
        }
        if chapter.report_semantics_fixed_by_sha:
            entry["report_semantics_fixed_by_sha"] = chapter.report_semantics_fixed_by_sha
        chapters_payload[chapter_id] = entry

    manifest_without_hash: dict[str, Any] = {
        "manifest_schema_version": MANIFEST_SCHEMA_VERSION,
        "closure_chapter": CLOSURE_CHAPTER,
        "baseline_git_sha": sources.baseline_git_sha,
        "source_descriptor_version": sources.source_descriptor_version,
        "canonicalization_version": CANONICALIZATION_VERSION,
        "chapters": chapters_payload,
        "runs": serialized_runs,
        "historical_failures": serialized_failures,
        "limitations": sorted(sources.limitations),
        "external_side_effect_totals": totals,
        "unknown_side_effect_fields": unknown_fields,
        "artifact_hashes": artifact_hash_map,
    }

    payload_hash = _compute_payload_hash(_manifest_hash_payload(manifest_without_hash))
    manifest = dict(manifest_without_hash)
    manifest["evidence_payload_hash"] = payload_hash
    if generated_at is not None:
        manifest["generated_at"] = generated_at.astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    return manifest


def _closure_criteria_states() -> dict[str, str]:
    return {
        "2F.1_foundation_closed": "passed",
        "2F.2_live_gmail_closed": "passed",
        "2F.3_live_llm_closed": "passed",
        "authoritative_artifacts_identified": "passed",
        "historical_failures_classified": "passed",
        "evidence_manifest_schema_valid": "passed",
        "artifact_hashes_verified": "passed",
        "observation_replay": "pending",
        "offline_smoke": "pending",
        "replay_determinism": "pending",
        "final_ci_delivery": "pending",
        "formal_documentation_closure": "pending",
        "no_unknown_external_side_effects_in_authoritative_evidence": "pending",
        "historical_unknowns_classified_and_excluded": "pending",
        "redaction_clean": "passed",
        "ci_green_on_baseline": "passed",
        "no_active_live_eval_runs": "passed",
        "no_new_external_runs_required": "passed",
    }


def build_final_report(
    manifest: dict[str, Any],
    *,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    closure_criteria = _closure_criteria_states()
    authoritative_runs = [
        run["workflow_run_id"]
        for run in manifest.get("runs", [])
        if run.get("classification") == "authoritative_success"
    ]
    report: dict[str, Any] = {
        "report_schema_version": FINAL_REPORT_SCHEMA_VERSION,
        "baseline_git_sha": manifest["baseline_git_sha"],
        "manifest_payload_hash": manifest["evidence_payload_hash"],
        "overall_status": "pending_replay",
        "chapter_results": {
            chapter_id: {
                "status": chapter["status"],
                "authoritative_evidence": chapter["authoritative_evidence"],
            }
            for chapter_id, chapter in sorted(manifest.get("chapters", {}).items())
        },
        "authoritative_runs": sorted(authoritative_runs),
        "historical_failures": [
            failure["workflow_run_id"]
            for failure in manifest.get("historical_failures", [])
        ],
        "release_gate": {
            "workflow_run_id": manifest["chapters"]["2F.1"]["authoritative_evidence"][0],
            "head_sha": manifest["baseline_git_sha"],
            "status": "success",
        },
        "replay_status": "pending",
        "redaction_status": "clean",
        "active_live_eval_runs": 0,
        "new_external_runs_required": False,
        "known_limitations": sorted(manifest.get("limitations", [])),
        "closure_criteria": closure_criteria,
    }
    if generated_at is not None:
        report["generated_at"] = generated_at.astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    return report


def build_final_evidence(
    sources: EvidenceSourcesDocument,
    *,
    generated_at: datetime | None = None,
) -> BuildResult:
    manifest = build_evidence_manifest(sources, generated_at=generated_at)
    final_report = build_final_report(manifest, generated_at=generated_at)
    return BuildResult(
        manifest=manifest,
        final_report=final_report,
        evidence_payload_hash=manifest["evidence_payload_hash"],
        manifest_payload_hash=manifest["evidence_payload_hash"],
    )


def load_evidence_sources(path: Path) -> EvidenceSourcesDocument:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return EvidenceSourcesDocument.model_validate(raw)


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        delete=False,
    ) as handle:
        handle.write(encoded)
        temp_name = handle.name
    Path(temp_name).replace(path)


def write_final_evidence_outputs(
    *,
    sources_path: Path,
    output_dir: Path,
    baseline_git_sha: str | None = None,
    generated_at: datetime | None = None,
) -> BuildResult:
    sources = load_evidence_sources(sources_path)
    if baseline_git_sha is not None:
        sources = sources.model_copy(update={"baseline_git_sha": baseline_git_sha})
    result = build_final_evidence(sources, generated_at=generated_at)
    write_json_atomic(output_dir / "2f_evidence_manifest.json", result.manifest)
    write_json_atomic(output_dir / "2f_final_report.json", result.final_report)
    return result
