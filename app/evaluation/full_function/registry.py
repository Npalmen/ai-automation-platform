"""Capability registry and TBG manifest loading."""

from __future__ import annotations

import importlib
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable

import yaml

from app.evaluation.full_function.scenarios._common import ScenarioRunResult
from app.evaluation.full_function.actions import EvalContext

CAPABILITIES_PATH = Path(__file__).resolve().parent / "capabilities.yaml"
MANIFEST_PATH = Path(__file__).resolve().parent / "resources" / "tbg_manifest.yaml"
EXPECTED_SCENARIO_IDS = tuple(f"TBG{index:02d}" for index in range(1, 26))


@lru_cache(maxsize=1)
def load_capabilities() -> dict[str, Any]:
    with CAPABILITIES_PATH.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("capabilities.yaml must be a mapping")
    return data


def capability_entries() -> list[dict[str, Any]]:
    entries = load_capabilities().get("capabilities")
    if not isinstance(entries, list):
        raise ValueError("capabilities must be a list")
    return entries


def capability_index() -> dict[str, dict[str, Any]]:
    return {str(entry["id"]): entry for entry in capability_entries()}


def validate_capabilities() -> list[str]:
    failures: list[str] = []
    entries = capability_entries()
    ids = [entry.get("id") for entry in entries]
    if len(ids) != len(set(ids)):
        failures.append("capability IDs must be unique")
    required = {
        "id",
        "domain",
        "description",
        "entrypoint",
        "supported_modes",
        "expected_default_status",
    }
    for entry in entries:
        missing = required - set(entry.keys())
        if missing:
            failures.append(f"{entry.get('id')}: missing fields {sorted(missing)}")
    from app.workflows.action_authorization import ACTION_REGISTRY

    for entry in entries:
        entrypoint = str(entry.get("entrypoint") or "")
        if entrypoint in ACTION_REGISTRY:
            continue
    return failures


@lru_cache(maxsize=1)
def load_manifest() -> dict[str, Any]:
    with MANIFEST_PATH.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("TBG manifest must be a mapping")
    return data


def manifest_scenarios() -> list[dict[str, Any]]:
    scenarios = load_manifest().get("scenarios")
    if not isinstance(scenarios, list):
        raise ValueError("TBG manifest scenarios must be a list")
    return scenarios


def validate_manifest() -> list[str]:
    failures: list[str] = []
    scenarios = manifest_scenarios()
    ids = [entry.get("scenario_id") for entry in scenarios]
    if ids != list(EXPECTED_SCENARIO_IDS):
        failures.append(f"manifest scenario IDs must be {list(EXPECTED_SCENARIO_IDS)}, got {ids}")
    if len(set(ids)) != len(ids):
        failures.append("manifest scenario IDs must be unique")
    known_caps = set(capability_index().keys())
    for entry in scenarios:
        scenario_id = entry.get("scenario_id")
        module_name = entry.get("module")
        if not scenario_id or not module_name:
            failures.append(f"manifest entry missing scenario_id/module: {entry}")
            continue
        for cap_id in entry.get("capability_ids", []):
            if cap_id not in known_caps:
                failures.append(f"{scenario_id}: unknown capability {cap_id}")
        module_path = f"app.evaluation.full_function.scenarios.{module_name}"
        try:
            importlib.import_module(module_path)
        except ModuleNotFoundError:
            failures.append(f"{scenario_id}: missing scenario module {module_path}")
    return failures


def load_tbg_runners() -> dict[str, Callable[[EvalContext], ScenarioRunResult]]:
    runners: dict[str, Callable[[EvalContext], ScenarioRunResult]] = {}
    for entry in manifest_scenarios():
        scenario_id = str(entry["scenario_id"])
        module_name = str(entry["module"])
        module = importlib.import_module(
            f"app.evaluation.full_function.scenarios.{module_name}"
        )
        runner = getattr(module, "run", None)
        if runner is None:
            raise ValueError(f"{scenario_id}: scenario module missing run()")
        runners[scenario_id] = runner
    return runners
