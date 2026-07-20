"""Canonical integration keys and legacy alias normalization."""

from __future__ import annotations

from typing import Final

CANONICAL_INTEGRATION_KEYS: Final[frozenset[str]] = frozenset(
    {
        "google_mail",
        "microsoft_mail",
        "visma",
        "fortnox",
        "google_sheets",
        "monday",
        "google_calendar",
        "microsoft_calendar",
    }
)

LEGACY_KEY_ALIASES: Final[dict[str, str]] = {
    "gmail": "google_mail",
}

DISPLAY_NAME_SV: Final[dict[str, str]] = {
    "google_mail": "Gmail",
    "microsoft_mail": "Microsoft 365",
    "visma": "Visma",
    "fortnox": "Fortnox",
    "google_sheets": "Google Sheets",
    "monday": "Monday",
    "google_calendar": "Google Calendar",
    "microsoft_calendar": "Microsoft Calendar",
}

# Systems evaluated by tenant integration health in Slice A.
TENANT_HEALTH_INTEGRATION_KEYS: Final[tuple[str, ...]] = (
    "google_mail",
    "monday",
    "fortnox",
)


def normalize_integration_key(raw: str | None) -> str | None:
    """Return canonical integration key or None when unknown."""
    if not raw:
        return None
    key = str(raw).strip().lower()
    if not key:
        return None
    key = LEGACY_KEY_ALIASES.get(key, key)
    if key not in CANONICAL_INTEGRATION_KEYS:
        return None
    return key


def normalize_integration_key_list(values: list[str] | None) -> list[str]:
    out: list[str] = []
    for raw in values or []:
        canonical = normalize_integration_key(raw)
        if canonical and canonical not in out:
            out.append(canonical)
    return out


def display_name_sv(integration_key: str) -> str:
    canonical = normalize_integration_key(integration_key) or integration_key
    return DISPLAY_NAME_SV.get(canonical, canonical.replace("_", " ").title())
