"""Safety gate coverage matrix (gate id → scenario or test)."""

from __future__ import annotations

SAFETY_GATE_COVERAGE: dict[str, str] = {
    "S-POL-01": "S10_urgent_electrical_safety",
    "S-POL-02": "S14_approval_gated_default",
    "S-POL-03": "S19_invoice_no_dispatch",
    "S-ACT-01": "S17_unknown_action_blocked",
    "S-ACT-02": "S14_approval_gated_default",
    "S-TRC-01": "tests/evaluation/test_harness_self.py::test_pending_intent_blocks_automatic_retry",
    "S-TRC-02": "S18_approval_resume_operation_id",
    "S-APPROVAL-01": "S18_approval_resume_operation_id",
    "S-CNT-01": "S08_sensitive_inkasso",
    "S-CNT-03": "tests/evaluation/test_harness_self.py::test_db_rollback_clears_tenant_rows",
    "S-INF-01": "tests/evaluation/test_harness_self.py::test_readiness_fails_without_migration",
    "S-DATA-01": "S20_data_deletion_request",
    "S-PG-01": "tests/evaluation/test_pg_eval_isolation.py::test_pg_migration_chain_from_empty_database",
    "S-PG-02": "tests/evaluation/test_pg_eval_isolation.py::test_pg_tenant_purge_after_scenario",
    "S-PG-03": "tests/evaluation/test_pg_eval_isolation.py::test_concurrent_approval_cas_single_execution",
    "S-PG-04": "tests/evaluation/test_pg_eval_isolation.py::test_pg_migration_014_to_015_upgrade_path",
    "S-PG-05": "tests/evaluation/test_pg_eval_isolation.py::test_pg_concurrent_append_if_absent",
    "S-PG-06": "tests/evaluation/test_pg_eval_isolation.py::test_pg_decision_trace_readiness_with_migration_015",
    "S-PG-07": "tests/evaluation/test_pg_eval_isolation.py::test_pg_decision_trace_readiness_without_migration_015",
}
