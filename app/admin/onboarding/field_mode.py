"""Field mode resolution for service profile lead requirements (Onboarding 2.0)."""

from __future__ import annotations

from typing import Literal

FieldOverrideMode = Literal["inherit", "required", "optional", "skip"]
EffectiveFieldMode = Literal["required", "optional", "skip"]

MODE_LABELS_SV: dict[str, str] = {
    "inherit": "Automatiskt",
    "required": "Obligatorisk",
    "optional": "Valfri",
    "skip": "Fråga inte",
}

EFFECTIVE_LABELS_SV: dict[str, str] = {
    "required": "Obligatorisk",
    "optional": "Valfri",
    "skip": "Fråga inte",
}


def platform_default_mode(field_key: str, profile) -> EffectiveFieldMode:
    if field_key in profile.required_fields:
        return "required"
    return "optional"


def resolve_field_mode(
    *,
    field_key: str,
    profile,
    override: str | None,
) -> dict[str, str]:
    """
    Resolve override → effective mode with Swedish presentation labels.

    Only non-inherit overrides are persisted in tenant settings.
    """
    raw = (override or "inherit").strip()
    if raw not in ("inherit", "required", "optional", "skip"):
        raw = "inherit"
    platform_default = platform_default_mode(field_key, profile)
    if raw == "inherit":
        effective: EffectiveFieldMode = platform_default
        source = "automatic"
    else:
        effective = raw  # type: ignore[assignment]
        source = "tenant_override"
    return {
        "override": raw,
        "effective": effective,
        "source": source,
        "override_label_sv": MODE_LABELS_SV.get(raw, raw),
        "effective_label_sv": EFFECTIVE_LABELS_SV.get(effective, effective),
        "platform_default": platform_default,
    }
