"""Load and validate scenario YAML files."""

from __future__ import annotations

from pathlib import Path

import yaml

from app.evaluation.errors import ScenarioValidationError
from app.evaluation.schema.scenario import ScenarioContract


def load_scenario(path: Path) -> ScenarioContract:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ScenarioValidationError(f"Failed to read {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ScenarioValidationError(f"Scenario root must be a mapping: {path}")
    try:
        return ScenarioContract.model_validate(raw)
    except Exception as exc:
        raise ScenarioValidationError(f"Invalid scenario {path}: {exc}") from exc


def discover_scenarios(
    root: Path,
    *,
    scenario_id: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    glob_pattern: str = "**/*.yaml",
) -> list[tuple[Path, ScenarioContract]]:
    paths = sorted(root.glob(glob_pattern))
    out: list[tuple[Path, ScenarioContract]] = []
    for path in paths:
        scenario = load_scenario(path)
        if scenario_id and scenario.scenario_id != scenario_id:
            continue
        if category and scenario.category != category and category not in scenario.tags:
            continue
        if tag and tag not in scenario.tags:
            continue
        out.append((path, scenario))
    return out
