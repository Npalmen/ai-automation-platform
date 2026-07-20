"""Safety gate coverage matrix and executable coverage gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.evaluation.dataset_manifest import DatasetManifest, load_manifest, resolve_scenarios_root
from app.evaluation.errors import HarnessError
from app.evaluation.loader import load_scenario
from app.evaluation.schema.scenario import ScenarioContract

SAFETY_GATE_COVERAGE: dict[str, str] = {
    "S-POL-01": "S10_urgent_electrical_safety",
    "S-POL-02": "S14_approval_gated_default",
    "S-POL-03": "S19_invoice_no_dispatch",
    "S-ACT-01": "S17_unknown_action_blocked",
    "S-ACT-02": "S14_approval_gated_default",
    "S-TRC-01": "S21_pending_blocks_retry",
    "S-TRC-02": "S18_approval_resume_operation_id",
    "S-APPROVAL-01": "S18_approval_resume_operation_id",
    "S-CNT-01": "S08_sensitive_inkasso",
    "S-CNT-02": "S22_cross_tenant_isolation",
    "S-CNT-03": "tests/evaluation/test_harness_self.py::test_db_rollback_clears_tenant_rows",
    "S-INF-01": "tests/evaluation/test_harness_self.py::test_readiness_fails_without_migration",
    "S-DATA-01": "S20_data_deletion_request",
    "S-INJ-01": "S31_prompt_injection_customer_text",
    "S-ADV-01": "S33_legal_threat_complaint",
    "S-ADV-02": "S34_spam_phishing_link",
    "S-PG-01": "tests/evaluation/test_pg_eval_isolation.py::test_pg_migration_chain_from_empty_database",
    "S-PG-02": "tests/evaluation/test_pg_eval_isolation.py::test_pg_tenant_purge_after_scenario",
    "S-PG-03": "tests/evaluation/test_pg_eval_isolation.py::test_concurrent_approval_cas_single_execution",
    "S-PG-04": "tests/evaluation/test_pg_eval_isolation.py::test_pg_migration_014_to_015_upgrade_path",
    "S-PG-05": "tests/evaluation/test_pg_eval_isolation.py::test_pg_concurrent_append_if_absent",
    "S-PG-06": "tests/evaluation/test_pg_eval_isolation.py::test_pg_decision_trace_readiness_with_migration_015",
    "S-PG-07": "tests/evaluation/test_pg_eval_isolation.py::test_pg_decision_trace_readiness_without_migration_015",
}


@dataclass
class CoverageGateResult:
    passed: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _forbidden_configured(scenario: ScenarioContract) -> bool:
    forbidden = scenario.expect.outcomes.forbidden
    return bool(
        forbidden.actions
        or forbidden.policy_authorizations
        or forbidden.reply_claims
        or forbidden.cross_tenant_access
        or forbidden.automatic_retry
        or forbidden.max_real_external_calls is not None
    )


def validate_coverage(
    manifest: DatasetManifest,
    scenarios_root: Path,
    *,
    loaded_scenarios: dict[str, ScenarioContract] | None = None,
    run_mode: str = "full",
) -> CoverageGateResult:
    errors: list[str] = []
    loaded = dict(loaded_scenarios or {})
    if not loaded:
        for sid in manifest.scenarios:
            path = scenarios_root / f"{sid}.yaml"
            if not path.exists():
                errors.append(f"manifest scenario file missing: {sid}")
                continue
            loaded[sid] = load_scenario(path)

    manifest_ids = set(manifest.scenarios)
    loaded_ids = set(loaded)

    if run_mode == "full":
        for path in sorted(scenarios_root.glob("*.yaml")):
            scenario = load_scenario(path)
            if scenario.scenario_id not in manifest_ids:
                errors.append(f"phantom scenario file not in manifest: {scenario.scenario_id}")

        if len(manifest.scenarios) != 20:
            errors.append(f"dataset must contain exactly 20 scenarios, got {len(manifest.scenarios)}")

    if run_mode in ("full", "smoke"):
        if len(manifest.smoke) != 10:
            errors.append(f"smoke set must contain exactly 10 scenarios, got {len(manifest.smoke)}")

    for gate, target in SAFETY_GATE_COVERAGE.items():
        if target.startswith("tests/"):
            continue
        if run_mode == "single" and target not in loaded_ids:
            continue
        if run_mode == "smoke" and target not in loaded_ids and target not in manifest.smoke:
            continue
        if target not in manifest_ids:
            errors.append(f"phantom gate reference {gate} -> missing scenario {target}")
        elif target not in loaded:
            errors.append(f"coverage gate {gate} scenario not loaded: {target}")

    smoke_ids = manifest.smoke if run_mode in ("full", "smoke") else []
    for sid in smoke_ids:
        if sid not in manifest_ids:
            errors.append(f"smoke scenario not in manifest scenarios list: {sid}")
        elif run_mode == "smoke" and sid not in loaded_ids:
            errors.append(f"smoke scenario not loaded: {sid}")
        elif sid in loaded and "smoke" not in loaded[sid].tags:
            errors.append(f"smoke scenario missing smoke tag: {sid}")

    for sid, scenario in loaded.items():
        if scenario.requires_forbidden and not _forbidden_configured(scenario):
            errors.append(f"high/critical scenario missing forbidden outcomes: {sid}")
        if scenario.source_mode != "fixture":
            errors.append(f"2E dataset scenario must use source_mode=fixture: {sid}")

    return CoverageGateResult(passed=not errors, errors=errors)


def enforce_coverage(manifest_path: Path | None = None) -> CoverageGateResult:
    path = manifest_path or (
        Path(__file__).resolve().parents[2] / "tests" / "evaluation" / "datasets" / "k2e-v1.yaml"
    )
    manifest = load_manifest(path)
    root = resolve_scenarios_root(manifest, path)
    result = validate_coverage(manifest, root)
    if not result.passed:
        raise HarnessError("coverage_gate_failed: " + "; ".join(result.errors))
    return result
