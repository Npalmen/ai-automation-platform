"""Hermetic contract tests for full-function registry and matrix."""

from __future__ import annotations

from app.evaluation.full_function.evidence import validate_tbg05_evidence
from app.evaluation.full_function.matrix import validate_matrix
from app.evaluation.full_function.registry import (
    EXPECTED_SCENARIO_IDS,
    capability_entries,
    validate_capabilities,
    validate_manifest,
)


def test_capability_ids_unique():
    ids = [entry["id"] for entry in capability_entries()]
    assert len(ids) == len(set(ids))


def test_manifest_has_tbg01_to_tbg25():
    failures = validate_manifest()
    assert failures == [], failures


def test_matrix_references_registered_capabilities():
    failures = validate_matrix()
    assert failures == [], failures


def test_registry_entrypoints_exist_for_actions():
    from app.workflows.action_authorization import ACTION_REGISTRY

    failures = validate_capabilities()
    assert failures == [], failures
    for entry in capability_entries():
        entrypoint = entry.get("entrypoint")
        if entrypoint in ACTION_REGISTRY:
            assert entry["id"].startswith("action.")


def test_expected_scenario_count():
    assert len(EXPECTED_SCENARIO_IDS) == 25


def test_tbg05_live_evidence_binding_compatible():
    assert validate_tbg05_evidence() == []
