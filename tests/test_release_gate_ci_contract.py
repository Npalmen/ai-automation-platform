"""CI contract tests for release-gate invocation."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

RELEASE_GATE_WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github" / "workflows" / "release-gate.yml"
)
RELEASE_GATE_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/ai_platform"


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
