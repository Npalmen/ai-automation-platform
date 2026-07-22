"""Workflow YAML contract tests."""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW_PATH = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "live-eval.yml"


def _load_workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _workflow_trigger(data: dict) -> dict:
    return data.get("on") or data[True]


def test_live_eval_workflow_contract():
    data = _load_workflow()
    transport = data["jobs"]["live_gmail_transport"]
    assert transport["timeout-minutes"] == 45
    assert transport["environment"] == "live-gmail-eval"
    assert transport["needs"] == ["foundation", "operator-gate"]
    assert data["concurrency"]["group"] == "live-gmail-eval"
    assert data["concurrency"]["cancel-in-progress"] is False

    permissions = data.get("permissions") or {}
    assert permissions == {"contents": "read"}

    trigger = _workflow_trigger(data)
    dispatch = trigger["workflow_dispatch"]
    assert "push" not in trigger
    assert "pull_request" not in trigger
    assert "schedule" not in trigger

    confirm_input = dispatch["inputs"]["confirm_live_gmail"]
    assert confirm_input["required"] is True
    assert confirm_input["type"] == "choice"
    assert confirm_input["default"] == "DO_NOT_RUN"
    assert confirm_input["options"] == ["DO_NOT_RUN", "RUN_S01"]

    operator_gate = data["jobs"]["operator-gate"]
    assert "environment" not in operator_gate
    gate_run = operator_gate["steps"][0]["run"]
    assert 'test "${GITHUB_REF}" = "refs/heads/main"' in gate_run
    assert 'test "${{ inputs.confirm_live_gmail }}" = "RUN_S01"' in gate_run

    step_names = [step.get("name", "") for step in transport["steps"]]
    assert any("PostgreSQL" in name or "Bootstrap" in name for name in step_names)
    assert any("recipient Gmail OAuth" in name or "OAuth" in name for name in step_names)
    assert not any("live_gmail_eval" in (step.get("run") or "") for step in transport["steps"])

    run_step = next(step for step in transport["steps"] if "run-scenario" in (step.get("run") or ""))
    assert "--run-id-file" in run_step["run"]
    assert "S01_lead_laddbox_quality" in run_step["run"]
    assert "--scenario-id" in run_step["run"]

    cleanup_step = next(step for step in transport["steps"] if step.get("id") == "cleanup")
    assert cleanup_step.get("if") == "always()"
    assert "|| true" not in (cleanup_step.get("run") or "")

    gate_step = next(step for step in transport["steps"] if step.get("name") == "Cleanup gate")
    assert gate_step.get("if") == "always()"
    assert "steps.cleanup.outcome" in (gate_step.get("run") or "")

    artifact_step = next(step for step in transport["steps"] if "Upload redacted artifacts" in step.get("name", ""))
    assert artifact_step.get("if") == "always() && env.RUN_ID != ''"

    freeform_inputs = set(dispatch["inputs"].keys()) - {"confirm_live_gmail"}
    assert not freeform_inputs, f"unexpected workflow inputs: {freeform_inputs}"
