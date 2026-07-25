"""Read-only canonical parent scenario loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.evaluation.dataset_manifest import (
    DEFAULT_MANIFEST,
    compute_scenario_file_hash,
    load_manifest_scenarios,
)
from app.evaluation.errors import ScenarioValidationError
from app.evaluation.schema.scenario import ScenarioContract


@dataclass(frozen=True)
class CanonicalParent:
    scenario_id: str
    path: Path
    scenario: ScenarioContract
    content_hash: str


def load_canonical_parents(
    manifest_path: Path | None = None,
) -> tuple[Path, list[CanonicalParent]]:
    path = manifest_path or DEFAULT_MANIFEST
    _, root, items = load_manifest_scenarios(path)
    parents: list[CanonicalParent] = []
    for scenario_path, scenario in items:
        if scenario.source_mode != "fixture":
            raise ScenarioValidationError(
                f"Canonical parent must use source_mode=fixture: {scenario.scenario_id}"
            )
        parents.append(
            CanonicalParent(
                scenario_id=scenario.scenario_id,
                path=scenario_path,
                scenario=scenario,
                content_hash=compute_scenario_file_hash(scenario_path),
            )
        )
    if not parents:
        raise ScenarioValidationError("No canonical parents found in manifest")
    return path, parents


def get_parent_by_id(parents: list[CanonicalParent], parent_scenario_id: str) -> CanonicalParent:
    for parent in parents:
        if parent.scenario_id == parent_scenario_id:
            return parent
    raise ScenarioValidationError(f"Unknown parent_scenario_id: {parent_scenario_id}")
