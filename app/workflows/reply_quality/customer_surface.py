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
    "existing_installation": "om det redan finns en solcellsanläggning på fastigheten",
    "existing_solar_system": "en kort beskrivning av befintlig solcellsanläggning",
    "current_inverter": "vilken växelriktare eller vilket system ni har idag",
    "intended_purpose": "huvudsakligt syfte med batteriet",
    "battery_preference": "önskad batteristorlek eller kapacitet",
    "charging_points": "antal laddpunkter och önskad placering",
    "main_fuse": "Vilken storlek har huvudsäkringen?",
    "load_balancing_need": "Behöver ni även lastbalansering till laddboxen?",
    "energy_priority_goal": "ert huvudsakliga mål (laddning, lägre elkostnad eller investering)",
    "ev_ownership_or_plan": "om ni har eller planerar elbil",
    "charging_need": "ert ungefärliga laddbehov",
    "preferred_call_times": "två eller tre tider som passar för ett samtal",
    "consultation_focus": "vilka frågor ni främst vill gå igenom",
    "preferred_contact_method": "vilken kontaktväg ni föredrar",
    "housing_association_context": "om det gäller privat, företag eller BRF",
    "system_type": "vilken typ av anläggning det gäller",
    "symptom": "en beskrivning av felet eller symptomet",
    "when_started": "när problemet började",
    "error_code": "någon felkod på display eller app",
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
    "main_fuse": "What size is your main fuse or available capacity?",
    "load_balancing_need": "Do you also need load balancing for the charger?",
    "energy_priority_goal": "your main goal (charging, lower electricity costs, or investment)",
    "ev_ownership_or_plan": "whether you have or are planning an electric car",
    "charging_need": "your approximate charging needs",
    "preferred_call_times": "two or three times that would suit you for a call",
    "consultation_focus": "which questions you mainly want to cover",
    "preferred_contact_method": "your preferred contact method",
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
    for candidate in ("Enköping", "Uppsala", "Stockholm"):
        if candidate.lower() in text.lower():
            return candidate
    city = entities.get("city")
    if isinstance(city, str) and city.strip():
        value = city.replace("known-", "").strip()
        lowered = value.lower()
        if lowered in {"", "city", "known-city", "known_city"}:
            return None
        if lowered in {"uppsala", "enköping", "stockholm"}:
            return value.title() if value.islower() else value
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


def pronoun_register_for_plan(*, service_family: str, language: str) -> str:
    if language == "en":
        return "you"
    if service_family in {"existing_installation_support", "complaint_warranty", "job_status"}:
        return "du"
    return "ni"


_PRONOUN_CONTRACTS_SV: dict[str, dict[str, tuple[str, ...]]] = {
    "du": {
        "allowed": ("du", "dig", "din", "ditt", "dina"),
        "forbidden": ("ni", "er", "ert", "era"),
    },
    "ni": {
        "allowed": ("ni", "er", "ert", "era"),
        "forbidden": ("du", "dig", "din", "ditt", "dina"),
    },
}


def pronoun_surface_contract(*, register: str, language: str) -> dict[str, tuple[str, ...]]:
    """Explicit allowed/forbidden pronoun forms for constrained LLM rendering."""
    if language == "en":
        return {
            "allowed": ("you", "your", "yours"),
            "forbidden": (),
        }
    return _PRONOUN_CONTRACTS_SV.get(register, _PRONOUN_CONTRACTS_SV["ni"])


def _adjust_sv_register(text: str, register: str) -> str:
    if register != "du":
        return text
    adjusted = text
    replacements = (
        (r"\bera\b", "dina"),
        (r"\bert\b", "ditt"),
        (r"\ber\b", "din"),
        (r"\bni\b", "du"),
        (r"\bom ni har\b", "om du har"),
        (r"\bni vill\b", "du vill"),
        (r"\bni söker\b", "du söker"),
        (r"\bni behöver\b", "du behöver"),
        (r"\bni har\b", "du har"),
    )
    for pattern, repl in replacements:
        adjusted = re.sub(pattern, repl, adjusted, flags=re.I)
    return adjusted


def contextual_question_surface(
    field: str,
    *,
    language: str,
    city_phrase: str | None = None,
    pronoun_register: str = "ni",
    service_family: str | None = None,
) -> str:
    labels = _QUESTION_LABELS_EN if language == "en" else _QUESTION_LABELS_SV
    if field == "address" and city_phrase:
        if language == "en":
            return f"the installation address in {city_phrase}"
        return f"adressen i {city_phrase}"
    if field == "energy_priority_goal":
        if service_family == "solar_battery_combined":
            if language == "en":
                return "the main goal or function for the battery part of the installation"
            return "batteriets huvudsakliga mål eller funktion"
        if language == "en":
            return "your main goal (charging, lower electricity costs, or investment)"
        return "ert huvudsakliga mål (laddning, lägre elkostnad eller investering)"
    if field == "attachment" and service_family in {"existing_installation_support", "complaint_warranty"}:
        if language == "en":
            return "Please send photos or drawings if you have any."
        return "Skicka gärna bilder eller ritningar om sådana finns."
    label = labels.get(field)
    if label is not None:
        return _adjust_sv_register(label, pronoun_register) if language == "sv" else label
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
    pronoun_register: str = "ni",
    service_family: str | None = None,
) -> tuple[str, ...]:
    return tuple(
        contextual_question_surface(
            field,
            language=language,
            city_phrase=city_phrase,
            pronoun_register=pronoun_register,
            service_family=service_family,
        )
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
        q = questions[0]
        if q.endswith("?"):
            return q
        if language == "en":
            return f"To move forward, could you share {q}?"
        return f"För att vi ska kunna gå vidare behöver vi {q}."

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
    business_intent: str = "lead",
    thread_state: str = "new_thread",
    is_continuation: bool = False,
    scenario_family: str | None = None,
    mentions_attachment_gap: bool = False,
) -> str:
    from app.workflows.reply_quality.next_step_surface import localized_next_step as _localized

    return _localized(
        step_id=step_id,
        language=language,
        service_family=service_family,
        has_questions=has_questions,
        business_intent=business_intent,
        thread_state=thread_state,
        is_continuation=is_continuation,
        scenario_family=scenario_family,
        mentions_attachment_gap=mentions_attachment_gap,
    )
