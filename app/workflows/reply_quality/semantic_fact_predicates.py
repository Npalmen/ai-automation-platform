"""Semantic fact predicates for coworker reply question selection."""

from __future__ import annotations

import re

# Maps extracted semantic fact ids to question fields they satisfy.
SEMANTIC_FACT_TO_FIELDS: dict[str, frozenset[str]] = {
    "location_city": frozenset(),
    "property_address": frozenset({"address"}),
    "property_type_villa": frozenset({"property_type", "housing_association_context"}),
    "property_type_private": frozenset({"property_type", "housing_association_context"}),
    "load_balancing_stated": frozenset({"load_balancing_need"}),
    "requested_service_explicit": frozenset({"requested_service"}),
    "consultation_solar_vs_battery": frozenset({"requested_service"}),
    "consultation_energy_storage": frozenset({"requested_service"}),
    "consultation_charger_vs_solar": frozenset({"requested_service"}),
    "consultation_booking": frozenset({"requested_service"}),
    "existing_solar_system": frozenset({"existing_solar_system", "existing_installation"}),
    "battery_retrofit": frozenset({"existing_solar_system", "existing_installation", "battery_interest"}),
    "solar_battery_combined_new": frozenset({"battery_interest", "requested_service"}),
    "attachment_missing": frozenset(),
    "attachment_missing_drawing": frozenset(),
    "attachment_claimed": frozenset({"attachment", "annual_consumption"}),
    "attachment_claimed_kwh": frozenset({"attachment", "annual_consumption"}),
    "attachment_present_kwh": frozenset({"annual_consumption"}),
}

_PRIVATE_PROPERTY_TOKENS = (
    "villa",
    "villan",
    "radhus",
    "privatbostad",
    "privat bostad",
    "detached house",
    "townhouse",
    "single-family",
)

_LOAD_BALANCING_TOKENS = (
    "med lastbalansering",
    "vill ha lastbalansering",
    "behöver lastbalansering",
    "need load balancing",
    "with load balancing",
    "load balancing",
)

_REQUESTED_SERVICE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"solceller\s+kontra\s+batteri", re.I), "consultation"),
    (re.compile(r"laddbox\s+eller\s+solceller", re.I), "consultation"),
    (re.compile(r"energy storage", re.I), "consultation"),
    (re.compile(r"solar,\s*battery\s+and\s+charging", re.I), "consultation"),
    (re.compile(r"short call about solar", re.I), "consultation"),
    (re.compile(r"book a short call", re.I), "consultation_booking"),
    (re.compile(r"solcellsoffert|solar quote", re.I), "solar"),
    (re.compile(r"\b(?:want|need|wants|looking for)\s+(?:a\s+)?solar\b", re.I), "solar"),
    (re.compile(r"\b(?:vill|önskar)\s+ha\s+solceller\b", re.I), "solar"),
    (re.compile(r"\b(?:installera|installation)\s+(?:av\s+)?solceller\b", re.I), "solar"),
    (re.compile(r"\bbatteri(?:lager|lagring)?\b", re.I), "battery"),
    (re.compile(r"\bladdbox\b|\bev charger\b", re.I), "ev_charger"),
)

_CONSULTATION_INTENT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"solceller\s+kontra\s+batteri", re.I), "consultation_solar_vs_battery"),
    (re.compile(r"overview of energy storage", re.I), "consultation_energy_storage"),
    (re.compile(r"energy storage options", re.I), "consultation_energy_storage"),
    (re.compile(r"laddbox\s+eller\s+solceller", re.I), "consultation_charger_vs_solar"),
    (re.compile(r"book a short call about solar", re.I), "consultation_booking"),
    (re.compile(r"short call about solar,\s*battery", re.I), "consultation_booking"),
)


def detect_consultation_intent(message: str) -> str | None:
    lowered = (message or "").lower()
    for pattern, intent in _CONSULTATION_INTENT_PATTERNS:
        if pattern.search(lowered):
            return intent
    return None


def detect_semantic_fact_ids(message: str) -> set[str]:
    """Return semantic fact ids inferred from customer text."""
    lowered = (message or "").lower()
    fact_ids: set[str] = set()

    if any(token in lowered for token in _PRIVATE_PROPERTY_TOKENS):
        fact_ids.add("property_type_villa")
        if any(token in lowered for token in ("privat", "private")):
            fact_ids.add("property_type_private")

    if any(token in lowered for token in _LOAD_BALANCING_TOKENS):
        fact_ids.add("load_balancing_stated")

    for pattern, _kind in _REQUESTED_SERVICE_PATTERNS:
        if pattern.search(lowered):
            fact_ids.add("requested_service_explicit")
            break

    consultation_intent = detect_consultation_intent(message)
    if consultation_intent:
        fact_ids.add(consultation_intent)

    has_existing_solar = bool(
        re.search(
            r"\b(?:vi har|we have|har)\s+solceller\b|befintlig(?:a)?\s+sol|existing solar",
            lowered,
            re.I,
        )
        or re.search(r"\b\d+\s*kwp\b", lowered, re.I)
    )
    wants_battery = bool(re.search(r"\bbatteri|battery(?:\s+storage)?\b", lowered, re.I))
    wants_new_solar = bool(
        re.search(
            r"\b(?:installera|vill ha|want|need)\s+.*\bsolceller\b|\bsolar quote\b|\bsolcellsoffert\b",
            lowered,
            re.I,
        )
        and not has_existing_solar
    )
    wants_combined_new = bool(
        re.search(r"installera\s+både\s+solceller\s+och\s+batteri", lowered, re.I)
        or re.search(r"solceller\s+tillsammans\s+med\s+batteri", lowered, re.I)
        or re.search(r"solar panels and battery", lowered, re.I)
        or re.search(r"\boffert\s+på\s+både\s+solceller\s+och\s+batteri\b", lowered, re.I)
        or (
            wants_battery
            and wants_new_solar
            and re.search(r"\b(?:både|tillsammans|and)\b", lowered, re.I)
        )
    )

    if has_existing_solar:
        fact_ids.add("existing_solar_system")
    if wants_combined_new and not has_existing_solar:
        fact_ids.add("solar_battery_combined_new")
    if has_existing_solar and wants_battery and not wants_new_solar:
        fact_ids.add("battery_retrofit")

    if re.search(r"\b\d{4,5}\s*kwh\b", lowered):
        if any(token in lowered for token in ("bifogar", "bifogade", "attached", "attach")):
            fact_ids.add("attachment_claimed_kwh")
            fact_ids.add("attachment_present_kwh")
        else:
            fact_ids.add("annual_consumption")

    if "saknas" in lowered or "saknar" in lowered or "not attached" in lowered or "inte bifogat" in lowered:
        if any(token in lowered for token in ("ritning", "drawing", "roof", "elritning", "elschema")):
            fact_ids.add("attachment_missing_drawing")
        fact_ids.add("attachment_missing")

    if re.search(r"\bskickar den\b|\bskickar ritning|\bsending (?:the|it)\b", lowered):
        fact_ids.add("attachment_promised")

    if any(token in lowered for token in ("bifogar", "bifogade", "attached", "attach", "bifoga", "skickar den")):
        if any(
            token in lowered
            for token in ("senare", "later", "så snart", "soon", "hemma", "strax", "nästa mail", "nästa meddelande")
        ):
            fact_ids.add("attachment_promised")
        elif "saknar" in lowered or "saknas" in lowered or "not attached" in lowered or "inte bifogat" in lowered:
            if any(token in lowered for token in ("ritning", "drawing", "roof", "elritning", "elschema")):
                fact_ids.add("attachment_missing_drawing")
            fact_ids.add("attachment_missing")
        elif "årsförbrukning" in lowered or re.search(r"\b\d{4,5}\s*kwh\b", lowered):
            fact_ids.add("attachment_claimed_kwh")
            fact_ids.add("attachment_claimed")
        else:
            fact_ids.add("attachment_claimed")

    if re.search(r"\b\d{1,4}\b.*\b(gatan|vägen|street)\b", lowered, re.I) or re.search(
        r"\bstorgatan\b", lowered, re.I
    ):
        fact_ids.add("property_address")

    if re.search(r"\b(?:i|in)\s+[a-zåäöé]+(?:\s+[a-zåäöé]+)?\s*$", lowered) and not fact_ids.intersection(
        {"property_address"}
    ):
        pass  # city-only handled separately via extract_city_phrase

    return fact_ids


def semantic_known_question_fields(fact_ids: set[str]) -> set[str]:
    fields: set[str] = set()
    for fact_id in fact_ids:
        fields.update(SEMANTIC_FACT_TO_FIELDS.get(fact_id, frozenset()))
    return fields


def is_battery_retrofit_intent(message: str) -> bool:
    return "battery_retrofit" in detect_semantic_fact_ids(message)


def is_combined_new_install_intent(message: str) -> bool:
    return "solar_battery_combined_new" in detect_semantic_fact_ids(message)


def attachment_state(message: str) -> str | None:
    fact_ids = detect_semantic_fact_ids(message)
    if "attachment_promised" in fact_ids:
        return "attachment_promised"
    if "attachment_present_kwh" in fact_ids:
        return "attachment_present_kwh"
    if "attachment_claimed_kwh" in fact_ids:
        return "attachment_claimed_kwh"
    if "attachment_missing_drawing" in fact_ids:
        return "attachment_missing_drawing"
    if "attachment_missing" in fact_ids:
        return "attachment_missing"
    if "attachment_claimed" in fact_ids:
        return "attachment_claimed"
    return None


def existing_solar_verified(fact_ids: set[str], extracted_known: set[str]) -> bool:
    return bool(
        fact_ids.intersection({"existing_solar_system", "battery_retrofit"})
        or "existing_solar_system" in extracted_known
        or "existing_installation" in extracted_known
    )
