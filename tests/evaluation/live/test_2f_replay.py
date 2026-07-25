"""Hermetic tests for Kapitel 2F.4C offline replay."""

from __future__ import annotations

import json
import re
import socket
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pydantic import ValidationError

from app.evaluation.live.final_evidence import (
    FINAL_REPORT_SCHEMA_VERSION,
    build_evidence_manifest,
    compute_evidence_source_descriptor_hash,
    load_evidence_sources,
)
from app.evaluation.live.replay_verifier import (
    REPLAY_SCHEMA_VERSION,
    ReplaySourcesDocument,
    build_final_report_with_replay,
    build_replay_report,
    load_replay_sources,
    run_offline_replay,
)

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "2f_evidence"
EVIDENCE_SOURCES = FIXTURES_DIR / "evidence_sources_v1.json"
REPLAY_SOURCES = FIXTURES_DIR / "replay_sources_v1.json"
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_BASELINE_A = "dd65822c56a9f3cbb53b5a965b3aa95d677ad0ed"
_BASELINE_B = "1111111111111111111111111111111111111111"


def _load_evidence(baseline_sha: str | None = None):
    sources = load_evidence_sources(EVIDENCE_SOURCES)
    if baseline_sha is not None:
        sources = sources.model_copy(update={"baseline_git_sha": baseline_sha})
    return sources


def _build_manifest(baseline_sha: str = _BASELINE_A):
    return build_evidence_manifest(_load_evidence(baseline_sha))


def _load_replay():
    return load_replay_sources(REPLAY_SOURCES)


def _build_replay_report(baseline_sha: str = _BASELINE_A, **kwargs):
    manifest = _build_manifest(baseline_sha)
    return build_replay_report(
        manifest=manifest,
        evidence_sources=_load_evidence(baseline_sha),
        sources=_load_replay(),
        baseline_git_sha=baseline_sha,
        **kwargs,
    )


def test_valid_replay_all_steps_passed():
    report = _build_replay_report()

    assert report["replay_schema_version"] == REPLAY_SCHEMA_VERSION
    assert report["overall_status"] == "passed"
    assert report["no_network"] is True
    assert report["evidence_source_descriptor_hash"] == _load_replay().evidence_source_descriptor_hash
    assert report["baseline_git_sha"] == _BASELINE_A
    assert report["external_side_effects"] == {
        "gmail_sends": 0,
        "gmail_reads": 0,
        "gmail_mutations": 0,
        "llm_provider_calls": 0,
        "app_replies": 0,
        "approval_resolutions": 0,
        "external_action_writes": 0,
    }
    assert _SHA256_RE.match(report["replay_payload_hash"])
    step_ids = [step["step_id"] for step in report["steps"]]
    assert step_ids == sorted(step_ids)
    assert step_ids == [
        "final_evidence_contract_smoke",
        "gmail_artifact_contract",
        "historical_failure_classification",
        "llm_artifact_contract",
        "llm_observation_report_regeneration",
    ]
    assert all(step["status"] == "passed" for step in report["steps"])


def test_llm_regeneration_exact_totals():
    report = _build_replay_report()
    step = next(
        item
        for item in report["steps"]
        if item["step_id"] == "llm_observation_report_regeneration"
    )
    assertions = step["assertions"]
    assert assertions["attempted"]["passed"] is True
    assert assertions["succeeded"]["passed"] is True
    assert assertions["operations_length"]["passed"] is True
    assert assertions["input_tokens"]["passed"] is True
    assert assertions["output_tokens"]["passed"] is True
    assert assertions["total_tokens"]["passed"] is True
    assert assertions["latency_ms"]["passed"] is True
    assert assertions["output_hashes"]["passed"] is True


def test_two_baselines_without_fixture_change():
    """Test A — two baseline SHAs without fixture change."""
    report_a = _build_replay_report(_BASELINE_A)
    report_b = _build_replay_report(_BASELINE_B)

    assert report_a["overall_status"] == "passed"
    assert report_b["overall_status"] == "passed"
    assert report_a["evidence_source_descriptor_hash"] == report_b["evidence_source_descriptor_hash"]
    assert report_a["evidence_manifest_payload_hash"] != report_b["evidence_manifest_payload_hash"]
    assert report_a["replay_payload_hash"] != report_b["replay_payload_hash"]
    assert report_a["baseline_git_sha"] == _BASELINE_A
    assert report_b["baseline_git_sha"] == _BASELINE_B


def test_wrong_source_descriptor_hash_fail_closed():
    """Test B — wrong source descriptor hash."""
    manifest = _build_manifest()
    sources = _load_replay().model_copy(
        update={"evidence_source_descriptor_hash": "0" * 64}
    )
    with pytest.raises(ValueError, match="evidence_source_descriptor_hash does not match"):
        build_replay_report(
            manifest=manifest,
            evidence_sources=_load_evidence(_BASELINE_A),
            sources=sources,
            baseline_git_sha=_BASELINE_A,
        )


def test_changed_evidence_source_without_hash_fail_closed():
    """Test C — changed evidence source without hash update."""
    manifest = _build_manifest()
    evidence_sources = _load_evidence(_BASELINE_A)
    mutated = evidence_sources.model_copy(
        update={"limitations": evidence_sources.limitations + ["new limitation"]}
    )
    with pytest.raises(ValueError, match="evidence_source_descriptor_hash does not match"):
        build_replay_report(
            manifest=manifest,
            evidence_sources=mutated,
            sources=_load_replay(),
            baseline_git_sha=_BASELINE_A,
        )


def test_wrong_runtime_manifest_hash_fail_closed():
    """Test D — wrong runtime manifest hash binding."""
    manifest = _build_manifest()
    replay_report = _build_replay_report()
    replay_report["evidence_manifest_payload_hash"] = "0" * 64
    with pytest.raises(ValueError, match="manifest evidence_payload_hash does not match"):
        build_final_report_with_replay(
            manifest,
            replay_report,
            baseline_git_sha=_BASELINE_A,
        )


def test_crossed_baseline_fail_closed():
    """Test E — crossed baseline between manifest and replay."""
    manifest_a = _build_manifest(_BASELINE_A)
    replay_b = _build_replay_report(_BASELINE_B)
    with pytest.raises(ValueError, match="manifest baseline_git_sha does not match replay report"):
        build_final_report_with_replay(
            manifest_a,
            replay_b,
            baseline_git_sha=_BASELINE_A,
        )


def test_replay_determinism_across_order_and_generated_at():
    """Test F — determinism across irrelevant ordering."""
    manifest = _build_manifest()
    sources = _load_replay()
    evidence_sources = _load_evidence(_BASELINE_A)
    first = build_replay_report(
        manifest=manifest,
        evidence_sources=evidence_sources,
        sources=sources,
        baseline_git_sha=_BASELINE_A,
    )
    shuffled_events = list(reversed(sources.llm_telemetry_events))
    shuffled = sources.model_copy(update={"llm_telemetry_events": shuffled_events})
    second = build_replay_report(
        manifest=manifest,
        evidence_sources=evidence_sources,
        sources=shuffled,
        baseline_git_sha=_BASELINE_A,
        generated_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
    )
    assert first["replay_payload_hash"] == second["replay_payload_hash"]
    assert "generated_at" not in first
    assert second["generated_at"] == "2099-01-01T00:00:00Z"

    shuffled_runs = evidence_sources.model_copy(
        update={"runs": list(reversed(evidence_sources.runs))}
    )
    assert compute_evidence_source_descriptor_hash(shuffled_runs) == first[
        "evidence_source_descriptor_hash"
    ]
    assert build_evidence_manifest(shuffled_runs)["evidence_payload_hash"] == manifest[
        "evidence_payload_hash"
    ]


def test_source_change_updates_all_hashes():
    """Test G — verified source field change updates hashes."""
    baseline_descriptor = compute_evidence_source_descriptor_hash(_load_evidence(_BASELINE_A))
    baseline_report = _build_replay_report()

    evidence_sources = _load_evidence(_BASELINE_A)
    gmail = next(run for run in evidence_sources.runs if run.workflow_run_id == "30050565974")
    mutated_runs = [
        run.model_copy(
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
        if run.workflow_run_id == "30050565974"
        else run
        for run in evidence_sources.runs
    ]
    mutated_sources = evidence_sources.model_copy(update={"runs": mutated_runs})
    mutated_manifest = build_evidence_manifest(mutated_sources)
    mutated_descriptor = compute_evidence_source_descriptor_hash(mutated_sources)

    assert mutated_descriptor != baseline_descriptor
    assert mutated_manifest["evidence_payload_hash"] != baseline_report[
        "evidence_manifest_payload_hash"
    ]

    with pytest.raises(ValueError, match="evidence_source_descriptor_hash does not match"):
        build_replay_report(
            manifest=mutated_manifest,
            evidence_sources=mutated_sources,
            sources=_load_replay(),
            baseline_git_sha=_BASELINE_A,
        )


def test_historical_unknown_does_not_block_closure():
    """Test H — historical unknown does not block closure."""
    manifest = _build_manifest()
    replay_report = _build_replay_report()
    final_report = build_final_report_with_replay(
        manifest,
        replay_report,
        baseline_git_sha=_BASELINE_A,
    )

    failure = manifest["historical_failures"][0]
    assert failure["provider_outcome"] == "unknown"
    criteria = final_report["closure_criteria"]
    assert criteria["no_unknown_external_side_effects_in_authoritative_evidence"] == "passed"
    assert criteria["historical_unknowns_classified_and_excluded"] == "passed"
    assert "provider outcome remains unknown" in " ".join(final_report["known_limitations"]).lower() or any(
        "unknown" in item.lower() for item in final_report["known_limitations"]
    )
    assert final_report["overall_status"] == "pending_closure"


def test_unknown_in_authoritative_success_blocks_closure():
    """Test I — unknown in authoritative evidence blocks closure."""
    evidence_sources = _load_evidence(_BASELINE_A)
    gate = next(run for run in evidence_sources.runs if run.workflow_run_id == "30133568883")
    mutated_runs = [
        run.model_copy(
            update={
                "external_side_effects": gate.external_side_effects.model_copy(
                    update={
                        "llm_provider_calls": gate.external_side_effects.llm_provider_calls.model_copy(
                            update={"known": False, "value": "unknown"}
                        )
                    }
                )
            }
        )
        if run.workflow_run_id == "30133568883"
        else run
        for run in evidence_sources.runs
    ]
    mutated_sources = evidence_sources.model_copy(update={"runs": mutated_runs})
    manifest = build_evidence_manifest(mutated_sources)
    replay_sources = _load_replay().model_copy(
        update={
            "evidence_source_descriptor_hash": compute_evidence_source_descriptor_hash(
                mutated_sources
            )
        }
    )
    replay_report = build_replay_report(
        manifest=manifest,
        evidence_sources=mutated_sources,
        sources=replay_sources,
        baseline_git_sha=_BASELINE_A,
    )
    final_report = build_final_report_with_replay(
        manifest,
        replay_report,
        baseline_git_sha=_BASELINE_A,
    )

    assert replay_report["overall_status"] == "passed"
    assert (
        final_report["closure_criteria"][
            "no_unknown_external_side_effects_in_authoritative_evidence"
        ]
        == "failed"
    )
    assert final_report["overall_status"] == "pending_replay"


def test_historical_failure_rejects_zero_provider_calls_in_reference():
    raw = json.loads(REPLAY_SOURCES.read_text(encoding="utf-8"))
    raw["historical_failure_reference"]["provider_outcome"] = "0"
    with pytest.raises(ValidationError):
        ReplaySourcesDocument.model_validate(raw)


def test_artifact_hash_mismatch_fails_step():
    manifest = _build_manifest()
    sources = _load_replay()
    broken = sources.model_copy(
        update={
            "gmail_artifact_reference": sources.gmail_artifact_reference.model_copy(
                update={"artifact_file_sha256": "0" * 64}
            )
        }
    )
    report = build_replay_report(
        manifest=manifest,
        evidence_sources=_load_evidence(_BASELINE_A),
        sources=broken,
        baseline_git_sha=_BASELINE_A,
    )
    assert report["overall_status"] == "failed"
    gmail_step = next(
        step for step in report["steps"] if step["step_id"] == "gmail_artifact_contract"
    )
    assert gmail_step["status"] == "failed"


def test_historical_failure_provider_outcome_must_remain_unknown():
    raw = json.loads(REPLAY_SOURCES.read_text(encoding="utf-8"))
    raw["historical_failure_reference"]["provider_outcome"] = "succeeded"
    with pytest.raises(ValidationError):
        ReplaySourcesDocument.model_validate(raw)


def test_replay_payload_hash_changes_when_verified_field_changes():
    manifest = _build_manifest()
    baseline = _build_replay_report()
    sources = _load_replay()
    mutated = sources.model_copy(
        update={
            "expected_replay_results": {
                **sources.expected_replay_results,
                "llm_regeneration": {
                    **sources.expected_replay_results["llm_regeneration"],
                    "latency_ms": 9999,
                },
            }
        }
    )
    report = build_replay_report(
        manifest=manifest,
        evidence_sources=_load_evidence(_BASELINE_A),
        sources=mutated,
        baseline_git_sha=_BASELINE_A,
    )
    assert report["overall_status"] == "failed"
    assert report["replay_payload_hash"] != baseline["replay_payload_hash"]


def test_no_network_socket_blocked(monkeypatch):
    def _blocked(*_args, **_kwargs):
        raise OSError("network blocked in replay tests")

    monkeypatch.setattr(socket, "socket", _blocked)
    result = run_offline_replay(
        evidence_sources_path=EVIDENCE_SOURCES,
        replay_sources_path=REPLAY_SOURCES,
        baseline_git_sha=_BASELINE_A,
    )
    assert result.replay_report["no_network"] is True


def test_redaction_rejects_forbidden_replay_content():
    raw = json.loads(REPLAY_SOURCES.read_text(encoding="utf-8"))
    raw["llm_telemetry_events"][0]["prompt"] = "secret prompt body"
    with pytest.raises(ValueError, match="forbidden"):
        load_replay_sources_from_dict(raw)


def test_final_report_transition_pending_closure():
    manifest = _build_manifest()
    replay_report = _build_replay_report()
    final_report = build_final_report_with_replay(
        manifest,
        replay_report,
        baseline_git_sha=_BASELINE_A,
    )

    assert final_report["report_schema_version"] == FINAL_REPORT_SCHEMA_VERSION
    assert final_report["overall_status"] == "pending_closure"
    assert final_report["replay_status"] == "passed"
    assert final_report["new_external_runs_required"] is False
    assert final_report["replay_report_schema"] == REPLAY_SCHEMA_VERSION
    assert final_report["replay_report_payload_hash"] == replay_report["replay_payload_hash"]
    assert final_report["evidence_source_descriptor_hash"] == replay_report[
        "evidence_source_descriptor_hash"
    ]
    criteria = final_report["closure_criteria"]
    assert criteria["observation_replay"] == "passed"
    assert criteria["offline_smoke"] == "passed"
    assert criteria["replay_determinism"] == "passed"
    assert criteria["final_ci_delivery"] == "pending"
    assert criteria["formal_documentation_closure"] == "pending"
    assert criteria["no_unknown_external_side_effects_in_authoritative_evidence"] == "passed"
    assert criteria["historical_unknowns_classified_and_excluded"] == "passed"
    assert final_report["overall_status"] != "passed"


def test_failed_replay_keeps_pending_replay():
    manifest = _build_manifest()
    sources = _load_replay().model_copy(
        update={"evidence_source_descriptor_hash": "0" * 64}
    )
    with pytest.raises(ValueError):
        build_replay_report(
            manifest=manifest,
            evidence_sources=_load_evidence(_BASELINE_A),
            sources=sources,
            baseline_git_sha=_BASELINE_A,
        )

    failed_report = {
        "replay_schema_version": REPLAY_SCHEMA_VERSION,
        "overall_status": "failed",
        "replay_payload_hash": "0" * 64,
        "baseline_git_sha": _BASELINE_A,
        "evidence_manifest_payload_hash": manifest["evidence_payload_hash"],
        "evidence_source_descriptor_hash": _load_replay().evidence_source_descriptor_hash,
    }
    final_report = build_final_report_with_replay(
        manifest,
        failed_report,
        baseline_git_sha=_BASELINE_A,
    )
    assert final_report["overall_status"] == "pending_replay"
    assert final_report["replay_status"] == "failed"


def test_run_offline_replay_end_to_end():
    result = run_offline_replay(
        evidence_sources_path=EVIDENCE_SOURCES,
        replay_sources_path=REPLAY_SOURCES,
        baseline_git_sha=_BASELINE_A,
    )
    assert result.replay_report["overall_status"] == "passed"
    assert result.final_report["overall_status"] == "pending_closure"


def load_replay_sources_from_dict(raw: dict) -> ReplaySourcesDocument:
    doc = ReplaySourcesDocument.model_validate(raw)
    from app.evaluation.live.final_evidence import _scan_forbidden_content

    issues = _scan_forbidden_content(raw)
    if issues:
        raise ValueError("replay sources contain forbidden keys or patterns: " + "; ".join(issues))
    return doc
