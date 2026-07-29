"""Feature-flag and tenant allowlist gates for shadow pipeline."""

from __future__ import annotations

from app.core.settings import get_settings
from app.production_pilot.shadow_policy import (
    production_pilot_shadow_intake_allowed,
    production_pilot_shadow_matching_allowed,
    production_pilot_shadow_promotion_allowed,
)


class ShadowGateError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _allowlist() -> set[str]:
    raw = get_settings().END_CUSTOMER_SHADOW_TENANT_ALLOWLIST.strip()
    if not raw:
        return set()
    return {item.strip() for item in raw.split(",") if item.strip()}


def assert_shadow_intake_allowed(tenant_id: str, tenant_settings: dict | None = None) -> None:
    if production_pilot_shadow_intake_allowed(tenant_id, tenant_settings):
        return
    settings = get_settings()
    if not settings.END_CUSTOMER_SHADOW_INTAKE_ENABLED:
        raise ShadowGateError("SHADOW_INTAKE_DISABLED", "Shadow intake is disabled")
    allowlist = _allowlist()
    if allowlist and tenant_id not in allowlist:
        raise ShadowGateError("SHADOW_TENANT_NOT_ALLOWED", f"Tenant {tenant_id} not in shadow allowlist")


def assert_shadow_matching_allowed(tenant_id: str, tenant_settings: dict | None = None) -> None:
    if production_pilot_shadow_matching_allowed(tenant_id, tenant_settings):
        return
    settings = get_settings()
    if not settings.END_CUSTOMER_SHADOW_MATCHING_ENABLED:
        raise ShadowGateError("SHADOW_MATCHING_DISABLED", "Shadow matching is disabled")
    allowlist = _allowlist()
    if allowlist and tenant_id not in allowlist:
        raise ShadowGateError("SHADOW_TENANT_NOT_ALLOWED", f"Tenant {tenant_id} not in shadow allowlist")


def assert_shadow_promotion_allowed(tenant_id: str, tenant_settings: dict | None = None) -> None:
    if production_pilot_shadow_promotion_allowed(tenant_id, tenant_settings):
        return
    settings = get_settings()
    if not settings.END_CUSTOMER_SHADOW_PROMOTION_ENABLED:
        raise ShadowGateError("SHADOW_PROMOTION_DISABLED", "Shadow promotion is disabled")
    allowlist = _allowlist()
    if allowlist and tenant_id not in allowlist:
        raise ShadowGateError("SHADOW_TENANT_NOT_ALLOWED", f"Tenant {tenant_id} not in shadow allowlist")


def shadow_flags_default_false() -> bool:
    settings = get_settings()
    return not any(
        (
            settings.END_CUSTOMER_SHADOW_INTAKE_ENABLED,
            settings.END_CUSTOMER_SHADOW_MATCHING_ENABLED,
            settings.END_CUSTOMER_SHADOW_PROMOTION_ENABLED,
        )
    )
