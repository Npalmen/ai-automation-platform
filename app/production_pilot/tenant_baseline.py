"""P0 baseline tenant configuration for production pilot."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.production_pilot.config_snapshot import build_snapshot_record, compute_snapshot_hash
from app.production_pilot.constants import PILOT_TENANT_ID, PRODUCTION_PILOT_MARKER
from app.production_pilot.kill_switches import apply_p0_baseline


def build_p0_tenant_record(
    *,
    pilot_owner: str = "operator",
    mailbox: str = "",
    operator_approval_id: str | None = None,
) -> dict[str, Any]:
    settings = apply_p0_baseline()
    snapshot = build_snapshot_record(settings)
    pilot = dict(settings["production_pilot"])
    pilot.update(
        {
            "pilot_owner": pilot_owner,
            "mailbox": mailbox,
            "pilot_started_at": None,
            "operator_approval_id": operator_approval_id,
            "baseline_snapshot_hash": snapshot["snapshot_hash"],
            "config_snapshot": snapshot,
        }
    )
    settings["production_pilot"] = pilot
    return {
        "tenant_id": PILOT_TENANT_ID,
        "name": "Production Pilot 01",
        "slug": "production-pilot-01",
        "status": "pilot",
        "enabled_job_types": ["lead", "customer_inquiry", "invoice", "unknown"],
        "allowed_integrations": ["google_mail"],
        "auto_actions": {},
        "settings": settings,
        "marker": PRODUCTION_PILOT_MARKER,
        "config_hash": compute_snapshot_hash(settings),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def validate_pilot_tenant_record(record: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if record.get("tenant_id") != PILOT_TENANT_ID:
        failures.append("tenant_id must be TENANT_PRODUCTION_PILOT_01")
    settings = record.get("settings") or {}
    pilot = settings.get("production_pilot") or {}
    if pilot.get("activation_stage") != "P0":
        failures.append("activation_stage must be P0")
    if settings.get("production_pilot_intake", {}).get("enabled"):
        failures.append("gmail intake must be disabled at P0")
    if (settings.get("scheduler") or {}).get("run_mode") != "paused":
        failures.append("scheduler must be paused at P0")
    if not (settings.get("automation") or {}).get("demo_mode"):
        failures.append("demo_mode must be true at P0")
    blocked = set(record.get("allowed_integrations") or []) & {"google_sheets", "monday", "visma"}
    if blocked:
        failures.append(f"blocked integrations configured: {sorted(blocked)}")
    return failures
