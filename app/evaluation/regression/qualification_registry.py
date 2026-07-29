"""Qualification registry loading, validation, and drift detection."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.evaluation.full_function.registry import capability_index
from app.evaluation.regression.constants import QUALIFICATION_REGISTRY_VERSION

QUALIFICATION_PATH = Path(__file__).resolve().parent / "qualification_registry.yaml"
DRIFT_VALID = "VALID"
DRIFT_STALE = "STALE"
DRIFT_INCOMPATIBLE = "INCOMPATIBLE"
DRIFT_MISSING_EVIDENCE = "MISSING_EVIDENCE"
DRIFT_SCOPE_EXPANSION_BLOCKED = "SCOPE_EXPANSION_BLOCKED"

REQUIRED_QUALIFICATION_FIELDS = {
    "id",
    "chapter",
    "scope",
    "source_workflow_run",
    "source_sha",
    "contract_version",
    "evidence_schema",
    "allowed_reuse",
    "incompatible_changes",
    "expiry_policy",
    "default_production_activation",
    "live_external_write_type",
    "status",
}


@lru_cache(maxsize=1)
def load_qualification_registry() -> dict[str, Any]:
    with QUALIFICATION_PATH.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("qualification_registry.yaml must be a mapping")
    return data


def qualification_entries() -> list[dict[str, Any]]:
    entries = load_qualification_registry().get("qualifications")
    if not isinstance(entries, list):
        raise ValueError("qualification registry qualifications must be a list")
    return entries


def qualification_index() -> dict[str, dict[str, Any]]:
    return {str(entry["id"]): entry for entry in qualification_entries()}


def validate_qualification_registry() -> list[str]:
    failures: list[str] = []
    version = load_qualification_registry().get("version")
    if version != QUALIFICATION_REGISTRY_VERSION:
        failures.append(
            f"qualification registry version must be {QUALIFICATION_REGISTRY_VERSION}, got {version}"
        )
    entries = qualification_entries()
    ids = [entry.get("id") for entry in entries]
    if len(ids) != len(set(ids)):
        failures.append("qualification IDs must be unique")
    known_caps = set(capability_index().keys())
    for entry in entries:
        missing = REQUIRED_QUALIFICATION_FIELDS - set(entry.keys())
        if missing:
            failures.append(f"{entry.get('id')}: missing fields {sorted(missing)}")
        if entry.get("default_production_activation") is True:
            failures.append(f"{entry.get('id')}: default_production_activation must be false")
        for cap_id in entry.get("compatible_capabilities", []):
            if cap_id not in known_caps:
                failures.append(f"{entry.get('id')}: unknown capability {cap_id}")
        if not entry.get("source_workflow_run"):
            failures.append(f"{entry.get('id')}: missing source_workflow_run evidence")
        if not entry.get("evidence_schema"):
            failures.append(f"{entry.get('id')}: missing evidence_schema")
    return failures


def audit_qualification_drift(
    *,
    contract_versions: dict[str, str] | None = None,
    requested_capabilities: list[str] | None = None,
) -> dict[str, str]:
    """Return drift status per qualification ID."""
    contract_versions = contract_versions or {}
    requested_capabilities = requested_capabilities or []
    drift: dict[str, str] = {}
    for qual_id, entry in qualification_index().items():
        status = str(entry.get("status") or DRIFT_VALID)
        contract_version = str(entry.get("contract_version") or "")
        if contract_versions.get(qual_id) and contract_versions[qual_id] != contract_version:
            drift[qual_id] = DRIFT_STALE
            continue
        if not entry.get("source_workflow_run"):
            drift[qual_id] = DRIFT_MISSING_EVIDENCE
            continue
        compatible = set(entry.get("compatible_capabilities") or [])
        if requested_capabilities and not set(requested_capabilities).issubset(compatible):
            drift[qual_id] = DRIFT_SCOPE_EXPANSION_BLOCKED
            continue
        drift[qual_id] = status if status in {
            DRIFT_VALID,
            DRIFT_STALE,
            DRIFT_INCOMPATIBLE,
            DRIFT_MISSING_EVIDENCE,
            DRIFT_SCOPE_EXPANSION_BLOCKED,
        } else DRIFT_VALID
    return drift


def capability_drift_for_qualifications() -> list[str]:
    failures: list[str] = []
    known_caps = set(capability_index().keys())
    for qual_id, entry in qualification_index().items():
        for cap_id in entry.get("compatible_capabilities", []):
            if cap_id not in known_caps:
                failures.append(f"{qual_id}: references removed capability {cap_id}")
    return failures
