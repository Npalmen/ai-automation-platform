"""Dataset manifest loading and hashing for Kapitel 2E gold dataset."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from app.evaluation.errors import ScenarioValidationError
from app.evaluation.loader import load_scenario
from app.evaluation.schema.scenario import ScenarioContract

DEFAULT_MANIFEST = (
    Path(__file__).resolve().parents[2] / "tests" / "evaluation" / "datasets" / "k2e-v1.yaml"
)


class DatasetManifest(BaseModel):
    dataset_id: str
    dataset_version: str
    schema_version: str
    baseline_id: str
    scenarios_dir: str = "scenarios"
    scenarios: list[str] = Field(default_factory=list)
    smoke: list[str] = Field(default_factory=list)


def load_manifest(path: Path | None = None) -> DatasetManifest:
    manifest_path = path or DEFAULT_MANIFEST
    try:
        raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ScenarioValidationError(f"Failed to read manifest {manifest_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ScenarioValidationError(f"Manifest root must be a mapping: {manifest_path}")
    try:
        return DatasetManifest.model_validate(raw)
    except Exception as exc:
        raise ScenarioValidationError(f"Invalid manifest {manifest_path}: {exc}") from exc


def resolve_scenarios_root(manifest: DatasetManifest, manifest_path: Path) -> Path:
    return (manifest_path.parent / manifest.scenarios_dir).resolve()


def load_manifest_scenarios(
    manifest_path: Path | None = None,
    *,
    scenario_id: str | None = None,
    smoke_only: bool = False,
) -> tuple[DatasetManifest, Path, list[tuple[Path, ScenarioContract]]]:
    path = manifest_path or DEFAULT_MANIFEST
    manifest = load_manifest(path)
    root = resolve_scenarios_root(manifest, path)
    allowed_ids = set(manifest.smoke if smoke_only else manifest.scenarios)
    items: list[tuple[Path, ScenarioContract]] = []
    for sid in manifest.scenarios if not smoke_only else manifest.smoke:
        if scenario_id and sid != scenario_id:
            continue
        if smoke_only and sid not in allowed_ids:
            continue
        scenario_path = root / f"{sid}.yaml"
        if not scenario_path.exists():
            raise ScenarioValidationError(f"Manifest scenario missing file: {scenario_path}")
        scenario = load_scenario(scenario_path)
        if scenario.scenario_id != sid:
            raise ScenarioValidationError(
                f"scenario_id mismatch in {scenario_path}: {scenario.scenario_id} != {sid}"
            )
        items.append((scenario_path, scenario))
    if scenario_id and not items:
        raise ScenarioValidationError(f"scenario_id '{scenario_id}' not in manifest")
    return manifest, root, items


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compute_manifest_hash(manifest_path: Path | None = None) -> dict[str, Any]:
    path = manifest_path or DEFAULT_MANIFEST
    manifest = load_manifest(path)
    root = resolve_scenarios_root(manifest, path)
    scenario_hashes = {}
    for sid in manifest.scenarios:
        sp = root / f"{sid}.yaml"
        scenario_hashes[sid] = hash_file(sp) if sp.exists() else "missing"
    canonical = {
        "dataset_id": manifest.dataset_id,
        "dataset_version": manifest.dataset_version,
        "schema_version": manifest.schema_version,
        "baseline_id": manifest.baseline_id,
        "scenarios": manifest.scenarios,
        "smoke": manifest.smoke,
        "scenario_hashes": scenario_hashes,
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "manifest_path": str(path),
        "manifest_hash": digest,
        "scenario_hashes": scenario_hashes,
        "canonical": canonical,
    }
