"""Report serialization for full-function matrix evaluation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORT_SCHEMA_VERSION = "full_function_matrix_eval_v1"


def _scan_for_credentials(payload: Any) -> bool:
    forbidden_key_tokens = ("password", "api_key", "access_token", "refresh_token", "authorization")
    if isinstance(payload, dict):
        for key, value in payload.items():
            if any(token in str(key).lower() for token in forbidden_key_tokens):
                return True
            if _scan_for_credentials(value):
                return True
    elif isinstance(payload, list):
        return any(_scan_for_credentials(item) for item in payload)
    elif isinstance(payload, str):
        lower = payload.lower()
        return any(token in lower for token in forbidden_key_tokens)
    return False


def write_json_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, default=str)


def write_markdown_report(path: Path, report: dict[str, Any]) -> None:
    lines = [
        "# Full-function matrix evaluation",
        "",
        f"**Overall:** {report.get('overall_result')}",
        f"**Git SHA:** {report.get('git_sha')}",
        f"**External side effects:** {report.get('external_side_effects')}",
        f"**Matrix status summary:** {report.get('matrix_status_summary')}",
        "",
        "## Scenarios",
    ]
    for scenario in report.get("scenarios", []):
        lines.append(f"- {scenario.get('scenario_id')}: {scenario.get('result')}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_report(
    *,
    git_sha: str,
    database_fingerprint: str,
    scenarios: list[dict[str, Any]],
    campaign_oracle: dict[str, Any] | None,
    cleanup_result: dict[str, Any] | None,
    matrix_status_summary: dict[str, int],
    external_side_effects: int,
    repeat_run_consistent: bool,
    repeat_hash_mismatches: dict[str, Any] | None = None,
    started_at: datetime,
    completed_at: datetime,
) -> dict[str, Any]:
    failed = [s for s in scenarios if s.get("result") != "PASS"]
    overall = "PASS" if not failed and (cleanup_result or {}).get("cleanup_status") == "restored" else "FAIL"
    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "overall_result": overall,
        "git_sha": git_sha,
        "database_kind": "postgresql",
        "database_fingerprint": database_fingerprint,
        "campaign_type": "tbg",
        "scenarios": scenarios,
        "campaign_oracle": campaign_oracle,
        "cleanup_result": cleanup_result,
        "matrix_status_summary": matrix_status_summary,
        "external_side_effects": external_side_effects,
        "credentials_exposed": _scan_for_credentials(scenarios),
        "repeat_run_consistent": repeat_run_consistent,
        "repeat_hash_mismatches": repeat_hash_mismatches or {},
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "new_live_external_writes": 0,
    }
