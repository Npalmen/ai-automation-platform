"""Hermetic tests for Kapitel 2F.4B evidence manifest and final report."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.evaluation.live.final_evidence import (
    CANONICALIZATION_VERSION,
    CLOSURE_CHAPTER,
    EvidenceSourcesDocument,
    FINAL_REPORT_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    SOURCE_DESCRIPTOR_VERSION,
    build_evidence_manifest,
    build_final_evidence,
    build_final_report,
    load_evidence_sources,
)
from app.evaluation.live.redaction import FORBIDDEN_KEYS

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "2f_evidence"
SOURCES_V1 = FIXTURES_DIR / "evidence_sources_v1.json"
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


def _load_v1():
    return load_evidence_sources(SOURCES_V1)


def test_valid_manifest_structure_and_hash():
    sources = _load_v1()
    manifest = build_evidence_manifest(sources)

    assert manifest["manifest_schema_version"] == MANIFEST_SCHEMA_VERSION
    assert manifest["closure_chapter"] == CLOSURE_CHAPTER
    assert manifest["canonicalization_version"] == CANONICALIZATION_VERSION
    assert manifest["source_descriptor_version"] == SOURCE_DESCRIPTOR_VERSION
    assert manifest["baseline_git_sha"] == "b344701b4bdc06207a2273e1f82fcd15fa2760cd"
    assert _SHA256_RE.match(manifest["evidence_payload_hash"])

    chapters = manifest["chapters"]
    assert chapters["2F.1"]["authoritative_evidence"] == ["30133568883"]
    assert chapters["2F.2"]["authoritative_evidence"] == ["30050565974"]
    assert chapters["2F.3"]["authoritative_evidence"] == ["30131333378"]
    assert chapters["2F.3"]["report_semantics_fixed_by_sha"] == (
        "b344701b4bdc06207a2273e1f82fcd15fa2760cd"
    )

    run_ids = [run["workflow_run_id"] for run in manifest["runs"]]
    assert run_ids == sorted(run_ids, key=lambda item: (item, ""))

    failure = manifest["historical_failures"][0]
    assert failure["workflow_run_id"] == "30125105087"
    assert failure["classification"] == "historical_harness_failure"
    assert failure["provider_outcome"] == "unknown"
    assert failure["never_rerun"] is True
    assert failure["never_resume"] is True
    assert failure["never_valid_as_success"] is True
    assert failure["root_cause"] == "PipelinePollResult observation unwrap"
    assert failure["fixed_by_sha"] == "5af00210833e9d78cd7a5033ddd5c796408c8378"

    gmail = next(run for run in manifest["runs"] if run["workflow_run_id"] == "30050565974")
    assert gmail["artifact_schema"] == "2f.2"
    llm = next(run for run in manifest["runs"] if run["workflow_run_id"] == "30131333378")
    assert llm["artifact_schema"] == "2f.3.llm"


def test_payload_hash_deterministic_across_order_and_generated_at():
    sources = _load_v1()
    shuffled = sources.model_copy(
        update={"runs": list(reversed(sources.runs))}
    )
    first = build_evidence_manifest(sources)
    second = build_evidence_manifest(
        shuffled,
        generated_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
    )
    third = build_evidence_manifest(
        sources,
        generated_at=datetime(2000, 6, 15, tzinfo=timezone.utc),
    )

    assert first["evidence_payload_hash"] == second["evidence_payload_hash"]
    assert first["evidence_payload_hash"] == third["evidence_payload_hash"]
    assert "generated_at" not in first
    assert second["generated_at"] == "2099-01-01T00:00:00Z"


def test_historical_failure_cannot_be_authoritative_success():
    sources = _load_v1()
    failure_id = sources.historical_failures[0].evaluation_run_id
    broken_runs = [
        run.model_copy(update={"evaluation_run_id": failure_id})
        if run.workflow_run_id == "30131333378"
        else run
        for run in sources.runs
    ]
    with pytest.raises(ValueError, match="shared with success run"):
        build_evidence_manifest(sources.model_copy(update={"runs": broken_runs}))


def test_failure_run_cannot_be_chapter_authoritative_evidence():
    sources = _load_v1()
    broken = sources.model_copy(
        update={
            "chapters": {
                **sources.chapters,
                "2F.3": sources.chapters["2F.3"].model_copy(
                    update={"authoritative_evidence": ["30125105087"]}
                ),
            }
        }
    )
    with pytest.raises(ValueError, match="unknown workflow_run_id"):
        build_evidence_manifest(broken)


def test_duplicate_evaluation_run_id_rejected():
    sources = _load_v1()
    gmail = next(run for run in sources.runs if run.workflow_run_id == "30050565974")
    llm = next(run for run in sources.runs if run.workflow_run_id == "30131333378")
    broken = sources.model_copy(
        update={
            "runs": [
                run
                if run.workflow_run_id != llm.workflow_run_id
                else run.model_copy(update={"evaluation_run_id": gmail.evaluation_run_id})
                for run in sources.runs
            ]
        }
    )
    with pytest.raises(ValueError, match="duplicate evaluation_run_id"):
        build_evidence_manifest(broken)


def test_dangling_chapter_reference_rejected():
    sources = _load_v1()
    broken = sources.model_copy(
        update={
            "chapters": {
                **sources.chapters,
                "2F.2": sources.chapters["2F.2"].model_copy(
                    update={"authoritative_evidence": ["99999999999"]}
                ),
            }
        }
    )
    with pytest.raises(ValueError, match="unknown workflow_run_id"):
        build_evidence_manifest(broken)


def test_unknown_provider_outcome_not_summed_in_totals():
    manifest = build_evidence_manifest(_load_v1())
    assert manifest["external_side_effect_totals"]["llm_provider_calls"] == 4
    assert "llm_provider_calls" in manifest["unknown_side_effect_fields"]


def test_side_effect_totals_only_sum_known_success_runs():
    manifest = build_evidence_manifest(_load_v1())
    totals = manifest["external_side_effect_totals"]
    assert totals["gmail_sends"] == 1
    assert totals["gmail_mutations"] == 1
    assert totals["external_action_writes"] == 0


def test_redaction_scan_rejects_forbidden_keys():
    from app.evaluation.live.final_evidence import _scan_forbidden_content

    issues = _scan_forbidden_content({"runs": [{"api_key": "secret-value"}]})
    assert issues


def test_redaction_rejects_bearer_pattern():
    raw = json.loads(SOURCES_V1.read_text(encoding="utf-8"))
    raw["limitations"] = ["Bearer abc.def.ghi"]
    with pytest.raises(ValueError, match="forbidden"):
        build_evidence_manifest(load_evidence_sources_from_dict(raw))


def test_fixture_has_no_forbidden_keys():
    raw = json.loads(SOURCES_V1.read_text(encoding="utf-8"))

    def walk(value, path="$"):
        if isinstance(value, dict):
            for key, item in value.items():
                assert key.lower() not in FORBIDDEN_KEYS, f"{path}.{key}"
                walk(item, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]")

    walk(raw)


def test_final_report_pending_state():
    sources = _load_v1()
    result = build_final_evidence(sources)
    report = result.final_report

    assert report["report_schema_version"] == FINAL_REPORT_SCHEMA_VERSION
    assert report["overall_status"] == "pending_replay"
    assert report["replay_status"] == "pending"
    assert report["new_external_runs_required"] is False
    assert report["manifest_payload_hash"] == result.evidence_payload_hash

    criteria = report["closure_criteria"]
    assert criteria["observation_replay"] == "pending"
    assert criteria["offline_smoke"] == "pending"
    assert criteria["replay_determinism"] == "pending"
    assert criteria["final_ci_delivery"] == "pending"
    assert criteria["formal_documentation_closure"] == "pending"
    assert criteria["2F.1_foundation_closed"] == "passed"
    assert criteria["2F.2_live_gmail_closed"] == "passed"
    assert criteria["2F.3_live_llm_closed"] == "passed"


def test_payload_hash_changes_when_verified_field_changes():
    sources = _load_v1()
    baseline_hash = build_evidence_manifest(sources)["evidence_payload_hash"]

    gmail = next(run for run in sources.runs if run.workflow_run_id == "30050565974")
    mutated_runs = [
        run.model_copy(
            update={"external_side_effects": gmail.external_side_effects.model_copy()}
        )
        if run.workflow_run_id != "30050565974"
        else run.model_copy(
            update={
                "external_side_effects": gmail.external_side_effects.model_copy(
                    update={
                        "gmail_sends": gmail.external_side_effects.gmail_sends.model_copy(
                            update={"value": 2}
                        )
                    }
                )
            }
        )
        for run in sources.runs
    ]
    mutated = sources.model_copy(update={"runs": mutated_runs})
    assert build_evidence_manifest(mutated)["evidence_payload_hash"] != baseline_hash


def test_artifact_hash_conflict_rejected():
    sources = _load_v1()
    gmail = next(run for run in sources.runs if run.workflow_run_id == "30050565974")
    readiness = next(run for run in sources.runs if run.workflow_run_id == "30130421434")
    broken_runs = []
    for run in sources.runs:
        if run.workflow_run_id == readiness.workflow_run_id:
            broken_runs.append(
                run.model_copy(
                    update={
                        "artifact_name": gmail.artifact_name,
                        "artifact_file_sha256": readiness.artifact_file_sha256,
                    }
                )
            )
        else:
            broken_runs.append(run)
    broken = sources.model_copy(update={"runs": broken_runs})
    with pytest.raises(ValueError, match="conflicting hashes"):
        build_evidence_manifest(broken)


def test_final_report_overall_status_not_passed_in_2f4b():
    manifest = build_evidence_manifest(_load_v1())
    report = build_final_report(manifest)
    assert report["overall_status"] != "passed"
    assert any(state == "pending" for state in report["closure_criteria"].values())


def load_evidence_sources_from_dict(raw: dict):
    return EvidenceSourcesDocument.model_validate(raw)


def test_build_final_evidence_end_to_end():
    result = build_final_evidence(_load_v1())
    assert result.manifest["evidence_payload_hash"]
    assert result.final_report["manifest_payload_hash"] == result.evidence_payload_hash
