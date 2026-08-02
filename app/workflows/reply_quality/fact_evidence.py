"""Evidence-backed fact states for reply planning."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.workflows.reply_quality.customer_surface import extract_city_phrase
from app.workflows.reply_quality.semantic_fact_predicates import (
    detect_semantic_fact_ids,
    existing_solar_verified,
)

POLICY_VERSION = "fact_evidence_v1"

ADDRESS_STATE_LOCATION_CITY = "location_city_known"
ADDRESS_STATE_PROPERTY_ADDRESS = "property_address_known"
ADDRESS_STATE_MISSING = "property_address_missing"
ADDRESS_STATE_NOT_REQUIRED = "property_address_not_required_yet"


@dataclass(frozen=True)
class AddressFactState:
    state: str
    city: str | None
    has_street_address: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "city": self.city,
            "has_street_address": self.has_street_address,
        }


@dataclass(frozen=True)
class FactEvidenceSnapshot:
    fact_ids: tuple[str, ...]
    evidenced_question_fields: tuple[str, ...]
    evidence_by_field: dict[str, str]
    address_state: AddressFactState
    policy_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_ids": list(self.fact_ids),
            "evidenced_question_fields": list(self.evidenced_question_fields),
            "evidence_by_field": dict(self.evidence_by_field),
            "address_state": self.address_state.to_dict(),
            "policy_version": self.policy_version,
        }


def _has_street_address(text: str, entities: dict[str, Any]) -> bool:
    if entities.get("address"):
        return True
    lowered = text.lower()
    return bool(
        re.search(r"\b\d{1,4}\b.*\b(gatan|vägen|street)\b", lowered, re.I)
        or re.search(r"\bstorgatan\b", lowered, re.I)
    )


def resolve_address_fact_state(
    *,
    text: str,
    entities: dict[str, Any] | None = None,
) -> AddressFactState:
    entities = dict(entities or {})
    city = extract_city_phrase(text=text, entities=entities)
    if city and city.lower() in {"city", "known-city"}:
        city = None
    has_address = _has_street_address(text, entities)
    if has_address:
        return AddressFactState(
            state=ADDRESS_STATE_PROPERTY_ADDRESS,
            city=city,
            has_street_address=True,
        )
    if city:
        return AddressFactState(
            state=ADDRESS_STATE_LOCATION_CITY,
            city=city,
            has_street_address=False,
        )
    return AddressFactState(
        state=ADDRESS_STATE_MISSING,
        city=None,
        has_street_address=False,
    )


def build_fact_evidence(
    *,
    input_data: dict[str, Any],
    entities: dict[str, Any] | None = None,
    known_fact_fields: tuple[str, ...] = (),
) -> FactEvidenceSnapshot:
    """Return only positively evidenced question fields and address state."""
    from app.workflows.reply_quality.fact_extraction import extract_customer_facts

    entities = dict(entities or {})
    message = f"{input_data.get('subject') or ''} {input_data.get('message_text') or ''}"
    extracted = extract_customer_facts(input_data=input_data, entities=entities)
    semantic_ids = set(detect_semantic_fact_ids(message))
    address = resolve_address_fact_state(text=message, entities=entities)

    evidence: dict[str, str] = {}
    evidenced: set[str] = set()

    def mark(field: str, source: str) -> None:
        evidenced.add(field)
        evidence[field] = source

    for field in known_fact_fields:
        if field == "address" and address.state != ADDRESS_STATE_PROPERTY_ADDRESS:
            continue
        if field == "annual_consumption":
            if not (
                re.search(r"\b\d{4,5}\s*kwh\b", message, re.I)
                or "annual_consumption" in extracted.known_question_fields
                or entities.get("annual_consumption")
            ):
                continue
        if field == "issue_description":
            if "issue_description" not in extracted.known_question_fields:
                continue
        if field in {"existing_solar_system", "current_inverter"} and not existing_solar_verified(
            semantic_ids, set(extracted.known_question_fields)
        ):
            continue
        mark(field, f"profile_known:{field}")

    if address.state == ADDRESS_STATE_PROPERTY_ADDRESS:
        mark("address", "semantic:property_address")

    if "property_address" in semantic_ids and "address" not in evidenced:
        mark("address", "semantic:property_address")

    for field in extracted.known_question_fields:
        if field == "address":
            if address.state != ADDRESS_STATE_PROPERTY_ADDRESS:
                continue
            mark("address", "extracted:property_address")
            continue
        if field in {"existing_solar_system", "current_inverter"}:
            if not existing_solar_verified(semantic_ids, set(extracted.known_question_fields)):
                continue
        if field == "existing_installation" and not existing_solar_verified(
            semantic_ids, set(extracted.known_question_fields)
        ):
            continue
        if field in evidenced:
            continue
        mark(field, f"extracted:{field}")

    if entities.get("address"):
        mark("address", "entity:address")
    if entities.get("property_type"):
        mark("property_type", "entity:property_type")
    if entities.get("main_fuse"):
        mark("main_fuse", "entity:main_fuse")
    if entities.get("annual_consumption"):
        mark("annual_consumption", "entity:annual_consumption")
    if entities.get("customer_name") or entities.get("company_name"):
        mark("contact_name", "entity:contact_name")
    if entities.get("email") or "@" in message:
        mark("phone_or_email", "entity:email")

    from app.workflows.reply_quality.fact_extraction import normalize_case_reference
    from app.workflows.reply_quality.customer_surface import extract_discovery_time_phrase

    case_ref = normalize_case_reference(message)
    if case_ref:
        mark("case_reference", "extracted:case_reference")
        if entities.get("email") or "@" in message:
            mark("customer_identifier", "entity:email_with_case_reference")
    if extract_discovery_time_phrase(message):
        mark("discovery_time", "extracted:discovery_time")
    if re.search(r"\bstatus\b|uppdatera status|hur ligger", message, re.I):
        mark("status_dimension", "extracted:status_request")
    if "load_balancing_stated" in semantic_ids:
        mark("load_balancing_need", "semantic:load_balancing_stated")
    if "requested_service_explicit" in semantic_ids or any(
        intent in semantic_ids
        for intent in (
            "consultation_solar_vs_battery",
            "consultation_energy_storage",
            "consultation_charger_vs_solar",
            "consultation_booking",
        )
    ):
        mark("requested_service", "semantic:requested_service_explicit")

    return FactEvidenceSnapshot(
        fact_ids=extracted.fact_ids,
        evidenced_question_fields=tuple(sorted(evidenced)),
        evidence_by_field=evidence,
        address_state=address,
        policy_version=POLICY_VERSION,
    )


def verified_fact_labels_from_evidence(
    *,
    service_type: str,
    evidence: FactEvidenceSnapshot,
    case_reference_phrase: str | None = None,
) -> tuple[str, ...]:
    labels: list[str] = []
    if service_type:
        labels.append(f"internal_service:{service_type}")
    if evidence.address_state.city:
        labels.append(f"internal_location_city:{evidence.address_state.city}")
    if case_reference_phrase:
        labels.append(f"internal_case_reference:{case_reference_phrase}")
    for field in evidence.evidenced_question_fields:
        labels.append(f"internal_known:{field}")
        labels.append(f"evidence:{field}:{evidence.evidence_by_field.get(field, 'unknown')}")
    return tuple(labels)
