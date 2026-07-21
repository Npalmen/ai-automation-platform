"""Regression tests for evaluation harness telemetry under ENV=test."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from app.evaluation.db_isolation import eval_db_session
from app.evaluation.loader import load_scenario
from app.evaluation.reporting import new_run_id
from app.evaluation.runner import EvalHarnessRunner
from app.evaluation.telemetry import get_telemetry

SCENARIOS_ROOT = Path(__file__).resolve().parent / "scenarios"

TELEMETRY_CASES = (
    ("S15_full_auto_execution_trace", 1),
    ("S18_approval_resume_operation_id", 1),
)


@pytest.fixture()
def harness_runner():
    return EvalHarnessRunner(run_id=new_run_id())


@pytest.mark.parametrize(("scenario_id", "min_fake_adapter_calls"), TELEMETRY_CASES)
def test_eval_telemetry_reaches_fake_adapter(
    scenario_id: str,
    min_fake_adapter_calls: int,
    harness_runner: EvalHarnessRunner,
):
    os.environ["ENV"] = "test"
    path = SCENARIOS_ROOT / f"{scenario_id}.yaml"
    if not path.exists():
        pytest.skip(f"Scenario file missing: {path}")

    scenario = load_scenario(path)
    with patch("app.workflows.action_executor.InternalStubAdapter") as stub_adapter:
        with eval_db_session() as db:
            result = harness_runner.run_scenario(db, scenario)
            telemetry = get_telemetry().as_dict()

    assert result.exit_code == 0, result.safety_violations
    assert telemetry["fake_adapter_calls"] >= min_fake_adapter_calls
    if scenario_id == "S18_approval_resume_operation_id":
        assert telemetry["fake_adapter_calls"] == 1
    assert telemetry["real_external_calls"] == 0
    stub_adapter.assert_not_called()
