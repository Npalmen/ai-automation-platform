"""Workflow contract tests for continuous regression workflows."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WORKFLOW_DIR = Path(__file__).resolve().parents[3] / ".github" / "workflows"
REGRESSION_WORKFLOWS = (
    "regression-pr.yml",
    "regression-main.yml",
    "regression-nightly.yml",
    "continuous-regression-h-qualification.yml",
)


def _load_workflow(name: str) -> dict:
    return yaml.safe_load((WORKFLOW_DIR / name).read_text(encoding="utf-8"))


def test_regression_workflows_exist():
    for name in REGRESSION_WORKFLOWS:
        assert (WORKFLOW_DIR / name).is_file(), name


@pytest.mark.parametrize("workflow_name", REGRESSION_WORKFLOWS)
def test_regression_workflows_are_manual_or_pr_main_only(workflow_name):
    data = _load_workflow(workflow_name)
    trigger = data.get("on") or data[True]
    if workflow_name == "continuous-regression-h-qualification.yml":
        assert trigger == {"workflow_dispatch": None} or "workflow_dispatch" in trigger
        assert "schedule" not in trigger
    elif workflow_name == "regression-nightly.yml":
        assert "schedule" in trigger
        assert "workflow_dispatch" in trigger
    else:
        assert "schedule" not in trigger


def test_regression_pr_has_no_live_secrets():
    data = _load_workflow("regression-pr.yml")
    content = (WORKFLOW_DIR / "regression-pr.yml").read_text(encoding="utf-8")
    assert "LIVE_EVAL_SENDER_GMAIL" not in content
    assert "environment: live-gmail-eval" not in content
    assert data["jobs"]


def test_regression_nightly_has_zero_write_budget_env():
    content = (WORKFLOW_DIR / "regression-nightly.yml").read_text(encoding="utf-8")
    assert "CONTINUOUS_REGRESSION_EXTERNAL_WRITE_BUDGET" in content
    assert "live-eval.yml" not in content
    assert "LIVE_EVAL_SENDER_GMAIL" not in content
