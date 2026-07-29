"""Hermetic contract tests for TBF manifest and registry."""

from __future__ import annotations

from app.evaluation.customer_domain.registry import (
    EXPECTED_SCENARIO_IDS,
    load_manifest,
    load_tbf_runners,
    manifest_scenarios,
    validate_manifest,
)
from app.evaluation.customer_domain.reporting import REPORT_SCHEMA_VERSION
from app.evaluation.customer_domain.semantic_hash import semantic_hash


def test_manifest_contains_exact_tbf01_to_tbf10():
    scenarios = manifest_scenarios()
    ids = [entry["scenario_id"] for entry in scenarios]
    assert ids == list(EXPECTED_SCENARIO_IDS)


def test_manifest_scenario_ids_unique():
    ids = [entry["scenario_id"] for entry in manifest_scenarios()]
    assert len(ids) == len(set(ids))


def test_manifest_validation_passes():
    assert validate_manifest() == []


def test_registry_loads_all_runners():
    runners = load_tbf_runners()
    assert set(runners) == set(EXPECTED_SCENARIO_IDS)


def test_manifest_campaign_type():
    manifest = load_manifest()
    assert manifest["campaign_type"] == "customer-card-stateful"


def test_report_schema_version_v2():
    assert REPORT_SCHEMA_VERSION == "customer_domain_stateful_eval_v2"


def test_semantic_hash_stable_for_oracle_shape():
    payload = {
        "end_customer_count": 1,
        "current_state": {"phone": "+46700101001"},
        "tenant_id": "eval_cd_abc_tbf01",
    }
    assert semantic_hash(payload) == semantic_hash(
        {
            "end_customer_count": 1,
            "current_state": {"phone": "+46700101001"},
            "tenant_id": "eval_cd_other",
        }
    )
