"""Hermetic tests for Kapitel 2G final closure."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from app.evaluation.closure_2g import (
    CLOSURE_MARKER,
    REQUIRED_CI_CHECKS,
    build_closure_context,
    build_final_report,
    verify_documentation_closure,
)

DOCS_ROOT = Path(__file__).resolve().parents[2]
RELEASE_GATE_PATH = DOCS_ROOT / ".github" / "workflows" / "release-gate.yml"
_BASELINE_SHA = "ad34495b5ef19155d3016559c57a927dd9b848c9"


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


def _passing_metrics() -> dict:
    return {
        "scenario_pass_rate": 1.0,
        "classification_accuracy": 1.0,
        "service_profile_accuracy": 1.0,
        "critical_entity_recall": 1.0,
        "unknown_recall": 1.0,
        "decision_authorization_correctness": 1.0,
        "deterministic_replay_rate": 1.0,
        "canonical_regression_count": 0,
        "approval_first_violation_count": 0,
        "external_write_violation_count": 0,
        "external_action_writes": 0,
        "injection_bypass_count": 0,
        "response_safety_violation_count": 0,
        "no_network": True,
        "openai_calls": 0,
        "gmail_calls": 0,
    }


def _passing_batch_report() -> dict:
    metrics = _passing_metrics()
    gates = {name: "passed" for name in (
        "external_action_violations",
        "approval_first_violations",
        "injection_bypasses",
        "canonical_regressions",
        "no_network",
        "openai_calls_zero",
        "gmail_calls_zero",
        "failure_corpus_empty",
    )}
    quality = {name: "passed" for name in (
        "classification_accuracy",
        "service_profile_accuracy",
        "critical_entity_recall",
        "unknown_recall",
        "decision_authorization_correctness",
        "deterministic_replay_rate",
        "scenario_pass_rate",
    )}
    return {
        "baseline_git_sha": _BASELINE_SHA,
        "overall_status": "passed",
        "batch_payload_hash": "a" * 64,
        "metrics": metrics,
        "blocking_gates": gates,
        "quality_gates": quality,
        "no_network": True,
        "external_side_effects": {
            "openai_calls": 0,
            "gmail_calls": 0,
            "external_action_writes": 0,
        },
    }


def _passing_artifacts() -> tuple[dict, dict, dict, dict]:
    generation_manifest = {
        "generation_payload_hash": "b" * 64,
    }
    failures = {"failures_payload_hash": "c" * 64}
    coverage = {"coverage_payload_hash": "d" * 64}
    batch_report = _passing_batch_report()
    return batch_report, generation_manifest, failures, coverage


def test_valid_final_closure_passes():
    batch_report, generation_manifest, failures, coverage = _passing_artifacts()
    context = _closure_context()
    documentation_status = verify_documentation_closure(DOCS_ROOT)
    final_report = build_final_report(
        batch_report=batch_report,
        generation_manifest=generation_manifest,
        failures=failures,
        coverage=coverage,
        context=context,
        documentation_status=documentation_status,
        pr_batch_status="passed",
    )
    criteria = final_report["closure_criteria"]

    assert final_report["overall_status"] == "passed"
    assert final_report["pr_batch_status"] == "passed"
    assert final_report["main_batch_status"] == "passed"
    assert criteria["pr_batch_passed"] == "passed"
    assert criteria["main_batch_passed"] == "passed"
    assert criteria["documentation_closure"] == "passed"
    assert all(value == "passed" for value in criteria.values())
    assert final_report["ci_delivery"]["run_id"] == "synthetic-test-000001"
    assert final_report["documentation_closure"]["closure_marker"] == CLOSURE_MARKER


def test_pr_event_denied():
    batch_report, generation_manifest, failures, coverage = _passing_artifacts()
    with pytest.raises(ValueError, match="requires ci event push"):
        build_final_report(
            batch_report=batch_report,
            generation_manifest=generation_manifest,
            failures=failures,
            coverage=coverage,
            context=_closure_context(ci_event="pull_request"),
            documentation_status=verify_documentation_closure(DOCS_ROOT),
            pr_batch_status="passed",
        )


def test_wrong_branch_denied():
    batch_report, generation_manifest, failures, coverage = _passing_artifacts()
    with pytest.raises(ValueError, match="requires ci branch main"):
        build_final_report(
            batch_report=batch_report,
            generation_manifest=generation_manifest,
            failures=failures,
            coverage=coverage,
            context=_closure_context(ci_branch="feat/example"),
            documentation_status=verify_documentation_closure(DOCS_ROOT),
            pr_batch_status="passed",
        )


def test_sha_mismatch_denied():
    batch_report, generation_manifest, failures, coverage = _passing_artifacts()
    with pytest.raises(ValueError, match="baseline_git_sha must match ci_head_sha"):
        build_final_report(
            batch_report=batch_report,
            generation_manifest=generation_manifest,
            failures=failures,
            coverage=coverage,
            context=_closure_context(ci_head_sha="1" * 40),
            documentation_status=verify_documentation_closure(DOCS_ROOT),
            pr_batch_status="passed",
        )


@pytest.mark.parametrize(
    "checks",
    [
        {**_success_checks(), "tests": "failure"},
        {**_success_checks(), "docker": "cancelled"},
        {**_success_checks(), "frontend": "skipped"},
        {**_success_checks(), "2g_main_eval": "failure"},
        {k: v for k, v in _success_checks().items() if k != "tests"},
    ],
)
def test_required_check_failure_denied(checks):
    batch_report, generation_manifest, failures, coverage = _passing_artifacts()
    with pytest.raises(ValueError):
        build_final_report(
            batch_report=batch_report,
            generation_manifest=generation_manifest,
            failures=failures,
            coverage=coverage,
            context=_closure_context(required_checks=checks),
            documentation_status=verify_documentation_closure(DOCS_ROOT),
            pr_batch_status="passed",
        )


def test_missing_documentation_marker_denied(tmp_path):
    fake_root = tmp_path / "repo"
    for relative in (
        "docs/01-current-truth.md",
        "docs/06-backlog.md",
        "docs/09-testing-and-release.md",
        "docs/10g-generated-scenario-eval.md",
    ):
        path = fake_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("placeholder without marker\n", encoding="utf-8")

    with pytest.raises(ValueError, match="closure marker missing"):
        verify_documentation_closure(fake_root)


def test_candidate_mode_pending_closure():
    batch_report, generation_manifest, failures, coverage = _passing_artifacts()
    final_report = build_final_report(
        batch_report=batch_report,
        generation_manifest=generation_manifest,
        failures=failures,
        coverage=coverage,
        context=None,
        documentation_status=None,
        pr_batch_status="passed",
    )
    assert final_report["overall_status"] == "pending_closure"


def test_documentation_closure_verifier():
    status = verify_documentation_closure(DOCS_ROOT)
    assert status["status"] == "closed"
    assert CLOSURE_MARKER in status["closure_marker"]
    assert "docs/10g-generated-scenario-eval.md" in status["verified_files"]


def test_documentation_contains_required_status():
    truth = (DOCS_ROOT / "docs/01-current-truth.md").read_text(encoding="utf-8")
    backlog = (DOCS_ROOT / "docs/06-backlog.md").read_text(encoding="utf-8")
    release = (DOCS_ROOT / "docs/09-testing-and-release.md").read_text(encoding="utf-8")
    generated = (DOCS_ROOT / "docs/10g-generated-scenario-eval.md").read_text(encoding="utf-8")

    assert CLOSURE_MARKER in truth
    assert "2G" in backlog
    assert "2g-generator-v1" in generated
    assert "2g-mutation-v1" in generated
    for doc in (truth, backlog, release, generated):
        assert "final-2g-evidence" in doc
        assert "2g-final-evidence" in doc
        assert "overall_status=passed" in doc or "overall_status = passed" in doc


def test_documentation_rejects_premature_official_closure_claims(tmp_path):
    fake_root = tmp_path / "repo"
    for relative in (
        "docs/01-current-truth.md",
        "docs/06-backlog.md",
        "docs/09-testing-and-release.md",
        "docs/10g-generated-scenario-eval.md",
    ):
        path = fake_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(
                [
                    CLOSURE_MARKER,
                    "final-2g-evidence",
                    "2g-final-evidence-<main-sha>",
                    "overall_status=passed",
                    "artifact already exists on this sha before merge",
                ]
            ),
            encoding="utf-8",
        )
    with pytest.raises(ValueError, match="forbidden pre-merge claim"):
        verify_documentation_closure(fake_root)


def test_release_gate_2g_pr_eval_job_contract():
    data = yaml.safe_load(RELEASE_GATE_PATH.read_text(encoding="utf-8"))
    job = data["jobs"]["2g-pr-eval"]
    assert job["if"] == "github.event_name == 'pull_request'"
    assert "needs" not in job or job.get("needs") is None

    build_step = next(step for step in job["steps"] if "Run 2G PR batch" in step.get("name", ""))
    build_run = build_step["run"]
    assert "run_2g_batch.py" in build_run
    assert '--mode pr' in build_run
    assert "gmail" not in build_run.lower()
    assert "openai" not in build_run.lower()


def test_release_gate_2g_main_eval_job_contract():
    data = yaml.safe_load(RELEASE_GATE_PATH.read_text(encoding="utf-8"))
    job = data["jobs"]["2g-main-eval"]
    assert job["if"] == "github.event_name == 'push' && github.ref == 'refs/heads/main'"
    assert job["needs"] == ["tests", "live-eval-postgres", "frontend", "docker"]

    build_step = next(step for step in job["steps"] if "Run 2G main batch" in step.get("name", ""))
    assert "run_2g_batch.py" in build_step["run"]
    assert '--mode main' in build_step["run"]


def test_release_gate_final_2g_evidence_job_contract():
    data = yaml.safe_load(RELEASE_GATE_PATH.read_text(encoding="utf-8"))
    job = data["jobs"]["final-2g-evidence"]
    assert job["if"] == "github.event_name == 'push' && github.ref == 'refs/heads/main'"
    assert job["needs"] == ["tests", "live-eval-postgres", "frontend", "docker", "2g-main-eval"]
    assert "always()" not in job.get("if", "")
    assert "workflow_dispatch" not in str(job)

    steps = job["steps"]
    build_step = next(
        step for step in steps if step.get("name") == "Build and finalize 2G evidence package"
    )
    build_run = build_step["run"]
    build_env = build_step.get("env") or {}
    assert build_env["OUTPUT_DIR"] == "${{ runner.temp }}/2g-final-evidence"
    assert "--finalize-closure" in build_run
    assert '--baseline-git-sha "${GITHUB_SHA}"' in build_run
    assert '--ci-run-id "${GITHUB_RUN_ID}"' in build_run
    assert "--required-check tests=${{ needs.tests.result }}" in build_run
    assert "--required-check 2g_main_eval=${{ needs['2g-main-eval'].result }}" in build_run
    assert "--required-check tests=success" not in build_run
    assert "run_2g_finalize.py" in build_run
    assert "gmail" not in build_run.lower()
    assert "openai" not in build_run.lower()

    upload_step = next(step for step in steps if "Upload 2G final evidence artifact" in step.get("name", ""))
    assert upload_step["uses"] == "actions/upload-artifact@v4"
    assert upload_step["with"]["name"] == "2g-final-evidence-${{ github.sha }}"
    upload_paths = upload_step["with"]["path"]
    assert upload_paths.count("2g_generation_manifest.json") == 1
    assert upload_paths.count("2g_batch_report.json") == 1
    assert upload_paths.count("2g_failures.json") == 1
    assert upload_paths.count("2g_coverage_report.json") == 1
    assert upload_paths.count("2g_final_report.json") == 1
    assert upload_step["with"]["if-no-files-found"] == "error"


def test_finalize_cli_produces_five_json_files(tmp_path: Path):
    output_dir = tmp_path / "finalize"
    env = os.environ.copy()
    env["PYTHONPATH"] = str(DOCS_ROOT)
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/run_2g_finalize.py",
            "--output-dir",
            str(output_dir),
            "--baseline-git-sha",
            _BASELINE_SHA,
        ],
        cwd=DOCS_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    for name in (
        "2g_generation_manifest.json",
        "2g_batch_report.json",
        "2g_failures.json",
        "2g_coverage_report.json",
        "2g_final_report.json",
    ):
        path = output_dir / name
        assert path.is_file(), f"missing {name}"
        json.loads(path.read_text(encoding="utf-8"))
    final_report = json.loads((output_dir / "2g_final_report.json").read_text(encoding="utf-8"))
    assert final_report["overall_status"] == "pending_closure"
    batch_report = json.loads((output_dir / "2g_batch_report.json").read_text(encoding="utf-8"))
    assert batch_report["scenario_count"] == 160
    assert batch_report["overall_status"] == "passed"


def test_no_network_socket_blocked_for_batch(monkeypatch):
    def _blocked(*_args, **_kwargs):
        raise OSError("network blocked in closure tests")

    monkeypatch.setattr(socket, "socket", _blocked)
    from app.evaluation.batch.runner import run_batch
    from app.evaluation.batch.sampler import build_pr_batch_records

    records = build_pr_batch_records().records[:5]
    batch = run_batch(records, mode="pr", verify_determinism=False)
    assert batch.no_network is True
    assert batch.openai_calls == 0
    assert batch.gmail_calls == 0
