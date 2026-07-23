"""CI contract tests for release-gate invocation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

RELEASE_GATE_WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release-gate.yml"
)
LIVE_EVAL_WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "live-eval.yml"
)
RELEASE_GATE_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/ai_platform"
LIVE_EVAL_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/ai_platform"


def test_release_gate_module_help_exits_zero():
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "-m", "scripts.run_release_gate_r1", "--help"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def _step_by_name(steps: list[dict], needle: str) -> dict:
    return next(step for step in steps if needle in (step.get("name") or ""))


def test_release_gate_live_eval_postgres_registry_refresh_contract():
    data = yaml.safe_load(RELEASE_GATE_WORKFLOW.read_text(encoding="utf-8"))
    job = data["jobs"]["live-eval-postgres"]
    assert job["name"] == "Live eval PostgreSQL (integration_db)"
    assert "postgres" in job.get("services", {})

    steps = job["steps"]
    step_names = [step.get("name", "") for step in steps]
    assert any("registry refresh" in name.lower() for name in step_names)

    refresh = _step_by_name(steps, "registry refresh")
    assert refresh.get("continue-on-error") is not True
    assert refresh.get("if") is None

    refresh_env = refresh.get("env") or {}
    assert refresh_env == {
        "ENV": "test",
        "DATABASE_URL": RELEASE_GATE_DATABASE_URL,
    }

    refresh_run = refresh.get("run") or ""
    assert "tests/evaluation/live/test_registry_refresh_pg.py" in refresh_run
    assert "-m integration_db" in refresh_run
    assert "live_eval_registry_refresh_pg.junit.xml" in refresh_run
    assert "verify_pytest_junit.py live_eval_registry_refresh_pg.junit.xml --expected 1" in refresh_run
    assert "|| true" not in refresh_run
    assert "pytest.skip" not in refresh_run
    assert '!= "1"' in refresh_run or "!= \"1\"" in refresh_run

    bootstrap_idx = next(
        i for i, step in enumerate(steps) if "Bootstrap PostgreSQL schema" in (step.get("name") or "")
    )
    refresh_idx = next(
        i for i, step in enumerate(steps) if "registry refresh" in (step.get("name") or "").lower()
    )
    assert bootstrap_idx < refresh_idx


def test_live_eval_foundation_integration_db_count_contract():
    data = yaml.safe_load(LIVE_EVAL_WORKFLOW.read_text(encoding="utf-8"))
    foundation = data["jobs"]["foundation"]
    transport = data["jobs"]["live_gmail_transport"]

    assert foundation.get("environment") is None
    assert transport["environment"] == "live-gmail-eval"
    assert transport["needs"] == ["foundation", "operator-gate"]

    steps = foundation["steps"]
    collect = _step_by_name(steps, "Verify integration_db test selection")
    collect_run = collect.get("run") or ""
    assert '!= "11"' in collect_run or "!= \"11\"" in collect_run
    assert "test_registry_refresh_pg.py" in collect_run
    assert "test_cleanup_persistence_pg.py" in collect_run
    assert "test_root_job_atomic_pg.py" in collect_run
    assert "test_telemetry_idempotency_pg.py" in collect_run
    assert (collect.get("env") or {}) == {
        "ENV": "test",
        "DATABASE_URL": LIVE_EVAL_DATABASE_URL,
    }

    junit = _step_by_name(steps, "Verify integration_db JUnit gate")
    assert "verify_pytest_junit.py foundation_integration_db.junit.xml --expected 11" in (
        junit.get("run") or ""
    )
    assert junit.get("continue-on-error") is not True

    transport_steps = transport["steps"]
    run_scenario = _step_by_name(transport_steps, "Live Gmail S01 scenario")
    cleanup = next(step for step in transport_steps if step.get("id") == "cleanup")
    readiness = _step_by_name(transport_steps, "Readiness-only report")
    assert run_scenario.get("if") == "inputs.confirm_live_gmail == 'RUN_S01'"
    assert cleanup.get("if") == "always() && inputs.confirm_live_gmail == 'RUN_S01'"
    assert readiness.get("if") == "inputs.confirm_live_gmail == 'READINESS_ONLY'"
