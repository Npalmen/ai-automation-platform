"""GitHub summary provenance contract tests."""

from __future__ import annotations

from pathlib import Path

from app.evaluation.live.reporting import (
    FailureSummary,
    _resolve_workflow_sha_for_summary,
    write_github_step_summary,
)


def test_fixture_workflow_sha_not_used_for_live_summary(monkeypatch):
    monkeypatch.setenv("BUILD_GIT_SHA", "abc123")
    assert _resolve_workflow_sha_for_summary() is None


def test_real_workflow_sha_used_for_live_summary(monkeypatch):
    sha = "aa002d7b8183804f579da699cdde494b21137f96"
    monkeypatch.setenv("BUILD_GIT_SHA", sha)
    assert _resolve_workflow_sha_for_summary() == sha


def test_write_github_step_summary_omits_fixture_workflow_sha(tmp_path, monkeypatch):
    summary_path = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_path))
    monkeypatch.setenv("BUILD_GIT_SHA", "abc123")
    summary = FailureSummary(
        evaluation_run_id="run-1",
        scenario_id="S01_lead_laddbox_quality",
        attempt_id=1,
        failure_category="safety_rejected",
        failed_stage="triggering_intake",
        primary_exit_code=2,
        cleanup_exit_code=None,
        artifact_status="present",
        final_exit_code=2,
        send_state="confirmed",
        send_attempted=True,
        send_confirmed=True,
        reconciliation_result="not_run",
        recipient_delivery_observed=True,
        root_job_bound=False,
        cleanup_state="not_run",
        gmail_mutations=0,
    )
    write_github_step_summary(summary)
    text = summary_path.read_text(encoding="utf-8")
    assert "workflow_sha: `abc123`" not in text
    assert "config_hash" not in text


def test_workflow_contract_blocks_fixture_marker_in_reporting_source():
    reporting_source = Path("app/evaluation/live/reporting.py").read_text(encoding="utf-8")
    assert "abc123" not in reporting_source or "_FIXTURE_WORKFLOW_SHA_MARKERS" in reporting_source
