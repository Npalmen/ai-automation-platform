"""Safe customer-message fact extraction for reply planning."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.workflows.reply_quality.customer_surface import (
    extract_case_reference,
    extract_city_phrase,
    extract_discovery_time_phrase,
)

POLICY_VERSION = "coworker_fact_extraction_v1"

# Semantic aliases: extracted fact id -> question fields it satisfies.
FACT_TO_QUESTION_FIELDS: dict[str, frozenset[str]] = {
    "location_city": frozenset(),  # city alone does not satisfy full address
    "property_address": frozenset({"address"}),
    "system_type_solar": frozenset({"system_type"}),
    "system_type_ev_charger": frozenset({"system_type"}),
    "symptom_poor_performance": frozenset({"symptom"}),
    "when_started_yesterday": frozenset({"when_started"}),
    "when_started_last_week": frozenset({"when_started"}),
    "property_type_villa": frozenset({"property_type"}),
    "existing_solar_system": frozenset({"existing_solar_system", "existing_installation"}),
    "annual_consumption": frozenset({"annual_consumption"}),
    "case_reference_valid": frozenset({"case_reference", "status_dimension"}),
    "status_requested": frozenset({"status_dimension"}),
    "discovery_time": frozenset({"discovery_time"}),
    "attachment_missing": frozenset({"attachment"}),
    "battery_interest": frozenset({"battery_interest"}),
}

INVALID_CASE_REFERENCES = frozenset({"0", "00", "000"})


@dataclass(frozen=True)
class ExtractedCustomerFacts:
    fact_ids: tuple[str, ...]
    known_question_fields: tuple[str, ...]
    location_city: str | None
    case_reference: str | None
    policy_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_ids": list(self.fact_ids),
            "known_question_fields": list(self.known_question_fields),
            "location_city": self.location_city,
            "case_reference": self.case_reference,
            "policy_version": self.policy_version,
        }


def is_valid_case_reference(value: str | None) -> bool:
    if not value:
        return False
    normalized = value.strip()
    if normalized in INVALID_CASE_REFERENCES:
        return False
    if normalized.isdigit():
        return int(normalized) >= 100
    return len(normalized) >= 3


def normalize_case_reference(text: str) -> str | None:
    raw = extract_case_reference(text)
    if not is_valid_case_reference(raw):
        return None
    return raw


def extract_customer_facts(
    *,
    input_data: dict[str, Any],
    entities: dict[str, Any] | None = None,
) -> ExtractedCustomerFacts:
    entities = dict(entities or {})
    message = f"{input_data.get('subject') or ''} {input_data.get('message_text') or ''}"
    lowered = message.lower()
    fact_ids: list[str] = []
    known_fields: set[str] = set()

    city = extract_city_phrase(text=message, entities=entities)
    if city and city.lower() not in {"city", "known-city"}:
        fact_ids.append("location_city")
    if re.search(r"\b\d{1,4}\b.*\b(gatan|vägen|street)\b", lowered, re.I) or re.search(
        r"\bstorgatan\b", lowered, re.I
    ):
        fact_ids.append("property_address")
        known_fields.add("address")

    if any(token in lowered for token in ("solcell", "solceller", "solar panel", "solar")):
        fact_ids.append("system_type_solar")
        known_fields.add("system_type")
    if any(token in lowered for token in ("laddbox", "ev charger", "charger")):
        fact_ids.append("system_type_ev_charger")
        known_fields.add("system_type")

    if any(
        token in lowered
        for token in (
            "fungerar dåligt",
            "fungerar inte",
            "problem",
            "fel",
            "poor performance",
            "not working",
            "fault",
        )
    ):
        fact_ids.append("symptom_poor_performance")
        known_fields.add("symptom")

    if any(token in lowered for token in ("igår", "yesterday")):
        fact_ids.append("when_started_yesterday")
        known_fields.add("when_started")
    elif any(token in lowered for token in ("förra veckan", "last week", "en vecka")):
        fact_ids.append("when_started_last_week")
        known_fields.add("when_started")

    if any(token in lowered for token in ("villa", "detached house", "radhus", "townhouse")):
        fact_ids.append("property_type_villa")
        known_fields.add("property_type")

    if any(token in lowered for token in ("solceller sedan", "existing solar", "8 kwp", "befintlig sol")):
        fact_ids.append("existing_solar_system")
        known_fields.update({"existing_solar_system", "existing_installation"})

    if re.search(r"\b\d{4,5}\s*kwh\b", lowered):
        fact_ids.append("annual_consumption")
        known_fields.add("annual_consumption")

    if re.search(r"\bstatus\b|uppdatera status|hur ligger", lowered, re.I):
        fact_ids.append("status_requested")
        known_fields.add("status_dimension")

    case_ref = normalize_case_reference(message)
    if case_ref:
        fact_ids.append("case_reference_valid")
        known_fields.add("case_reference")

    discovery = extract_discovery_time_phrase(message)
    if discovery:
        fact_ids.append("discovery_time")
        known_fields.add("discovery_time")

    if any(token in lowered for token in ("bifogar", "attached", "attachment", "ritning", "bifogade")):
        if "saknar" in lowered or "without" in lowered or "inte bifogat" in lowered:
            fact_ids.append("attachment_missing")

    if any(token in lowered for token in ("batteri", "battery storage", "battery")):
        if "sol" in lowered or "solar" in lowered:
            fact_ids.append("battery_interest")
            known_fields.add("battery_interest")

    for fact_id in fact_ids:
        known_fields.update(FACT_TO_QUESTION_FIELDS.get(fact_id, frozenset()))

    return ExtractedCustomerFacts(
        fact_ids=tuple(sorted(set(fact_ids))),
        known_question_fields=tuple(sorted(known_fields)),
        location_city=city if city and city.lower() not in {"city"} else None,
        case_reference=case_ref,
        policy_version=POLICY_VERSION,
    )


def question_conflicts_with_known(field: str, known_fields: set[str]) -> bool:
    return field in known_fields
