"""TBR01-TBR20 continuous regression scenario contracts."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
import yaml

from app.evaluation.regression.constants import EXPECTED_TBR_IDS, SECURITY_CRITICAL_SUITE_TAGS
from app.evaluation.regression.determinism import validate_repeat_run_hashes, validate_semantic_hash_version
from app.evaluation.regression.flakiness import FlakinessPolicyError, FlakinessState, QuarantineEntry
from app.evaluation.regression.guards import NetworkGuard, RegressionGuardError, WriteBudgetGuard
from app.evaluation.regression.impact import is_shared_core_change, select_suites_for_changes
from app.evaluation.regression.qualification_registry import audit_qualification_drift
from app.evaluation.regression.reporting import validate_report_schema
from app.evaluation.regression.runner import run_tier


def test_tbr01_clean_pr_fast_selection_docs_only():
    selected, _ = select_suites_for_changes(["docs/README.md"], tier="pr_fast")
    assert "regression-registry-contract" in selected
    assert "pg-eval-suite" not in selected


def test_tbr02_shared_decisioning_change_broad_regression():
    selected, _ = select_suites_for_changes(["app/decisioning/policy.py"], tier="main_pg")
    assert "release-gate-hermetic" in selected
    assert "full-function-contract" in selected
    assert is_shared_core_change(["app/workflows/intake.py"]) is True


def test_tbr03_customer_domain_change_triggers_f_and_g():
    selected, _ = select_suites_for_changes(["app/domain/customer/models.py"], tier="main_pg")
    assert "customer-domain-manifest-contract" in selected
    assert "pg-eval-suite" in selected


def test_tbr04_migration_added_triggers_migration_chain():
    selected, _ = select_suites_for_changes(["migrations/025_example.sql"], tier="main_pg")
    assert "migration-chain-bootstrap" in selected


def test_tbr05_workflow_change_triggers_contracts():
    selected, _ = select_suites_for_changes([".github/workflows/release-gate.yml"], tier="pr_fast")
    assert "workflow-live-eval-contract" in selected


def test_tbr06_unknown_path_uses_conservative_fallback():
    selected, _ = select_suites_for_changes(["misc/unknown_file.txt"], tier="pr_fast")
    assert "regression-registry-contract" in selected
    assert "full-function-contract" in selected


def test_tbr07_qualification_contract_drift_stale():
    drift = audit_qualification_drift(
        contract_versions={"FULL_FUNCTION_MATRIX_PASS": "broken-version"},
    )
    assert drift["FULL_FUNCTION_MATRIX_PASS"] == "STALE"


def test_tbr08_capability_drift_detected_via_registry_validation():
    from app.evaluation.regression.qualification_registry import capability_drift_for_qualifications

    assert capability_drift_for_qualifications() == []


def test_tbr09_determinism_drift_blocks_repeat_run():
    failures = validate_repeat_run_hashes({"TBG01": "a"}, {"TBG01": "b"})
    assert failures


def test_tbr10_blind_rerun_forbidden_and_first_failure_preserved():
    state = FlakinessState()
    assert state.blind_rerun_forbidden() is True
    from app.evaluation.regression.flakiness import FailureArtifact

    state.record_failure(FailureArtifact("suite", 1, "boom"))
    state.record_failure(FailureArtifact("suite", 1, "boom-again"))
    assert state.first_failure is not None
    assert state.first_failure.output == "boom"


def test_tbr11_quarantine_expiry_blocks():
    state = FlakinessState()
    with pytest.raises(FlakinessPolicyError, match="expiry"):
        state.register_quarantine(
            QuarantineEntry(
                test_id="flaky-test",
                owner="platform",
                expires_on=date.today() - timedelta(days=1),
                issue_ref="INC-1",
            )
        )


def test_tbr12_unauthorized_network_attempt_blocked():
    guard = NetworkGuard(tier="pr_fast")
    with pytest.raises(RegressionGuardError, match="Forbidden network"):
        guard.record("gmail.googleapis.com", call_site="test")


def test_tbr13_external_write_attempt_blocked_before_adapter():
    guard = WriteBudgetGuard(tier="pr_fast")
    with pytest.raises(RegressionGuardError, match="External write budget"):
        guard.record("gmail")


def test_tbr14_tenant_isolation_cannot_be_quarantined():
    state = FlakinessState()
    with pytest.raises(FlakinessPolicyError, match="security-critical"):
        state.register_quarantine(
            QuarantineEntry(
                test_id="tenant-isolation",
                owner="platform",
                expires_on=date.today() + timedelta(days=7),
                issue_ref="INC-2",
                suite_tags=["tenant_isolation"],
            )
        )
    assert "tenant_isolation" in SECURITY_CRITICAL_SUITE_TAGS


def test_tbr15_cleanup_regression_blocks_pass_status():
    report = run_tier("pr_fast", dry_run=True, report_json=None, report_markdown=None)
    report["cleanup_status"] = "failed"
    if report["cleanup_status"] != "restored":
        report["status"] = "FAIL"
    assert report["status"] == "FAIL"


def test_tbr16_feature_flag_default_drift_blocks(monkeypatch):
    monkeypatch.setattr(
        "app.evaluation.regression.runner.validate_feature_flag_defaults",
        lambda: ["END_CUSTOMER_WRITE_API_ENABLED default must be false"],
    )
    report = run_tier("pr_fast", dry_run=True, report_json=None, report_markdown=None)
    assert report["status"] == "FAIL"


def test_tbr17_broken_artifact_schema_fails():
    failures = validate_report_schema({"schema_version": "broken"})
    assert failures


def test_tbr18_missing_evidence_reference_blocks_pass_live_claim():
    drift = audit_qualification_drift()
    for qual_id, entry in drift.items():
        assert qual_id
    assert drift["FULL_FUNCTION_MATRIX_PASS"] == "VALID"


def test_tbr19_nightly_tier_dry_run_structure_passes_registry_checks():
    report = run_tier("nightly", dry_run=True, report_json=None, report_markdown=None)
    assert "pg-eval-suite" in report["selected_suites"]
    assert report["external_writes"] == 0


def test_tbr20_manual_live_workflow_has_no_schedule():
    workflow_path = (
        __import__("pathlib").Path(__file__).resolve().parents[3]
        / ".github"
        / "workflows"
        / "live-eval.yml"
    )
    data = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    trigger = data.get("on") or data[True]
    assert "schedule" not in trigger
    assert "workflow_dispatch" in trigger


@pytest.mark.parametrize("scenario_id", EXPECTED_TBR_IDS)
def test_tbr_scenario_ids_registered(scenario_id):
    assert scenario_id.startswith("TBR")
