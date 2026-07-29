"""Kill switch settings patches for production pilot."""

from __future__ import annotations

from typing import Any

from app.production_pilot.constants import DEFAULT_ACTIVATION_STAGE, PRODUCTION_PILOT_MARKER


def _pilot_blob(settings: dict[str, Any] | None) -> dict[str, Any]:
    return dict((settings or {}).get("production_pilot") or {})


def pause_tenant_automation(settings: dict[str, Any] | None) -> dict[str, Any]:
    updated = dict(settings or {})
    automation = dict(updated.get("automation") or {})
    automation["demo_mode"] = True
    automation["automatic_gmail_replies"] = False
    updated["automation"] = automation
    operations = dict(updated.get("operations") or {})
    operations["paused"] = True
    updated["operations"] = operations
    return updated


def disable_scheduler(settings: dict[str, Any] | None) -> dict[str, Any]:
    updated = dict(settings or {})
    scheduler = dict(updated.get("scheduler") or {})
    scheduler["run_mode"] = "paused"
    updated["scheduler"] = scheduler
    return updated


def disable_gmail_replies(settings: dict[str, Any] | None) -> dict[str, Any]:
    updated = pause_tenant_automation(settings)
    automation = dict(updated.get("automation") or {})
    automation["automatic_gmail_replies"] = False
    updated["automation"] = automation
    pilot = _pilot_blob(updated)
    pilot["gmail_reply_kill_switch"] = True
    updated["production_pilot"] = pilot
    return updated


def disable_shadow_intake(settings: dict[str, Any] | None) -> dict[str, Any]:
    updated = dict(settings or {})
    pilot = _pilot_blob(updated)
    pilot["shadow_intake_enabled"] = False
    updated["production_pilot"] = pilot
    return updated


def disable_shadow_matching(settings: dict[str, Any] | None) -> dict[str, Any]:
    updated = dict(settings or {})
    pilot = _pilot_blob(updated)
    pilot["shadow_matching_enabled"] = False
    updated["production_pilot"] = pilot
    return updated


def disable_shadow_promotion(settings: dict[str, Any] | None) -> dict[str, Any]:
    updated = dict(settings or {})
    pilot = _pilot_blob(updated)
    pilot["shadow_promotion_enabled"] = False
    updated["production_pilot"] = pilot
    return updated


def disable_gmail_intake(settings: dict[str, Any] | None) -> dict[str, Any]:
    updated = dict(settings or {})
    intake = dict(updated.get("production_pilot_intake") or {})
    intake["enabled"] = False
    updated["production_pilot_intake"] = intake
    return updated


def enable_read_only_operator_mode(settings: dict[str, Any] | None) -> dict[str, Any]:
    updated = pause_tenant_automation(settings)
    updated = disable_scheduler(updated)
    updated = disable_gmail_intake(updated)
    pilot = _pilot_blob(updated)
    pilot["operator_read_only"] = True
    updated["production_pilot"] = pilot
    return updated


def apply_p0_baseline(settings: dict[str, Any] | None = None) -> dict[str, Any]:
    updated = dict(settings or {})
    pilot = {
        "marker": PRODUCTION_PILOT_MARKER,
        "activation_stage": DEFAULT_ACTIVATION_STAGE,
        "pilot_status": "release_ready",
        "shadow_intake_enabled": False,
        "shadow_matching_enabled": False,
        "shadow_promotion_enabled": False,
        "gmail_reply_kill_switch": True,
        "operator_read_only": False,
        "write_budgets": {
            "gmail_replies": 0,
            "non_gmail_writes": 0,
            "inbound_reads": 0,
        },
        "audit_reason": "production_pilot_p0_baseline",
    }
    updated["production_pilot"] = pilot
    updated["production_pilot_intake"] = {"enabled": False}
    updated["scheduler"] = {"run_mode": "paused"}
    updated["automation"] = {"demo_mode": True, "automatic_gmail_replies": False}
    updated["operations"] = {"paused": True}
    updated["allowed_integrations"] = ["google_mail"]
    updated["auto_actions"] = {}
    return updated


KILL_SWITCH_ACTIONS = {
    "pause_tenant_automation": pause_tenant_automation,
    "disable_scheduler": disable_scheduler,
    "disable_gmail_replies": disable_gmail_replies,
    "disable_shadow_intake": disable_shadow_intake,
    "disable_shadow_matching": disable_shadow_matching,
    "disable_shadow_promotion": disable_shadow_promotion,
    "disable_gmail_intake": disable_gmail_intake,
    "enable_read_only_operator_mode": enable_read_only_operator_mode,
}
