"""GITHUB_STEP_SUMMARY isolation for foundation and live-eval commands."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.evaluation.live.reporting import (
    FailureSummary,
    _resolve_workflow_sha_for_summary,
    write_github_step_summary,
)


def test_conftest_isolates_summary_from_fixture_config_hash(tmp_path, monkeypatch):
    summary_path = tmp_path / "step-summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
    monkeypatch.setenv("BUILD_GIT_SHA", "abc123")

    summary = FailureSummary(
        evaluation_run_id="run-1",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        failure_category="job_timeout",
        failed_stage="job_detected",
        primary_exit_code=5,
        cleanup_exit_code=None,
        artifact_status="present",
        final_exit_code=5,
        send_state="confirmed",
        send_attempted=True,
        send_confirmed=True,
        reconciliation_result="not_run",
        recipient_delivery_observed=True,
        root_job_bound=True,
        cleanup_state="not_run",
        gmail_mutations=0,
    )
    write_github_step_summary(summary)
    text = summary_path.read_text(encoding="utf-8")
    assert "workflow_sha: `abc123`" not in text
    assert "config_hash" not in text


def test_readiness_summary_uses_real_sha_not_fixture(tmp_path, monkeypatch):
    sha = "ec29e40e5d605cb72c2941347b880fa68b85b604"
    summary_path = tmp_path / "readiness-summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
    monkeypatch.setenv("BUILD_GIT_SHA", sha)
    assert _resolve_workflow_sha_for_summary() == sha

    summary_path.write_text(
        "\n".join(
            [
                "## Live Gmail readiness-only",
                "- result: **passed**",
                f"- workflow_sha: `{sha}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    text = summary_path.read_text(encoding="utf-8")
    assert sha in text
    assert "abc123" not in text


def test_offline_dry_run_summary_contract(tmp_path, monkeypatch):
    summary_path = tmp_path / "dry-run-summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_live_eval.py",
            "dry-run",
            "--evaluation-run-id",
            "run-offline-summary",
            "--scenario-id",
            "S01_lead_laddbox_quality",
            "--attempt-id",
            "1",
        ],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    text = summary_path.read_text(encoding="utf-8")
    assert "offline/hermetic" in text
    assert "not applicable" in text
    assert "abc123" not in text


def test_all_summary_writers_use_env_path_only():
    reporting_source = Path("app/evaluation/live/reporting.py").read_text(encoding="utf-8")
    cli_source = Path("scripts/run_live_eval.py").read_text(encoding="utf-8")
    assert 'os.environ.get("GITHUB_STEP_SUMMARY")' in reporting_source
    assert 'os.environ.get("GITHUB_STEP_SUMMARY")' in cli_source
    assert "abc123" not in reporting_source or "_FIXTURE_WORKFLOW_SHA_MARKERS" in reporting_source
