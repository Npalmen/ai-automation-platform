"""Structured evidence for profile semi-auto live campaigns."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVIDENCE_SCHEMA = "profile_testbot_semi_auto_live_v1"


def build_campaign_evidence(
    *,
    campaign_state: dict[str, Any],
    scenario_results: list[dict[str, Any]],
    external_writes: dict[str, int],
    tenant_isolation: dict[str, Any],
    cleanup: dict[str, Any],
) -> dict[str, Any]:
    return {
        "report_schema_version": EVIDENCE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime_sha": campaign_state.get("runtime_sha"),
        "campaign_id": campaign_state.get("campaign_id"),
        "profile_id": campaign_state.get("profile_id"),
        "profile_snapshot_hash": campaign_state.get("profile_snapshot_hash"),
        "manifest_hash": campaign_state.get("manifest_hash"),
        "oracle_versions": {"profile_testbot": campaign_state.get("oracle_version")},
        "scenario_count": len(scenario_results),
        "scenario_states": scenario_results,
        "external_writes": external_writes,
        "tenant_isolation": tenant_isolation,
        "idempotency": {
            "campaign_bound": True,
            "resume_supported": True,
        },
        "cleanup": cleanup,
        "qualification_status": campaign_state.get("qualification_status", "PENDING"),
        "contract_mode": campaign_state.get("contract_mode", True),
        "overall_status": campaign_state.get("overall_status", "unknown"),
    }


def write_campaign_evidence_report(
    *,
    campaign_id: str,
    payload: dict[str, Any],
    output_dir: str = "storage/status",
) -> Path:
    path = Path(output_dir) / f"profile-testbot-semi-auto-live-{campaign_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Profile testbot semi-auto live campaign {campaign_id}",
        "",
        f"- report_schema: `{payload.get('report_schema_version')}`",
        f"- runtime_sha: `{payload.get('runtime_sha')}`",
        f"- overall_status: **{payload.get('overall_status')}**",
        f"- contract_mode: **{payload.get('contract_mode')}**",
        f"- qualification_status: **{payload.get('qualification_status')}**",
        "",
        "## Evidence",
        "",
        "```json",
        json.dumps(payload, indent=2, ensure_ascii=False),
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
