"""Workflow YAML contract tests."""

from __future__ import annotations

from pathlib import Path

import yaml


def test_live_eval_workflow_contract():
    workflow_path = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "live-eval.yml"
    data = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    transport = data["jobs"]["live_gmail_transport"]
    assert transport["timeout-minutes"] == 45
    assert data["concurrency"]["group"] == "live-gmail-eval"
    assert data["concurrency"]["cancel-in-progress"] is False

    step_names = [step.get("name", "") for step in transport["steps"]]
    assert any("PostgreSQL" in name or "Bootstrap" in name for name in step_names)
    assert any("recipient Gmail OAuth" in name or "OAuth" in name for name in step_names)
    assert not any("live_gmail_eval" in (step.get("run") or "") for step in transport["steps"])

    run_step = next(step for step in transport["steps"] if "run-scenario" in (step.get("run") or ""))
    assert "--run-id-file" in run_step["run"]
