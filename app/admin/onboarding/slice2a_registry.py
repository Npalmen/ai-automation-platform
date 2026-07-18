"""Slice 2A static registry data for onboarding (presentation-safe)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.admin.onboarding.registries import PRODUCT_CAPABILITIES
from app.admin.onboarding.type_mapping import SERVICE_TYPE_LEAD_TYPE_MAP_VERSION, lead_type_for_service_type
from app.service_profiles.registry import get_profile, list_profiles

Availability = Literal["available", "read_only", "deferred"]

SETTINGS_SCHEMA_VERSION: int = 2

INTERNAL_ROUTING_DESTINATIONS: tuple[str, ...] = (
    "sales",
    "support",
    "invoice",
    "manual_review",
)

# Not selectable in onboarding slice 2A
_DEFERRED_SERVICE_TYPES = frozenset({"debt_collection_risk", "invoice_generic"})

_CAPABILITY_PROFILE_HINTS: dict[str, tuple[str, ...]] = {
    "lead_management": (
        "generic_lead",
        "ev_charger_installation",
        "solar_installation",
        "battery_storage",
        "electrical_panel",
        "building_project",
    ),
    "customer_inquiries": ("generic_support", "vvs_service", "electrical_fault", "inverter_support"),
    "quote_drafts": ("generic_lead", "building_project", "electrical_panel"),
    "followups": (),
    "invoice_handling": ("invoice_generic",),
}


@dataclass(frozen=True)
class DataStartModeDefinition:
    key: str
    label_sv: str
    description_sv: str
    availability: Availability
    supported_in_current_slice: bool
    recommended: bool = False


DATA_START_MODES: dict[str, DataStartModeDefinition] = {
    "new_incoming_only": DataStartModeDefinition(
        key="new_incoming_only",
        label_sv="Endast nya inkommande",
        description_sv="Ingen historikscan eller retroaktiv import vid aktivering.",
        availability="available",
        supported_in_current_slice=True,
        recommended=True,
    ),
    "limited_onboarding_import": DataStartModeDefinition(
        key="limited_onboarding_import",
        label_sv="Begränsad onboarding-import",
        description_sv="Kräver separat säkert importflöde (ej tillgängligt i slice 2A).",
        availability="deferred",
        supported_in_current_slice=False,
    ),
    "historical_scan_later": DataStartModeDefinition(
        key="historical_scan_later",
        label_sv="Historikscan senare",
        description_sv="Planeringsval — ingen aktiv import i slice 2A.",
        availability="deferred",
        supported_in_current_slice=False,
    ),
}


def profiles_for_onboarding() -> list:
    result = []
    for profile in list_profiles():
        if profile.service_type in _DEFERRED_SERVICE_TYPES:
            availability: Availability = "deferred"
            supported = False
        else:
            availability = "available"
            supported = True
        result.append(
            {
                "key": profile.service_type,
                "label": profile.follow_up_intro.split("—")[0].strip()[:40]
                if profile.follow_up_intro
                else profile.service_type.replace("_", " ").title(),
                "description": profile.reply_opener or profile.follow_up_intro or "",
                "category": profile.family,
                "supported_job_types": [lead_type_for_service_type(profile.service_type) or "unknown"],
                "required_fields_summary": list(profile.required_fields),
                "optional_fields_summary": list(profile.optional_fields),
                "default_route": profile.default_route,
                "availability": availability,
                "supported_in_current_slice": supported,
                "capability_dependencies": [
                    cap
                    for cap, hints in _CAPABILITY_PROFILE_HINTS.items()
                    if profile.service_type in hints
                ],
            }
        )
    # Fix labels from registry profile names
    for item in result:
        p = get_profile(item["key"])
        if p:
            item["label"] = item["key"].replace("_", " ").title()
            if p.reply_opener:
                item["description"] = p.reply_opener
    return sorted(result, key=lambda x: x["key"])


def lead_field_registry() -> list[dict[str, str]]:
    fields: dict[str, str] = {}
    for profile in list_profiles():
        if profile.service_type in _DEFERRED_SERVICE_TYPES:
            continue
        for field_key in (*profile.required_fields, *profile.optional_fields):
            label = profile.follow_up_questions.get(field_key, field_key.replace("_", " "))
            fields.setdefault(field_key, label)
    return [{"key": k, "label": fields[k]} for k in sorted(fields)]


def recommended_profiles_for_capabilities(capability_keys: list[str]) -> list[str]:
    keys: set[str] = set()
    for cap in capability_keys:
        keys.update(_CAPABILITY_PROFILE_HINTS.get(cap, ()))
    return sorted(keys)


def capability_needs_service_profile(capability_keys: list[str]) -> bool:
    return any(k in ("lead_management", "customer_inquiries", "quote_drafts") for k in capability_keys)
