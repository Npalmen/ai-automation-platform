"""Full-function matrix validation."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.evaluation.full_function.registry import capability_index

MATRIX_PATH = Path(__file__).resolve().parent / "resources" / "full_function_matrix.yaml"
PASS_STATUSES = {"PASS", "PASS_LIVE", "SANDBOX_ONLY", "BLOCKED_BY_POLICY", "DISABLED_BY_FLAG", "NOT_IMPLEMENTED", "NOT_APPLICABLE", "UNQUALIFIED"}


@lru_cache(maxsize=1)
def load_matrix() -> dict[str, Any]:
    with MATRIX_PATH.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("full_function_matrix.yaml must be a mapping")
    return data


def matrix_cells() -> list[dict[str, Any]]:
    cells = load_matrix().get("matrix")
    if not isinstance(cells, list):
        raise ValueError("matrix must be a list")
    return cells


def validate_matrix() -> list[str]:
    failures: list[str] = []
    caps = capability_index()
    for cell in matrix_cells():
        cap_id = cell.get("capability_id")
        status = cell.get("status")
        evidence = cell.get("evidence")
        if cap_id not in caps:
            failures.append(f"matrix references unknown capability {cap_id}")
        if status not in PASS_STATUSES and status != "FAIL":
            failures.append(f"{cap_id}: invalid status {status}")
        if status in {"PASS", "PASS_LIVE", "SANDBOX_ONLY"} and not evidence:
            failures.append(f"{cap_id}: PASS statuses require evidence")
        if status == "PASS_LIVE" and not str(evidence).startswith("AUTOMATIC_GMAIL"):
            failures.append(f"{cap_id}: PASS_LIVE requires live qualification evidence")
    return failures


def matrix_status_summary() -> dict[str, int]:
    summary: dict[str, int] = {}
    for cell in matrix_cells():
        status = str(cell.get("status"))
        summary[status] = summary.get(status, 0) + 1
    return summary
