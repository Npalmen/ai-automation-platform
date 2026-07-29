"""Hermetic contract tests for continuous regression registry."""

from __future__ import annotations

import pytest

from app.evaluation.regression.constants import AUTOMATED_TIERS, EXPECTED_TBR_IDS
from app.evaluation.regression.determinism import validate_migration_registry
from app.evaluation.regression.feature_flags import validate_feature_flag_defaults
from app.evaluation.regression.qualification_registry import (
    audit_qualification_drift,
    qualification_entries,
    validate_qualification_registry,
)
from app.evaluation.regression.registry import suite_entries, suite_index, validate_regression_registry
from app.evaluation.regression.reporting import REPORT_SCHEMA_VERSION, build_report, validate_report_schema


def test_regression_suite_ids_unique():
    ids = [entry["id"] for entry in suite_entries()]
    assert len(ids) == len(set(ids))


def test_regression_registry_valid():
    failures = validate_regression_registry()
    assert failures == [], failures


def test_qualification_ids_unique():
    ids = [entry["id"] for entry in qualification_entries()]
    assert len(ids) == len(set(ids))


def test_qualification_registry_valid():
    failures = validate_qualification_registry()
    assert failures == [], failures


def test_automated_tiers_forbid_network_and_writes():
    for entry in suite_entries():
        for tier in entry.get("tier", []):
            if tier in AUTOMATED_TIERS:
                assert entry.get("network") == "forbidden"
                assert int(entry.get("external_write_budget", -1)) == 0


def test_qualification_drift_defaults_valid():
    drift = audit_qualification_drift()
    assert drift
    assert all(status == "VALID" for status in drift.values())


def test_migration_registry_consistent():
    assert validate_migration_registry() == []


def test_feature_flags_fail_closed_defaults():
    assert validate_feature_flag_defaults() == []


def test_report_schema_valid():
    report = build_report(
        run_id="test",
        runtime_sha="abc",
        tier="pr_fast",
        trigger="unit",
        selected_suites=["regression-registry-contract"],
        skipped_suites=[],
        skip_reasons={},
        test_counts={"selected": 1},
        scenario_counts={"tbr": 20},
        qualification_drift={},
        capability_drift=[],
        migration_result="PASS",
        determinism_result="PASS",
        external_writes=0,
        network_attempts=0,
        cross_tenant_findings=[],
        security_failures=[],
        quarantined_tests=[],
        cleanup_status="restored",
        redaction_status="clean",
        duration_seconds=1.0,
        status="PASS",
    )
    assert validate_report_schema(report) == []
    assert report["schema_version"] == REPORT_SCHEMA_VERSION


def test_unknown_tier_rejected_by_runner():
    from app.evaluation.regression.runner import run_tier

    with pytest.raises(ValueError, match="Unknown automated tier"):
        run_tier("manual_canary")


def test_suite_commands_are_lists():
    for entry in suite_entries():
        command = entry.get("command")
        assert isinstance(command, list) and command


def test_all_suite_ids_addressable():
    index = suite_index()
    for entry in suite_entries():
        assert entry["id"] in index


def test_expected_tbr_count():
    assert len(EXPECTED_TBR_IDS) == 20
