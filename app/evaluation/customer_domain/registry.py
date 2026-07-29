"""TBF campaign manifest registry for customer-card stateful evaluation."""

from __future__ import annotations

import importlib
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import yaml

from app.evaluation.customer_domain.scenarios._common import ScenarioRunResult
from app.evaluation.customer_domain.actions import EvalContext

MANIFEST_PATH = Path(__file__).resolve().parent / "resources" / "tbf_manifest.yaml"
EXPECTED_SCENARIO_IDS = tuple(f"TBF{index:02d}" for index in range(1, 11))


@lru_cache(maxsize=1)
def load_manifest() -> dict[str, Any]:
    with MANIFEST_PATH.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("TBF manifest must be a mapping")
    return data


def manifest_scenarios() -> list[dict[str, Any]]:
    scenarios = load_manifest().get("scenarios")
    if not isinstance(scenarios, list):
        raise ValueError("TBF manifest scenarios must be a list")
    return scenarios


def validate_manifest() -> list[str]:
    failures: list[str] = []
    scenarios = manifest_scenarios()
    ids = [entry.get("scenario_id") for entry in scenarios]
    if ids != list(EXPECTED_SCENARIO_IDS):
        failures.append(
            f"manifest scenario IDs must be {list(EXPECTED_SCENARIO_IDS)}, got {ids}"
        )
    if len(set(ids)) != len(ids):
        failures.append("manifest scenario IDs must be unique")
    for entry in scenarios:
        scenario_id = entry.get("scenario_id")
        module_name = entry.get("module")
        if not scenario_id or not module_name:
            failures.append(f"manifest entry missing scenario_id/module: {entry}")
            continue
        module_path = f"app.evaluation.customer_domain.scenarios.{module_name}"
        try:
            importlib.import_module(module_path)
        except ModuleNotFoundError:
            failures.append(f"{scenario_id}: missing scenario module {module_path}")
    return failures


def load_tbf_runners() -> dict[str, Callable[[EvalContext], ScenarioRunResult]]:
    runners: dict[str, Callable[[EvalContext], ScenarioRunResult]] = {}
    for entry in manifest_scenarios():
        scenario_id = str(entry["scenario_id"])
        module_name = str(entry["module"])
        module = importlib.import_module(
            f"app.evaluation.customer_domain.scenarios.{module_name}"
        )
        runner = getattr(module, "run", None)
        if runner is None:
            raise ValueError(f"{scenario_id}: scenario module missing run()")
        runners[scenario_id] = runner
    return runners
