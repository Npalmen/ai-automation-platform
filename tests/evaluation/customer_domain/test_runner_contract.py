"""Contract tests for customer-domain stateful evaluation (no PostgreSQL required)."""

from __future__ import annotations

import pytest

from app.evaluation.customer_domain.guards import (
    EvalGuardError,
    ExternalSideEffectGuard,
    REQUIRED_DB_NAME_FRAGMENT,
    assert_eval_database_url,
    assert_eval_environment,
)
from app.evaluation.customer_domain.reporting import REPORT_SCHEMA_VERSION, build_report
from app.evaluation.customer_domain.scenario_schema import (
    ALLOWED_ACTIONS,
    SCENARIO_SCHEMA_VERSION,
    StatefulScenario,
    ScenarioStep,
)
from app.evaluation.customer_domain.semantic_hash import semantic_hash
from app.evaluation.customer_domain.db import cleanup_eval_tenants
from datetime import datetime, timezone


def test_scenario_schema_accepts_valid_fixture():
    scenario = StatefulScenario(
        scenario_id="contract_fixture",
        family="family_01",
        tenant_id="eval_cd_contract",
        description="contract",
        steps=[
            ScenarioStep(
                step_id="step1",
                phase="act",
                action="create_private_customer",
                payload={"display_name": "Test"},
                idempotency_key="key-1",
            )
        ],
        expected_final_invariants=["customer_count"],
    )
    assert scenario.schema_version == SCENARIO_SCHEMA_VERSION


def test_scenario_schema_rejects_duplicate_step_id():
    with pytest.raises(ValueError, match="duplicate step_id"):
        StatefulScenario(
            scenario_id="dup_steps",
            family="family_01",
            tenant_id="eval_cd_dup",
            steps=[
                ScenarioStep(step_id="same", phase="act", action="create_private_customer"),
                ScenarioStep(step_id="same", phase="assert", action="assert_db_counts"),
            ],
        )


def test_scenario_schema_rejects_unknown_version():
    with pytest.raises(ValueError, match="unsupported schema_version"):
        StatefulScenario(
            schema_version="v0",
            scenario_id="bad_version",
            family="family_01",
            tenant_id="eval_cd_bad",
        )


def test_allowed_actions_include_production_and_arrange():
    assert "create_private_customer" in ALLOWED_ACTIONS
    assert "arrange_thread_link" in ALLOWED_ACTIONS


def test_semantic_hash_normalizes_uuid_and_timestamp():
    payload = {
        "customer_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "at": "2026-07-26T12:00:00+00:00",
        "tenant_id": "eval_cd_family01",
        "status": "verified",
    }
    h1 = semantic_hash(payload)
    h2 = semantic_hash(
        {
            "customer_id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
            "at": "2020-01-01T00:00:00+00:00",
            "tenant_id": "eval_cd_other",
            "status": "verified",
        }
    )
    assert h1 == h2


def test_db_guard_rejects_non_eval_database_name():
    with pytest.raises(EvalGuardError, match=REQUIRED_DB_NAME_FRAGMENT):
        assert_eval_database_url("postgresql://postgres:postgres@localhost:5432/ai_platform")


def test_db_guard_accepts_eval_database_name(monkeypatch):
    monkeypatch.setenv("ENV", "test")
    name = assert_eval_database_url(
        "postgresql://postgres:postgres@localhost:5432/ai_platform_customer_domain_eval"
    )
    assert "customer_domain_eval" in name


def test_external_guard_records_violation():
    guard = ExternalSideEffectGuard()
    with pytest.raises(EvalGuardError):
        guard.record("gmail.send")
    assert guard.count == 1


def test_report_schema_fields():
    now = datetime.now(timezone.utc)
    report = build_report(
        git_sha="abc",
        database_kind="postgresql",
        database_fingerprint="ai_platform_customer_domain_eval",
        scenarios=[],
        tenant_controls={"result": "PASS"},
        concurrency_controls={"result": "PASS"},
        security_controls={"result": "PASS"},
        feature_flag_controls={"result": "PASS"},
        external_side_effects=0,
        non_eval_rows_changed=0,
        repeat_run_consistent=True,
        deferred_capabilities=[],
        h_gap_findings=[],
        started_at=now,
        completed_at=now,
    )
    assert report["schema_version"] == REPORT_SCHEMA_VERSION
    assert report["credentials_exposed"] is False


def test_audit_idempotency_scan_ignores_masked_reference():
    from app.evaluation.customer_domain.controls import _audit_contains_raw_idempotency_key

    assert not _audit_contains_raw_idempotency_key(
        {"idempotency_reference": "sha256:abcdef"}
    )
    assert _audit_contains_raw_idempotency_key({"idempotency_key": "raw-key"})


def test_eval_environment_requires_allowlisted_env(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    from app.core.settings import get_settings

    get_settings.cache_clear()
    with pytest.raises(EvalGuardError):
        assert_eval_environment()
    get_settings.cache_clear()
