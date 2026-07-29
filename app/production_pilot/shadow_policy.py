"""Production pilot shadow policy helpers."""

from __future__ import annotations

from typing import Any

from app.production_pilot.gates import is_production_pilot_tenant
from app.production_pilot.stages import current_activation_stage, production_pilot_settings, stage_capabilities


def production_pilot_shadow_intake_allowed(tenant_id: str, tenant_settings: dict[str, Any] | None) -> bool:
    if not is_production_pilot_tenant(tenant_id) or not tenant_settings:
        return False
    caps = stage_capabilities(current_activation_stage(tenant_settings))
    pilot = production_pilot_settings(tenant_settings)
    return bool(caps["shadow_intake"] and pilot.get("shadow_intake_enabled"))


def production_pilot_shadow_matching_allowed(tenant_id: str, tenant_settings: dict[str, Any] | None) -> bool:
    if not is_production_pilot_tenant(tenant_id) or not tenant_settings:
        return False
    caps = stage_capabilities(current_activation_stage(tenant_settings))
    pilot = production_pilot_settings(tenant_settings)
    return bool(caps["shadow_matching"] and pilot.get("shadow_matching_enabled"))


def production_pilot_shadow_promotion_allowed(tenant_id: str, tenant_settings: dict[str, Any] | None) -> bool:
    if not is_production_pilot_tenant(tenant_id) or not tenant_settings:
        return False
    caps = stage_capabilities(current_activation_stage(tenant_settings))
    pilot = production_pilot_settings(tenant_settings)
    return bool(caps["shadow_promotion"] and pilot.get("shadow_promotion_enabled"))
