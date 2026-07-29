"""Regression suite registry loading and validation."""

from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.evaluation.regression.constants import (
    AUTOMATED_TIERS,
    FORBIDDEN_NETWORK_TIERS,
    REGISTRY_VERSION,
    ZERO_WRITE_BUDGET_TIERS,
)

REGISTRY_PATH = Path(__file__).resolve().parent / "regression_registry.yaml"
REQUIRED_SUITE_FIELDS = {
    "id",
    "chapter",
    "description",
    "tier",
    "command",
    "required_paths",
    "database",
    "network",
    "external_write_budget",
    "artifact_schema",
    "timeout_class",
    "repeat_run",
    "cleanup_required",
    "owners",
}


@lru_cache(maxsize=1)
def load_regression_registry() -> dict[str, Any]:
    with REGISTRY_PATH.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("regression_registry.yaml must be a mapping")
    return data


def suite_entries() -> list[dict[str, Any]]:
    suites = load_regression_registry().get("suites")
    if not isinstance(suites, list):
        raise ValueError("regression registry suites must be a list")
    return suites


def suite_index() -> dict[str, dict[str, Any]]:
    return {str(entry["id"]): entry for entry in suite_entries()}


def validate_regression_registry() -> list[str]:
    failures: list[str] = []
    version = load_regression_registry().get("version")
    if version != REGISTRY_VERSION:
        failures.append(f"registry version must be {REGISTRY_VERSION}, got {version}")
    entries = suite_entries()
    ids = [entry.get("id") for entry in entries]
    if len(ids) != len(set(ids)):
        failures.append("regression suite IDs must be unique")
    repo_root = Path(__file__).resolve().parents[3]
    for entry in entries:
        missing = REQUIRED_SUITE_FIELDS - set(entry.keys())
        if missing:
            failures.append(f"{entry.get('id')}: missing fields {sorted(missing)}")
        suite_id = str(entry.get("id") or "")
        tiers = entry.get("tier") or []
        if not isinstance(tiers, list) or not tiers:
            failures.append(f"{suite_id}: tier must be a non-empty list")
            continue
        unknown_tiers = [tier for tier in tiers if tier not in AUTOMATED_TIERS]
        if unknown_tiers:
            failures.append(f"{suite_id}: unknown tier(s) {unknown_tiers}")
        if entry.get("network") != "forbidden":
            failures.append(f"{suite_id}: network must be forbidden for automated tiers")
        if int(entry.get("external_write_budget", -1)) != 0:
            failures.append(f"{suite_id}: external_write_budget must be 0")
        command = entry.get("command")
        if not isinstance(command, list) or not command:
            failures.append(f"{suite_id}: command must be a non-empty list")
        for rel_path in entry.get("required_paths", []):
            glob_path = str(rel_path).replace("**", "*")
            if "*" in glob_path:
                parent = repo_root / str(rel_path).split("**", 1)[0]
                if not parent.exists():
                    failures.append(f"{suite_id}: required_paths parent missing: {rel_path}")
            else:
                if not (repo_root / str(rel_path)).exists():
                    failures.append(f"{suite_id}: required_paths missing: {rel_path}")
    return failures


def suites_for_tier(tier: str) -> list[dict[str, Any]]:
    return [entry for entry in suite_entries() if tier in (entry.get("tier") or [])]


def run_suite_command(command: list[str], *, cwd: Path | None = None) -> tuple[int, str]:
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode, output.strip()
