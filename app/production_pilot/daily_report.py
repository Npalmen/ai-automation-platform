"""Daily operator report for production pilot."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.production_pilot.gates import build_activation_snapshot
from app.production_pilot.stages import current_activation_stage


def build_daily_pilot_report(
    *,
    tenant_id: str,
    settings: dict[str, Any] | None,
    runtime_sha: str | None,
    ops_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ops = ops_state or {}
    return {
        "report_schema_version": "production-pilot.daily-report.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tenant_id": tenant_id,
        "runtime_sha": runtime_sha,
        "activation_stage": current_activation_stage(settings),
        "activation_snapshot": build_activation_snapshot(tenant_id=tenant_id, settings=settings),
        "health": ops.get("health"),
        "scheduler_state": ops.get("scheduler"),
        "automation_state": ops.get("automation"),
        "integration_status": ops.get("integrations"),
        "jobs_by_status": ops.get("jobs_by_status"),
        "approvals_pending": ops.get("approvals_pending"),
        "needs_help_count": ops.get("needs_help_count"),
        "incidents_open": ops.get("incidents_open"),
        "feature_flags": ops.get("feature_flags"),
        "shadow_observations": ops.get("shadow_observations"),
        "match_proposals_awaiting_review": ops.get("match_proposals_awaiting_review"),
        "provider_failures": ops.get("provider_failures"),
        "duplicate_replay_blocks": ops.get("duplicate_replay_blocks"),
        "usage": ops.get("usage"),
        "redaction_status": "clean",
    }
