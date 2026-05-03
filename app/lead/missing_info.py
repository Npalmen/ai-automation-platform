"""Missing Info Engine.

Defines required/optional field schemas per lead_type and computes
a completeness_score (0–1) by checking extracted entities + input_data.
"""
from __future__ import annotations

import re
from typing import Any

from app.lead.models import LeadType, MissingInfoResult


# ── field schemas per lead_type ───────────────────────────────────────────────

_SCHEMAS: dict[str, dict[str, list[str]]] = {
    "solar_installation": {
        "required": ["address", "roof_type", "annual_consumption", "installation_timeline"],
        "optional": ["battery_interest", "roof_angle", "current_electricity_cost"],
    },
    "battery_storage": {
        "required": ["address", "installation_timeline", "solar_exists"],
        "optional": ["battery_capacity_preference", "current_electricity_cost"],
    },
    "ev_charger": {
        "required": ["address", "property_type", "charger_count", "main_fuse", "installation_timeline"],
        "optional": ["preferred_brand", "parking_type"],
    },
    "electrical_work": {
        "required": ["address", "work_description", "installation_timeline"],
        "optional": ["property_type", "current_panel_age"],
    },
    "roof_painting": {
        "required": ["address", "roof_material", "approximate_area", "installation_timeline"],
        "optional": ["roof_condition", "preferred_color"],
    },
    "roof_cleaning": {
        "required": ["address", "roof_material", "approximate_area", "roof_condition", "installation_timeline"],
        "optional": ["moss_level", "previous_cleaning"],
    },
    "unknown": {
        "required": ["address", "work_description"],
        "optional": [],
    },
}

# ── keyword probes for each logical field ────────────────────────────────────
# Each field is present if any keyword is found in the combined text, OR if
# a matching entity is non-empty.

_FIELD_KEYWORDS: dict[str, list[str]] = {
    "address": [],          # covered by entity extraction (entities.address)
    "roof_type": [
        "betong", "tegelpannor", "plåt", "shingel", "eternit",
        "trätak", "glas", "platt tak", "sadel",
    ],
    "annual_consumption": [
        "kwh", "årsförbrukning", "elförbrukning", "kilowatt",
        "kw/h", "förbrukning",
    ],
    "installation_timeline": [
        "när", "tidplan", "månad", "kvartal", "vecka", "datum",
        "snart", "nästa år", "i år",
    ],
    "battery_interest": [
        "batteri", "batterilager", "lagra",
    ],
    "roof_angle": [
        "vinkel", "lutning", "grader", "°",
    ],
    "current_electricity_cost": [
        "elkostnad", "elpris", "elräkning", "kr/kwh",
    ],
    "solar_exists": [
        "solcell", "solpanel", "befintlig solar", "har solar",
    ],
    "battery_capacity_preference": [
        "kwh batteri", "kapacitet", "antal kwh",
    ],
    "property_type": [
        "villa", "radhus", "lägenhet", "brf", "fastighet",
        "hus", "kontor", "lokal", "garage",
    ],
    "charger_count": [
        "laddbox", "antal", "en laddbox", "två laddbox",
        "laddpunkt",
    ],
    "main_fuse": [
        "huvudsäkring", "säkring", "ampere", "amp", "16a", "20a",
        "25a", "35a", "63a",
    ],
    "work_description": [],  # covered by message length / requested_service entity
    "current_panel_age": [
        "gammal", "år gammal", "elcentral", "ålder",
    ],
    "roof_material": [
        "betong", "tegel", "plåt", "shingel", "eternit", "glas",
    ],
    "approximate_area": [
        "kvm", "m²", "kvadrat", "area", "storlek", "yta",
    ],
    "roof_condition": [
        "skick", "mossa", "alger", "lav", "spricka", "skadad",
        "sliten", "ny",
    ],
    "preferred_color": [
        "färg", "kulör", "röd", "svart", "grön", "grå",
    ],
    "moss_level": [
        "mycket mossa", "lite mossa", "kraftig mossa",
    ],
    "previous_cleaning": [
        "tidigare tvättad", "senast tvättad", "har tvättat",
    ],
    "preferred_brand": [
        "zaptec", "easee", "garo", "schneider", "abb", "wallbox",
    ],
    "parking_type": [
        "garage", "carport", "utomhus", "parkeringsplats",
    ],
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _combined_text(input_data: dict) -> str:
    subject = (input_data.get("subject") or "").lower()
    body = (input_data.get("message_text") or "").lower()
    return f"{subject} {body}"


def _field_present(field: str, text: str, entities: dict[str, Any]) -> bool:
    # Entity-backed fields
    if field == "address":
        return bool(entities.get("address") or entities.get("city"))
    if field == "work_description":
        requested = entities.get("requested_service") or ""
        body = input_data_body_from_text(text)
        return bool(requested) or len(body) >= 30

    keywords = _FIELD_KEYWORDS.get(field, [])
    if not keywords:
        return False
    return any(re.search(r"\b" + re.escape(kw) + r"\b", text) for kw in keywords)


def input_data_body_from_text(text: str) -> str:
    """Strip the leading subject portion (first line) from combined text."""
    parts = text.split("\n", 1)
    return parts[1].strip() if len(parts) > 1 else text.strip()


# ── public API ────────────────────────────────────────────────────────────────

def compute_missing_info(
    lead_type: LeadType,
    input_data: dict,
    entities: dict | None = None,
) -> MissingInfoResult:
    """Compute which fields are present/missing and a completeness_score."""
    entities = entities or {}
    text = _combined_text(input_data)

    schema = _SCHEMAS.get(lead_type, _SCHEMAS["unknown"])
    required: list[str] = schema["required"]
    optional: list[str] = schema["optional"]

    present: list[str] = []
    missing: list[str] = []

    for field in required:
        if _field_present(field, text, entities):
            present.append(field)
        else:
            missing.append(field)

    # Also check optional fields so UI can show what's known
    for field in optional:
        if _field_present(field, text, entities):
            present.append(field)

    completeness = len(present) / len(required) if required else 1.0
    completeness = min(completeness, 1.0)

    return MissingInfoResult(
        required_fields=required,
        present_fields=present,
        missing_fields=missing,
        optional_fields=optional,
        completeness_score=completeness,
    )
