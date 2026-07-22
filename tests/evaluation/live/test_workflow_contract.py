"""Workflow YAML contract tests."""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW_PATH = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "live-eval.yml"


def _load_workflow() -> dict:
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _workflow_trigger(data: dict) -> dict:
    return data.get("on") or data[True]


def _step_by_name(steps: list[dict], needle: str) -> dict:
    return next(step for step in steps if needle in (step.get("name") or ""))


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
    assert confirm_input["options"] == ["DO_NOT_RUN", "READINESS_ONLY", "RUN_S01"]

    operator_gate = data["jobs"]["operator-gate"]
    assert "environment" not in operator_gate
    gate_run = operator_gate["steps"][0]["run"]
    assert 'test "${GITHUB_REF}" = "refs/heads/main"' in gate_run
    assert "READINESS_ONLY|RUN_S01" in gate_run
    assert 'test "${{ inputs.confirm_live_gmail }}" = "RUN_S01"' not in gate_run

    steps = transport["steps"]
    step_names = [step.get("name", "") for step in steps]
    assert any("PostgreSQL" in name or "Bootstrap" in name for name in step_names)
    assert any("recipient Gmail OAuth" in name or "OAuth" in name for name in step_names)
    assert not any("live_gmail_eval" in (step.get("run") or "") for step in steps)

    recipient_step = _step_by_name(steps, "Recipient read-only")
    assert "gmail-readiness" in (recipient_step.get("run") or "")

    sender_step = _step_by_name(steps, "Sender read-only")
    sender_run = sender_step.get("run") or ""
    assert "--sender-readiness" in sender_run
    assert "--confirm-read-only" in sender_run

    readiness_step = _step_by_name(steps, "Readiness-only report")
    assert readiness_step.get("if") == "inputs.confirm_live_gmail == 'READINESS_ONLY'"
    readiness_run = readiness_step.get("run") or ""
    assert "readiness-only" in readiness_run
    assert "run-scenario" not in readiness_run

    readiness_artifact = _step_by_name(steps, "Upload readiness artifact")
    assert readiness_artifact.get("if") == "always() && inputs.confirm_live_gmail == 'READINESS_ONLY'"

    run_step = _step_by_name(steps, "Live Gmail S01 scenario")
    assert run_step.get("if") == "inputs.confirm_live_gmail == 'RUN_S01'"
    run_run = run_step.get("run") or ""
    assert "--run-id-file" in run_run
    assert "S01_lead_laddbox_quality" in run_run
    assert "--scenario-id" in run_run

    cleanup_step = next(step for step in steps if step.get("id") == "cleanup")
    assert cleanup_step.get("if") == "always() && inputs.confirm_live_gmail == 'RUN_S01'"
    assert "|| true" not in (cleanup_step.get("run") or "")

    gate_step = _step_by_name(steps, "Cleanup gate")
    assert gate_step.get("if") == "always() && inputs.confirm_live_gmail == 'RUN_S01'"
    assert "steps.cleanup.outcome" in (gate_step.get("run") or "")

    artifact_step = _step_by_name(steps, "Upload redacted artifacts")
    assert artifact_step.get("if") == "always() && inputs.confirm_live_gmail == 'RUN_S01' && env.RUN_ID != ''"

    freeform_inputs = set(dispatch["inputs"].keys()) - {"confirm_live_gmail"}
    assert not freeform_inputs, f"unexpected workflow inputs: {freeform_inputs}"
