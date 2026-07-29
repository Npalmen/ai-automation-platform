"""Continuous regression report schema and serialization."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.evaluation.regression.constants import (
    QUALIFICATION_REGISTRY_VERSION,
    REGISTRY_VERSION,
    REPORT_SCHEMA_VERSION,
)


def build_report(
    *,
    run_id: str,
    runtime_sha: str,
    tier: str,
    trigger: str,
    selected_suites: list[str],
    skipped_suites: list[str],
    skip_reasons: dict[str, str],
    test_counts: dict[str, int],
    scenario_counts: dict[str, int],
    qualification_drift: dict[str, str],
    capability_drift: list[str],
    migration_result: str,
    determinism_result: str,
    external_writes: int,
    network_attempts: int,
    cross_tenant_findings: list[str],
    security_failures: list[str],
    quarantined_tests: list[str],
    cleanup_status: str,
    redaction_status: str,
    duration_seconds: float,
    status: str,
    suite_results: list[dict[str, Any]] | None = None,
    failure_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "run_id": run_id,
        "runtime_sha": runtime_sha,
        "tier": tier,
        "trigger": trigger,
        "registry_version": REGISTRY_VERSION,
        "qualification_registry_version": QUALIFICATION_REGISTRY_VERSION,
        "selected_suites": selected_suites,
        "skipped_suites": skipped_suites,
        "skip_reasons": skip_reasons,
        "test_counts": test_counts,
        "scenario_counts": scenario_counts,
        "qualification_drift": qualification_drift,
        "capability_drift": capability_drift,
        "migration_result": migration_result,
        "determinism_result": determinism_result,
        "external_writes": external_writes,
        "network_attempts": network_attempts,
        "cross_tenant_findings": cross_tenant_findings,
        "security_failures": security_failures,
        "quarantined_tests": quarantined_tests,
        "cleanup_status": cleanup_status,
        "redaction_status": redaction_status,
        "duration_seconds": duration_seconds,
        "status": status,
        "suite_results": suite_results or [],
        "failure_payload": failure_payload or {},
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }


def validate_report_schema(report: dict[str, Any]) -> list[str]:
    required = {
        "schema_version",
        "run_id",
        "runtime_sha",
        "tier",
        "trigger",
        "registry_version",
        "qualification_registry_version",
        "selected_suites",
        "skipped_suites",
        "skip_reasons",
        "test_counts",
        "scenario_counts",
        "qualification_drift",
        "capability_drift",
        "migration_result",
        "determinism_result",
        "external_writes",
        "network_attempts",
        "cross_tenant_findings",
        "security_failures",
        "quarantined_tests",
        "cleanup_status",
        "redaction_status",
        "duration_seconds",
        "status",
    }
    missing = required - set(report.keys())
    failures: list[str] = []
    if report.get("schema_version") != REPORT_SCHEMA_VERSION:
        failures.append("schema_version must be continuous_regression_report_v1")
    if missing:
        failures.append(f"missing report fields: {sorted(missing)}")
    return failures


def write_json_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True)


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Continuous regression report",
        "",
        f"**Status:** {report.get('status')}",
        f"**Tier:** {report.get('tier')}",
        f"**Run ID:** {report.get('run_id')}",
        f"**Git SHA:** {report.get('runtime_sha')}",
        f"**External writes:** {report.get('external_writes')}",
        f"**Network attempts:** {report.get('network_attempts')}",
        "",
        "## Selected suites",
    ]
    for suite_id in report.get("selected_suites", []):
        lines.append(f"- {suite_id}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
