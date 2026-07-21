"""S15/S18 telemetry contract regression tests for Kapitel 2E.1."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.evaluation.db_isolation import eval_db_session
from app.evaluation.loader import load_scenario
from app.evaluation.runner import EvalHarnessRunner
from scripts.run_eval_harness import main as harness_main

from tests.evaluation.test_harness_self import SMOKE_IDS

SCENARIOS_ROOT = Path("tests/evaluation/scenarios")
S18_ID = "S18_approval_resume_operation_id"
S15_ID = "S15_full_auto_execution_trace"


@pytest.fixture()
def ci_test_env(monkeypatch):
    monkeypatch.setenv("ENV", "test")


def _run_scenario(scenario_id: str, run_id: str) -> object:
    scenario = load_scenario(SCENARIOS_ROOT / f"{scenario_id}.yaml")
    with eval_db_session() as db:
        return EvalHarnessRunner(run_id=run_id).run_scenario(db, scenario)


def _assert_adapter_telemetry_contract(result) -> None:
    assert result.status == "pass", result.safety_violations
    assert result.runtime.fake_adapter_calls >= 1
    assert result.runtime.real_external_calls == 0
    assert result.runtime.execution_function_calls >= 1


def _assert_s18_adapter_telemetry(result) -> None:
    _assert_adapter_telemetry_contract(result)
    assert result.runtime.fake_adapter_calls == 1


def test_s18_fake_adapter_calls_under_ci_env(ci_test_env):
    result = _run_scenario(S18_ID, "s18-ci-env")
    _assert_s18_adapter_telemetry(result)


def test_s18_isolated_twice_no_state_leak(ci_test_env):
    first = _run_scenario(S18_ID, "s18-run-a")
    second = _run_scenario(S18_ID, "s18-run-b")
    _assert_s18_adapter_telemetry(first)
    _assert_s18_adapter_telemetry(second)


def test_s18_after_other_smoke_scenarios(ci_test_env):
    for scenario_id in SMOKE_IDS:
        if scenario_id == S18_ID:
            continue
        prior = _run_scenario(scenario_id, f"pre-{scenario_id}")
        assert prior.exit_code == 0, f"{scenario_id} failed before S18: {prior.safety_violations}"
    result = _run_scenario(S18_ID, "s18-after-smoke")
    _assert_s18_adapter_telemetry(result)


def test_s15_and_s18_share_telemetry_contract(ci_test_env):
    s15 = _run_scenario(S15_ID, "s15-contract")
    s18 = _run_scenario(S18_ID, "s18-contract")
    _assert_adapter_telemetry_contract(s15)
    _assert_s18_adapter_telemetry(s18)


def test_smoke_harness_passes_under_ci_env(ci_test_env):
    assert harness_main(["--smoke", "--fail-on-regression", "-q"]) == 0
