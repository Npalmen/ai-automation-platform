"""P1 observe-only activation helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.production_pilot.config_snapshot import build_snapshot_record, compute_snapshot_hash
from app.production_pilot.constants import PILOT_TENANT_ID, PRODUCTION_PILOT_MARKER
from app.production_pilot.kill_switches import apply_p1_activation
from app.production_pilot.stages import stage_capabilities, validate_stage_transition


def build_p1_tenant_record(
    *,
    pilot_owner: str = "operator",
    mailbox: str = "",
    operator_approval_id: str | None = None,
    pre_activation_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if pre_activation_snapshot:
        current_stage = (
            (pre_activation_snapshot.get("payload") or {})
            .get("production_pilot", {})
            .get("activation_stage", "P0")
        )
        validate_stage_transition(str(current_stage), "P1")
    settings = apply_p1_activation()
    snapshot = build_snapshot_record(settings)
    pilot = dict(settings["production_pilot"])
    pilot.update(
        {
            "pilot_owner": pilot_owner,
            "mailbox": mailbox,
            "pilot_started_at": datetime.now(timezone.utc).isoformat(),
            "operator_approval_id": operator_approval_id,
            "pre_activation_snapshot_hash": (
                pre_activation_snapshot.get("snapshot_hash") if pre_activation_snapshot else None
            ),
            "activation_snapshot_hash": snapshot["snapshot_hash"],
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
        "activation_stage": "P1",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def validate_p1_tenant_record(record: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if record.get("tenant_id") != PILOT_TENANT_ID:
        failures.append("tenant_id must be TENANT_PRODUCTION_PILOT_01")
    settings = record.get("settings") or {}
    pilot = settings.get("production_pilot") or {}
    caps = stage_capabilities("P1")
    if pilot.get("activation_stage") != "P1":
        failures.append("activation_stage must be P1")
    if not settings.get("production_pilot_intake", {}).get("enabled"):
        failures.append("gmail intake must be enabled at P1")
    if (settings.get("scheduler") or {}).get("run_mode") not in {"manual", "paused"}:
        failures.append("scheduler must be manual or paused at P1")
    if (settings.get("automation") or {}).get("demo_mode"):
        failures.append("demo_mode must be false at P1 for intake")
    if (settings.get("automation") or {}).get("automatic_gmail_replies"):
        failures.append("automatic_gmail_replies must be false at P1")
    if not pilot.get("shadow_intake_enabled"):
        failures.append("shadow intake must be enabled at P1")
    if not pilot.get("shadow_matching_enabled"):
        failures.append("shadow matching must be enabled at P1")
    if pilot.get("shadow_promotion_enabled"):
        failures.append("shadow promotion must be disabled at P1")
    if caps["gmail_reply_budget"] != 0:
        failures.append("gmail reply budget must be 0 at P1")
    blocked = set(record.get("allowed_integrations") or []) & {"google_sheets", "monday", "visma"}
    if blocked:
        failures.append(f"blocked integrations configured: {sorted(blocked)}")
    return failures
