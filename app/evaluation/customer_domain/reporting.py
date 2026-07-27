"""Report serialization for customer-domain stateful evaluation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_SCHEMA_VERSION = "customer_domain_stateful_eval_v1"


def _scan_for_credentials(payload: Any) -> bool:
    forbidden = (
        "password",
        "api_key",
        "access_token",
        "refresh_token",
        "authorization",
        "credential",
        "secret",
    )
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_norm = str(key).lower()
            if any(token in key_norm for token in forbidden):
                return True
            if _scan_for_credentials(value):
                return True
    elif isinstance(payload, list):
        return any(_scan_for_credentials(item) for item in payload)
    elif isinstance(payload, str):
        lower = payload.lower()
        return any(token in lower for token in ("api_key=", "bearer ", "refresh_token"))
    return False


def write_json_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, default=str)


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Customer domain stateful evaluation",
        "",
        f"**Overall:** {report.get('overall_result')}",
        f"**Git SHA:** {report.get('git_sha')}",
        f"**Database:** {report.get('database_kind')} ({report.get('database_fingerprint')})",
        f"**External side effects:** {report.get('external_side_effects')}",
        f"**Credentials exposed:** {report.get('credentials_exposed')}",
        f"**Non-eval rows changed:** {report.get('non_eval_rows_changed')}",
        f"**Repeat-run consistent:** {report.get('repeat_run_consistent')}",
        "",
        "## Scenarios",
    ]
    for scenario in report.get("scenarios", []):
        lines.append(
            f"- {scenario.get('scenario_id')}: {scenario.get('result')} "
            f"(hash={scenario.get('semantic_result_hash')})"
        )
    lines.extend(
        [
            "",
            "## Controls",
            f"- Tenant controls: {report.get('tenant_controls', {}).get('result')}",
            f"- Concurrency: {report.get('concurrency_controls', {}).get('result')}",
            f"- Security: {report.get('security_controls', {}).get('result')}",
            f"- Feature flags: {report.get('feature_flag_controls', {}).get('result')}",
            "",
            "## Deferred capabilities",
        ]
    )
    for item in report.get("deferred_capabilities", []):
        lines.append(f"- {item}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_report(
    *,
    git_sha: str,
    database_kind: str,
    database_fingerprint: str,
    scenarios: list[dict[str, Any]],
    tenant_controls: dict[str, Any],
    concurrency_controls: dict[str, Any],
    security_controls: dict[str, Any],
    feature_flag_controls: dict[str, Any],
    external_side_effects: int,
    non_eval_rows_changed: int,
    repeat_run_consistent: bool,
    deferred_capabilities: list[str],
    h_gap_findings: list[str],
    started_at: datetime,
    completed_at: datetime,
) -> dict[str, Any]:
    passed = sum(1 for s in scenarios if s.get("result") == "PASS")
    failed = sum(1 for s in scenarios if s.get("result") == "FAIL")
    blocked = sum(1 for s in scenarios if s.get("result") == "BLOCKED")
    control_results = [
        tenant_controls.get("result"),
        concurrency_controls.get("result"),
        security_controls.get("result"),
        feature_flag_controls.get("result"),
    ]
    overall = "PASS"
    if blocked:
        overall = "BLOCKED"
    elif failed or any(r != "PASS" for r in control_results):
        overall = "FAIL"
    elif external_side_effects > 0 or non_eval_rows_changed > 0:
        overall = "FAIL"
    elif not repeat_run_consistent:
        overall = "FAIL"

    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "evaluation_id": f"customer-domain-eval-{started_at.strftime('%Y%m%d%H%M%S')}",
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "git_sha": git_sha,
        "database_kind": database_kind,
        "database_fingerprint": database_fingerprint,
        "external_side_effects": external_side_effects,
        "credentials_exposed": False,
        "non_eval_rows_changed": non_eval_rows_changed,
        "scenario_count": len(scenarios),
        "passed_count": passed,
        "failed_count": failed,
        "blocked_count": blocked,
        "overall_result": overall,
        "repeat_run_consistent": repeat_run_consistent,
        "scenarios": scenarios,
        "tenant_controls": tenant_controls,
        "concurrency_controls": concurrency_controls,
        "security_controls": security_controls,
        "feature_flag_controls": feature_flag_controls,
        "deferred_capabilities": deferred_capabilities,
        "h_gap_findings": h_gap_findings,
    }
    scan_payload = {
        "scenarios": scenarios,
        "tenant_controls": tenant_controls,
        "concurrency_controls": concurrency_controls,
        "security_controls": security_controls,
        "feature_flag_controls": feature_flag_controls,
    }
    report["credentials_exposed"] = _scan_for_credentials(scan_payload)
    return report
