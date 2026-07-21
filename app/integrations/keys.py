"""Canonical integration keys and legacy alias normalization."""

from __future__ import annotations

from typing import Final, Literal

SupportStatus = Literal["available", "limited", "coming_later", "legacy_only"]
IntegrationCategory = Literal[
    "email",
    "finance",
    "work_management",
    "spreadsheet_export",
    "calendar",
]

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
        "bokio",
    }
)

LEGACY_KEY_ALIASES: Final[dict[str, str]] = {
    "gmail": "google_mail",
    "sheets": "google_sheets",
}

REGISTRY_TO_CANONICAL: Final[dict[str, str]] = {
    "gmail": "google_mail",
    "google_sheets": "google_sheets",
    "monday": "monday",
    "visma": "visma",
    "fortnox": "fortnox",
}

DISPLAY_NAME_SV: Final[dict[str, str]] = {
    "google_mail": "Gmail",
    "microsoft_mail": "Microsoft 365",
    "visma": "Visma",
    "fortnox": "Fortnox",
    "bokio": "Bokio",
    "google_sheets": "Google Kalkylark",
    "monday": "Monday",
    "google_calendar": "Google Kalender",
    "microsoft_calendar": "Microsoft Kalender",
}

INTEGRATION_REGISTRY: Final[dict[str, dict[str, str | tuple[str, ...] | bool]]] = {
    "google_mail": {
        "display_name_sv": "Gmail",
        "category": "email",
        "alternatives_group": "email_system",
        "support_status": "available",
        "selectable": True,
        "registry_key": "gmail",
    },
    "microsoft_mail": {
        "display_name_sv": "Microsoft 365",
        "category": "email",
        "alternatives_group": "email_system",
        "support_status": "coming_later",
        "selectable": False,
        "registry_key": "microsoft_mail",
    },
    "visma": {
        "display_name_sv": "Visma",
        "category": "finance",
        "alternatives_group": "finance_destination",
        "support_status": "available",
        "selectable": True,
        "registry_key": "visma",
    },
    "fortnox": {
        "display_name_sv": "Fortnox",
        "category": "finance",
        "alternatives_group": "finance_destination",
        "support_status": "coming_later",
        "selectable": False,
        "registry_key": "fortnox",
    },
    "bokio": {
        "display_name_sv": "Bokio",
        "category": "finance",
        "alternatives_group": "finance_destination",
        "support_status": "coming_later",
        "selectable": False,
        "registry_key": "bokio",
    },
    "monday": {
        "display_name_sv": "Monday",
        "category": "work_management",
        "alternatives_group": "work_management",
        "support_status": "available",
        "selectable": True,
        "registry_key": "monday",
    },
    "google_sheets": {
        "display_name_sv": "Google Kalkylark",
        "category": "spreadsheet_export",
        "alternatives_group": "spreadsheet_export",
        "support_status": "available",
        "selectable": True,
        "registry_key": "google_sheets",
    },
    "google_calendar": {
        "display_name_sv": "Google Kalender",
        "category": "calendar",
        "alternatives_group": "calendar_system",
        "support_status": "coming_later",
        "selectable": False,
        "registry_key": "google_calendar",
    },
    "microsoft_calendar": {
        "display_name_sv": "Microsoft Kalender",
        "category": "calendar",
        "alternatives_group": "calendar_system",
        "support_status": "coming_later",
        "selectable": False,
        "registry_key": "microsoft_calendar",
    },
}

ALTERNATIVES_GROUPS: Final[dict[str, dict[str, str]]] = {
    "email_system": {"label_sv": "E-post"},
    "finance_destination": {"label_sv": "Ekonomi"},
    "work_management": {"label_sv": "Arbetsledning och export"},
    "spreadsheet_export": {"label_sv": "Kalkylark/export"},
    "calendar_system": {"label_sv": "Kalender"},
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


def registry_key_to_canonical(raw: str | None) -> str | None:
    if not raw:
        return None
    mapped = REGISTRY_TO_CANONICAL.get(str(raw).strip().lower())
    if mapped:
        return mapped
    return normalize_integration_key(raw)


def normalize_integration_key_list(values: list[str] | None) -> list[str]:
    out: list[str] = []
    for raw in values or []:
        canonical = normalize_integration_key(raw)
        if canonical and canonical not in out:
            out.append(canonical)
    return out


def validate_unique_canonical_keys(keys: list[str]) -> None:
    canonical = normalize_integration_key_list(keys)
    if len(canonical) != len(set(canonical)):
        raise ValueError("Duplicate canonical integration keys")
    raw_lower = [str(k).strip().lower() for k in keys]
    for alias, target in LEGACY_KEY_ALIASES.items():
        if alias in raw_lower and target in canonical:
            raise ValueError(f"Conflicting alias keys: {alias} and {target}")


def display_name_sv(integration_key: str) -> str:
    canonical = normalize_integration_key(integration_key) or integration_key
    return DISPLAY_NAME_SV.get(canonical, canonical.replace("_", " ").title())
