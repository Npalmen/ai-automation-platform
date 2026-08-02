"""Localized customer-facing surface strings for reply rendering."""

from __future__ import annotations

import re
from typing import Any

_QUESTION_LABELS_SV: dict[str, str] = {
    "address": "adressen till fastigheten",
    "property_type": "vilken typ av fastighet det gäller (villa, radhus, BRF m.m.)",
    "roof_type": "vilken typ av tak huset har och ungefärlig takyta",
    "annual_consumption": "er ungefärliga årsförbrukning (kWh)",
    "battery_interest": "om ni vill titta på batterilagring samtidigt",
    "existing_installation": "om det redan finns en solcellsanläggning",
    "existing_solar_system": "en kort beskrivning av befintlig solcellsanläggning",
    "current_inverter": "vilken växelriktare eller vilket system ni har idag",
    "intended_purpose": "huvudsakligt syfte med batteriet",
    "battery_preference": "önskad batteristorlek eller kapacitet",
    "charging_points": "antal laddpunkter och önskad placering",
    "main_fuse": "huvudsäkring eller tillgänglig kapacitet",
    "load_balancing_need": "om ni behöver lastbalansering",
    "housing_association_context": "om det gäller privat, företag eller BRF",
    "system_type": "vilken typ av anläggning det gäller",
    "symptom": "en beskrivning av felet eller symptomet",
    "when_started": "när problemet började",
    "error_code": "eventuell felkod på display eller app",
    "safety_state": "om något känns osäkert el- eller brandsäkerhetsmässigt",
    "original_case": "orderreferens eller ursprungligt ärende",
    "discovery_time": "när problemet upptäcktes",
    "evidence": "bilder eller dokument som stödjer ärendet",
    "safety_relevance": "om felet kan påverka säkerheten",
    "requested_service": "vilken tjänst ni söker",
    "project_description": "en kort beskrivning av uppdraget",
    "attachment": "bilder eller ritningar om ni har",
    "phone_or_email": "hur vi bäst når er för uppföljning",
    "contact_name": "ert namn",
    "case_reference": "ärendenummer eller orderreferens",
    "customer_identifier": "adressen eller namnet som ärendet gäller",
    "status_dimension": "vad ni vill ha status på",
    "issue_summary": "en kort sammanfattning av ärendet",
    "issue_description": "en beskrivning av reklamationen",
}

_QUESTION_LABELS_EN: dict[str, str] = {
    "address": "the property address",
    "property_type": "the type of property (detached house, townhouse, housing association, etc.)",
    "roof_type": "the roof type and approximate roof area",
    "annual_consumption": "your approximate annual electricity consumption (kWh)",
    "battery_interest": "whether you are considering battery storage as well",
    "existing_installation": "whether there is already a solar installation",
    "existing_solar_system": "a brief description of the existing solar installation",
    "current_inverter": "which inverter or system you have today",
    "intended_purpose": "the main purpose of the battery",
    "battery_preference": "your preferred battery size or capacity",
    "charging_points": "how many charging points you need and where they should be placed",
    "main_fuse": "your main fuse rating or available capacity",
    "load_balancing_need": "whether you need load balancing",
    "housing_association_context": "whether this is for a private home, business, or housing association",
    "system_type": "which type of installation this concerns",
    "symptom": "a description of the fault or symptom",
    "when_started": "when the problem started",
    "error_code": "any error code shown on the display or app",
    "safety_state": "whether anything feels unsafe electrically or from a fire-safety perspective",
    "original_case": "the original order or case reference",
    "discovery_time": "when the problem was discovered",
    "evidence": "photos or documents that support the case",
    "safety_relevance": "whether the fault may affect safety",
    "requested_service": "which service you are looking for",
    "project_description": "a brief description of the project",
    "attachment": "photos or drawings if you have them",
    "phone_or_email": "the best way to reach you for follow-up",
    "contact_name": "your name",
    "case_reference": "the case or order number",
    "customer_identifier": "the address or name connected to the case",
    "status_dimension": "what you would like status on",
    "issue_summary": "a brief summary of the case",
    "issue_description": "a description of the complaint",
}


def extract_case_reference(text: str) -> str | None:
    lowered = text.lower()
    patterns = (
        r"\bärende\s*(?:nr\.?|nummer)?\s*(\d+)\b",
        r"\bcase\s*(?:no\.?|number)?\s*(\d+)\b",
        r"\bstatus\s+på\s+vårt\s+ärende\s+(\d+)\b",
        r"\border\s*(?:no\.?|number)?\s*(\d+)\b",
        r"\boffertförfrågan\s*(\d+)\b",
        r"\bquote\s*(?:request|enquiry)?\s*(?:no\.?|number)?\s*(\d+)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, lowered, re.I)
        if match:
            return match.group(1)
    return None


def extract_city_phrase(*, text: str, entities: dict[str, Any]) -> str | None:
    city = entities.get("city")
    if isinstance(city, str) and city.strip():
        value = city.replace("known-", "").strip()
        if value and not value.startswith("known"):
            return value.title() if value.islower() else value
    for candidate in ("Uppsala", "Stockholm", "Enköping"):
        if candidate.lower() in text.lower():
            return candidate
    return None


def extract_discovery_time_phrase(text: str) -> str | None:
    patterns = (
        r"\b(i går|igår|idag|i dag|den här veckan|för två veckor sedan|för en vecka sedan|nyligen)\b",
        r"\b(yesterday|today|this week|two weeks ago|recently)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1)
    return None


def contextual_question_surface(
    field: str,
    *,
    language: str,
    city_phrase: str | None = None,
) -> str:
    labels = _QUESTION_LABELS_EN if language == "en" else _QUESTION_LABELS_SV
    if field == "address" and city_phrase:
        if language == "en":
            return f"the property address in {city_phrase}"
        return f"adressen till fastigheten i {city_phrase}"
    label = labels.get(field)
    if label is not None:
        return label
    # Never expose raw schema field ids to customers.
    normalized = field.replace("_", " ")
    if language == "en":
        return f"some additional details about {normalized}"
    return f"ytterligare uppgifter om {normalized}"


def build_question_surface_labels(
    selected_questions: tuple[str, ...],
    *,
    language: str,
    city_phrase: str | None = None,
) -> tuple[str, ...]:
    return tuple(
        contextual_question_surface(field, language=language, city_phrase=city_phrase)
        for field in selected_questions
    )


def compose_question_block(
    questions: tuple[str, ...],
    *,
    language: str,
    service_family: str,
) -> str:
    if not questions:
        return ""

    if len(questions) == 1:
        if language == "en":
            return f"To move forward, could you share {questions[0]}?"
        return f"För att vi ska kunna gå vidare behöver vi {questions[0]}."

    if len(questions) <= 3:
        if language == "sv":
            joined = ", ".join(questions[:-1]) + f" och {questions[-1]}"
            return f"För att vi ska kunna göra en första bedömning behöver vi {joined}."
        joined = ", ".join(questions[:-1]) + f", and {questions[-1]}"
        return f"To make an initial assessment, please send us {joined}."

    intro = {
        "solar_installation": ("For the solar quote we need:", "För solcellsofferten behöver vi:"),
        "battery_installation": ("For the battery assessment we need:", "För batteribedömningen behöver vi:"),
        "ev_charger": ("For the charger project we need:", "För laddboxprojektet behöver vi:"),
        "existing_installation_support": ("To troubleshoot further we need:", "För att felsöka vidare behöver vi:"),
        "complaint_warranty": ("For the complaint case we need:", "För reklamationsärendet behöver vi:"),
    }.get(service_family, ("Could you reply with:", "Kan du återkomma med:"))
    prefix = intro[1 if language == "sv" else 0]
    bullets = "\n".join(
        f"- {q.capitalize() if language == 'en' else (q[0].upper() + q[1:] if q else q)}"
        for q in questions
    )
    return f"{prefix}\n{bullets}"


def localized_next_step(
    *,
    step_id: str,
    language: str,
    service_family: str,
    has_questions: bool,
) -> str:
    if service_family == "job_status":
        return (
            "We will get back to you once we have reviewed the case."
            if language == "en"
            else "Vi återkommer när vi har gått igenom ärendet."
        )
    if service_family == "complaint_warranty":
        return (
            "A colleague will review the case manually once we have the details."
            if language == "en"
            else "En kollega går igenom ärendet när vi har underlaget."
        )
    if has_questions:
        return (
            "Once we have that information, we will review the site conditions and get back to you."
            if language == "en"
            else "När vi har det underlaget går vi igenom förutsättningarna och återkommer."
        )
    return (
        "We will review the details and get back to you."
        if language == "en"
        else "Vi går igenom underlaget och återkommer."
    )
