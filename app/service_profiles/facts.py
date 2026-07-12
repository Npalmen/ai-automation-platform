"""Fact state detection for service profile fields.

A fact can be more than just present/missing.  Customers often mention
a field keyword but state they don't know its value — which is very different
from not mentioning the field at all, and should produce a *soft* follow-up
question rather than omitting it.

Public API:
    FactState          — enum: confirmed / unknown / uncertain / partial / missing
    detect_fact_state  — detect state of a specific field in message text
    detect_all_facts   — detect states for all fields of a profile
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any


class FactState(str, Enum):
    CONFIRMED = "confirmed"   # Customer clearly provided the information
    UNKNOWN = "unknown"       # Customer explicitly said they don't know
    UNCERTAIN = "uncertain"   # Customer gave an approximate/unsure value
    PARTIAL = "partial"       # Some related context provided, key detail missing
    MISSING = "missing"       # Not mentioned at all


# ── Negation / unknown phrase patterns ──────────────────────────────────────

# Phrases that indicate the customer does NOT know the field value.
_UNKNOWN_PHRASES: list[str] = [
    "vet inte",
    "vet ej",
    "har ingen aning",
    "ingen aning",
    "osäker",
    "osäker på",
    "känner inte till",
    "okänt",
    "inte koll",
    "har inte koll",
    "kan inte svara",
    "vet inte vilken",
    "vet inte vad",
    "vet inte hur",
    "vet inte modell",
    "osäker på modell",
    "vet inte märket",
]

# Phrases that indicate the customer is guessing / approximating.
_UNCERTAIN_PHRASES: list[str] = [
    "tror att",
    "tror det är",
    "ungefär",
    "ca ",
    "runt ",
    "kanske",
    "möjligen",
    "förmodligen",
    "troligtvis",
    "inte helt säker",
    "kan vara",
]

# ── Per-field keywords used to detect proximity of negation ─────────────────

_FIELD_CONTEXT_KEYWORDS: dict[str, list[str]] = {
    "main_fuse": [
        "huvudsäkring", "säkring", "ampere", "ampere", "elcentral",
    ],
    "desired_location": [
        "placering", "plats", "var", "parkeringsplats", "garage", "carport",
    ],
    "charger_preference": [
        "laddbox", "märke", "modell", "zaptec", "easee", "wallbox",
    ],
    "inverter_brand_model": [
        "växelriktare", "inverter", "modell", "märke",
    ],
    "backup_requirement": [
        "backup", "strömavbrott", "reservkraft",
    ],
    "existing_solar_size": [
        "kwp", "solcell", "anläggning", "paneler",
    ],
    "roof_type": [
        "tak", "taktyp", "taket",
    ],
    "property_type": [
        "fastighet", "villa", "hus", "lägenhet", "brf",
    ],
    "error_code": [
        "felkod", "larm", "lampa", "display", "app",
    ],
}


def _proximity_match(text: str, phrase: str, keywords: list[str], window: int = 120) -> bool:
    """Return True if *phrase* appears within *window* chars of any *keywords* in *text*."""
    lower = text.lower()
    pos_p = lower.find(phrase)
    if pos_p < 0:
        return False
    for kw in keywords:
        pos_k = lower.find(kw)
        if pos_k >= 0 and abs(pos_p - pos_k) <= window:
            return True
    return False


def detect_fact_state(
    field: str,
    text: str,
    entities: dict[str, Any] | None = None,
) -> FactState:
    """Return the FactState for *field* given raw message *text*.

    Priority:
      1. CONFIRMED — field value detected in text or entities (checked first to
                     avoid false UNKNOWN when an unrelated "vet inte" is nearby)
      2. UNKNOWN   — customer explicitly said they don't know the field
      3. UNCERTAIN — customer gave an approximate value
      4. PARTIAL   — related keyword present but key detail missing
      5. MISSING   — field not mentioned at all
    """
    from app.service_profiles.qualification import _profile_field_present

    entities = entities or {}
    lower = text.lower()
    field_kws = _FIELD_CONTEXT_KEYWORDS.get(field, [])

    # ── Step 1: CONFIRMED — check first to avoid false UNKNOWN classifications ─
    # If the field value is clearly present in the text, it's CONFIRMED regardless
    # of other phrases in the message ("villa" near "vet inte" about main_fuse).
    if _profile_field_present(field, text, entities):
        return FactState.CONFIRMED

    # ── Step 2: UNKNOWN — customer explicitly said they don't know ───────────
    # Only mark UNKNOWN when an unknown phrase appears CLOSE to a field keyword.
    # "vet inte vad jag har för huvudsäkring" → main_fuse UNKNOWN (within 120 chars)
    # "vet inte" about main_fuse should NOT affect property_type.
    for phrase in _UNKNOWN_PHRASES:
        if phrase not in lower:
            continue
        if not field_kws:
            continue  # No keywords to check proximity against — skip
        # Field keyword must appear within window chars of the unknown phrase
        if _proximity_match(lower, phrase, field_kws, window=120):
            return FactState.UNKNOWN

    # ── Step 3: UNCERTAIN — customer gave approximate/unsure value ───────────
    for phrase in _UNCERTAIN_PHRASES:
        if phrase in lower and field_kws:
            if _proximity_match(lower, phrase, field_kws, window=120):
                return FactState.UNCERTAIN

    # ── Step 4: PARTIAL — related keyword present but field not confirmed ─────
    if field_kws and any(kw in lower for kw in field_kws):
        return FactState.PARTIAL

    # ── Step 5: MISSING ───────────────────────────────────────────────────────
    return FactState.MISSING


def detect_all_facts(
    fields: list[str],
    text: str,
    entities: dict[str, Any] | None = None,
) -> dict[str, FactState]:
    """Return a mapping of field → FactState for all *fields*."""
    return {field: detect_fact_state(field, text, entities) for field in fields}


def should_ask_field(state: FactState) -> bool:
    """Return True if this fact state means the field should be asked about."""
    return state in (FactState.UNKNOWN, FactState.UNCERTAIN, FactState.PARTIAL, FactState.MISSING)


def is_known(state: FactState) -> bool:
    """Return True if the customer has provided useful information about this field."""
    return state == FactState.CONFIRMED


def soft_question_prefix(state: FactState) -> str:
    """Return a soft prefix for unknown/uncertain fields."""
    if state == FactState.UNKNOWN:
        return "Om du skulle kunna ta reda på det — "
    if state == FactState.UNCERTAIN:
        return "Ungefär "
    return ""
