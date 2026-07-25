"""Hermetic tests for Kapitel 2F.4D final closure."""

from __future__ import annotations

import json
import re
import socket
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from app.evaluation.live.closure import (
    CLOSURE_MARKER,
    REQUIRED_CI_CHECKS,
    apply_final_closure,
    build_closure_context,
    finalize_offline_replay_result,
    verify_documentation_closure,
)
from app.evaluation.live.final_evidence import compute_evidence_source_descriptor_hash, load_evidence_sources
from app.evaluation.live.replay_verifier import run_offline_replay

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "2f_evidence"
EVIDENCE_SOURCES = FIXTURES_DIR / "evidence_sources_v1.json"
REPLAY_SOURCES = FIXTURES_DIR / "replay_sources_v1.json"
DOCS_ROOT = Path(__file__).resolve().parents[3]
RELEASE_GATE_PATH = DOCS_ROOT / ".github" / "workflows" / "release-gate.yml"
_BASELINE_SHA = "74407fefaa4f753b7a7e1862046cd719a2a61480"
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")


def _success_checks() -> dict[str, str]:
    return {name: "success" for name in REQUIRED_CI_CHECKS}


def _closure_context(**overrides):
    defaults = {
        "baseline_git_sha": _BASELINE_SHA,
        "ci_event": "push",
        "ci_branch": "main",
        "ci_run_id": "synthetic-test-000001",
        "ci_head_sha": _BASELINE_SHA,
        "required_checks": _success_checks(),
        "documentation_root": DOCS_ROOT,
    }
    defaults.update(overrides)
    return build_closure_context(**defaults)


def _offline_result(baseline_sha: str = _BASELINE_SHA):
    return run_offline_replay(
        evidence_sources_path=EVIDENCE_SOURCES,
        replay_sources_path=REPLAY_SOURCES,
        baseline_git_sha=baseline_sha,
    )


def test_valid_final_closure_passes():
    result = _offline_result()
    closed = finalize_offline_replay_result(result, _closure_context())
    criteria = closed.final_report["closure_criteria"]

    assert closed.final_report["overall_status"] == "passed"
    assert closed.final_report["replay_status"] == "passed"
    assert closed.final_report["new_external_runs_required"] is False
    assert criteria["final_ci_delivery"] == "passed"
    assert criteria["formal_documentation_closure"] == "passed"
    assert all(value == "passed" for value in criteria.values())
    assert closed.final_report["ci_delivery"]["run_id"] == "synthetic-test-000001"
    assert closed.final_report["documentation_closure"]["closure_marker"] == CLOSURE_MARKER


def test_pr_event_denied():
    result = _offline_result()
    with pytest.raises(ValueError, match="requires ci event push"):
        finalize_offline_replay_result(
            result,
            _closure_context(ci_event="pull_request"),
        )


def test_wrong_branch_denied():
    result = _offline_result()
    with pytest.raises(ValueError, match="requires ci branch main"):
        finalize_offline_replay_result(
            result,
            _closure_context(ci_branch="feat/example"),
        )


def test_sha_mismatch_denied():
    result = _offline_result()
    with pytest.raises(ValueError, match="baseline_git_sha must match ci_head_sha"):
        finalize_offline_replay_result(
            result,
            _closure_context(ci_head_sha="1" * 40),
        )


@pytest.mark.parametrize(
    "checks",
    [
        {**_success_checks(), "tests": "failure"},
        {**_success_checks(), "docker": "cancelled"},
        {**_success_checks(), "frontend": "skipped"},
        {k: v for k, v in _success_checks().items() if k != "tests"},
    ],
)
def test_required_check_failure_denied(checks):
    result = _offline_result()
    with pytest.raises(ValueError):
        finalize_offline_replay_result(result, _closure_context(required_checks=checks))


def test_missing_documentation_marker_denied(tmp_path):
    result = _offline_result()
    fake_root = tmp_path / "repo"
    for relative in (
        "docs/01-current-truth.md",
        "docs/06-backlog.md",
        "docs/09-testing-and-release.md",
        "docs/10f-live-eval-testbot.md",
    ):
        path = fake_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder without marker\n", encoding="utf-8")

    with pytest.raises(ValueError, match="closure marker missing"):
        finalize_offline_replay_result(
            result,
            _closure_context(documentation_root=fake_root),
        )


def test_replay_not_passed_denied():
    result = _offline_result()
    result.replay_report["overall_status"] = "failed"
    with pytest.raises(ValueError, match="replay report overall_status must be passed"):
        apply_final_closure(
            manifest=result.manifest,
            replay_report=result.replay_report,
            final_report=result.final_report,
            context=_closure_context(),
            documentation_status=verify_documentation_closure(DOCS_ROOT),
        )


def test_wrong_manifest_hash_denied():
    result = _offline_result()
    result.replay_report["evidence_manifest_payload_hash"] = "0" * 64
    with pytest.raises(ValueError, match="manifest evidence_payload_hash does not match"):
        apply_final_closure(
            manifest=result.manifest,
            replay_report=result.replay_report,
            final_report=result.final_report,
            context=_closure_context(),
            documentation_status=verify_documentation_closure(DOCS_ROOT),
        )


def test_authoritative_unknown_denied():
    evidence_sources = load_evidence_sources(EVIDENCE_SOURCES).model_copy(
        update={"baseline_git_sha": _BASELINE_SHA}
    )
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
    from app.evaluation.live.replay_verifier import build_replay_report, load_replay_sources
    from app.evaluation.live.final_evidence import build_evidence_manifest
    from app.evaluation.live.replay_verifier import build_final_report_with_replay

    manifest = build_evidence_manifest(mutated_sources)
    replay_sources = load_replay_sources(REPLAY_SOURCES).model_copy(
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
        baseline_git_sha=_BASELINE_SHA,
    )
    final_report = build_final_report_with_replay(
        manifest,
        replay_report,
        baseline_git_sha=_BASELINE_SHA,
    )
    with pytest.raises(ValueError, match="authoritative evidence contains unknown side effects"):
        apply_final_closure(
            manifest=manifest,
            replay_report=replay_report,
            final_report=final_report,
            context=_closure_context(),
            documentation_status=verify_documentation_closure(DOCS_ROOT),
        )


def test_historical_unknown_still_allows_closure():
    result = _offline_result()
    failure = result.manifest["historical_failures"][0]
    assert failure["provider_outcome"] == "unknown"
    closed = finalize_offline_replay_result(result, _closure_context())
    assert closed.final_report["overall_status"] == "passed"
    assert (
        closed.final_report["closure_criteria"][
            "historical_unknowns_classified_and_excluded"
        ]
        == "passed"
    )


def test_candidate_mode_pending_closure():
    result = _offline_result()
    assert result.final_report["overall_status"] == "pending_closure"
    assert result.final_report["closure_criteria"]["final_ci_delivery"] == "pending"


def test_closure_deterministic_despite_generated_at():
    first = finalize_offline_replay_result(
        run_offline_replay(
            evidence_sources_path=EVIDENCE_SOURCES,
            replay_sources_path=REPLAY_SOURCES,
            baseline_git_sha=_BASELINE_SHA,
        ),
        _closure_context(),
    )
    second = finalize_offline_replay_result(
        run_offline_replay(
            evidence_sources_path=EVIDENCE_SOURCES,
            replay_sources_path=REPLAY_SOURCES,
            baseline_git_sha=_BASELINE_SHA,
            generated_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        ),
        _closure_context(ci_run_id="synthetic-test-000001"),
    )
    assert first.final_report["manifest_payload_hash"] == second.final_report["manifest_payload_hash"]
    assert first.replay_payload_hash == second.replay_payload_hash


def test_documentation_closure_verifier():
    status = verify_documentation_closure(DOCS_ROOT)
    assert status["status"] == "closed"
    assert CLOSURE_MARKER in status["closure_marker"]
    assert "docs/01-current-truth.md" in status["verified_files"]
    assert "docs/06-backlog.md" in status["verified_files"]


def test_documentation_contains_required_status():
    truth = (DOCS_ROOT / "docs/01-current-truth.md").read_text(encoding="utf-8")
    backlog = (DOCS_ROOT / "docs/06-backlog.md").read_text(encoding="utf-8")
    release = (DOCS_ROOT / "docs/09-testing-and-release.md").read_text(encoding="utf-8")
    testbot = (DOCS_ROOT / "docs/10f-live-eval-testbot.md").read_text(encoding="utf-8")

    assert CLOSURE_MARKER in truth
    for chapter in ("2F.1", "2F.2", "2F.3", "2F.4"):
        assert chapter in truth
    assert "30050565974" in truth
    assert "30131333378" in truth
    assert "30125105087" in truth
    assert "2G" in backlog
    assert "2F.3+ — Live LLM E2E" not in backlog or "Not started" not in backlog
    assert "30050565974" in testbot
    assert "30131333378" in testbot
    assert "provider_outcome" in testbot

    for doc in (truth, backlog, release, testbot):
        assert "final-2f-evidence" in doc
        assert "2f-final-evidence" in doc
        assert "overall_status=passed" in doc or "overall_status = passed" in doc
        assert "74407fe" not in doc
        assert "stängt @ `74407fe`" not in doc


def test_documentation_rejects_premature_official_closure_claims(tmp_path):
    fake_root = tmp_path / "repo"
    for relative in (
        "docs/01-current-truth.md",
        "docs/06-backlog.md",
        "docs/09-testing-and-release.md",
        "docs/10f-live-eval-testbot.md",
    ):
        path = fake_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                [
                    CLOSURE_MARKER,
                    "2F.1",
                    "2F.2",
                    "2F.3",
                    "2F.4",
                    "final-2f-evidence",
                    "2f-final-evidence-<main-sha>",
                    "overall_status=passed",
                    "30050565974",
                    "30131333378",
                    "30125105087",
                    "provider_outcome",
                    "2G",
                    "stängt @ `74407fe`",
                ]
            ),
            encoding="utf-8",
        )
    with pytest.raises(ValueError, match="forbidden pre-merge claim"):
        verify_documentation_closure(fake_root)


def test_release_gate_final_evidence_job_contract():
    data = yaml.safe_load(RELEASE_GATE_PATH.read_text(encoding="utf-8"))
    job = data["jobs"]["final-2f-evidence"]
    assert job["if"] == "github.event_name == 'push' && github.ref == 'refs/heads/main'"
    assert job["needs"] == ["tests", "live-eval-postgres", "frontend", "docker"]
    assert "always()" not in job.get("if", "")
    assert "workflow_dispatch" not in str(job)

    steps = job["steps"]
    build_step = next(step for step in steps if step.get("name") == "Build and finalize 2F evidence package")
    build_run = build_step["run"]
    build_env = build_step.get("env") or {}
    assert build_env["OUTPUT_DIR"] == "${{ runner.temp }}/2f-final-evidence"
    assert "--finalize-closure" in build_run
    assert '--baseline-git-sha "${GITHUB_SHA}"' in build_run
    assert '--ci-run-id "${GITHUB_RUN_ID}"' in build_run
    assert '--ci-event "${{ github.event_name }}"' in build_run
    assert '--ci-branch "${{ github.ref_name }}"' in build_run
    assert "--required-check tests=${{ needs.tests.result }}" in build_run
    assert "--required-check live_eval_postgresql=${{ needs['live-eval-postgres'].result }}" in build_run
    assert "--required-check frontend=${{ needs.frontend.result }}" in build_run
    assert "--required-check docker=${{ needs.docker.result }}" in build_run
    assert "--required-check tests=success" not in build_run
    assert "--required-check live_eval_postgresql=success" not in build_run
    assert "--required-check frontend=success" not in build_run
    assert "--required-check docker=success" not in build_run
    assert "run_2f_offline_replay.py" in build_run
    assert "gmail" not in build_run.lower()
    assert "openai" not in build_run.lower()
    assert "postgres" not in build_run.lower() or "live_eval_postgresql" in build_run

    upload_step = next(step for step in steps if "Upload 2F final evidence artifact" in step.get("name", ""))
    assert upload_step["uses"] == "actions/upload-artifact@v4"
    artifact_name = upload_step["with"]["name"]
    assert artifact_name == "2f-final-evidence-${{ github.sha }}"
    upload_paths = upload_step["with"]["path"]
    assert upload_paths.count("2f_evidence_manifest.json") == 1
    assert upload_paths.count("2f_replay_report.json") == 1
    assert upload_paths.count("2f_final_report.json") == 1
    assert "${{ runner.temp }}/2f-final-evidence" in upload_paths
    assert upload_step["with"]["if-no-files-found"] == "error"


def test_no_network_socket_blocked_for_closure(monkeypatch):
    def _blocked(*_args, **_kwargs):
        raise OSError("network blocked in closure tests")

    monkeypatch.setattr(socket, "socket", _blocked)
    closed = finalize_offline_replay_result(_offline_result(), _closure_context())
    assert closed.replay_report["no_network"] is True
    assert closed.final_report["overall_status"] == "passed"
