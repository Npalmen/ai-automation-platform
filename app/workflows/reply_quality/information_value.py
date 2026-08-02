"""Information-value question planning (Todo C)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.service_profiles.qualification import _profile_field_present

from app.workflows.reply_quality.customer_surface import (
    contextual_question_surface,
    extract_city_phrase,
    extract_discovery_time_phrase,
)
from app.workflows.reply_quality.fact_extraction import (
    extract_customer_facts,
    normalize_case_reference,
)
from app.workflows.reply_quality.fact_evidence import (
    ADDRESS_STATE_PROPERTY_ADDRESS,
    build_fact_evidence,
)
from app.workflows.reply_quality.semantic_fact_predicates import (
    attachment_state,
    detect_consultation_intent,
    existing_solar_verified,
)
from app.workflows.reply_quality.operational_next_step import OperationalNextStep
from app.workflows.reply_quality.service_playbooks import ReplyServicePlaybook

POLICY_VERSION = "information_value_plan_v5"

_FIELD_LABELS: dict[str, str] = {
    "address": "Adress eller ort för installationen/ärendet",
    "property_type": "Typ av fastighet (villa, radhus, BRF m.m.)",
    "roof_type": "Taktyp och ungefärlig takyta",
    "annual_consumption": "Ungefärlig årsförbrukning (kWh)",
    "battery_interest": "Om du vill kombinera med batterilager",
    "existing_installation": "Om det finns befintlig solcellsanläggning",
    "existing_solar_system": "Beskrivning av befintlig solcellsanläggning",
    "current_inverter": "Vilken växelriktare/system du har idag",
    "intended_purpose": "Huvudsakligt syfte med batteriet",
    "battery_preference": "Önskad batteristorlek eller kapacitet",
    "charging_points": "Antal laddpunkter och önskad placering",
    "main_fuse": "Huvudsäkring eller tillgänglig kapacitet",
    "load_balancing_need": "Behov av lastbalansering",
    "housing_association_context": "Privat, företag eller BRF",
    "system_type": "Vilken typ av anläggning det gäller",
    "symptom": "Beskrivning av felet eller symptomet",
    "when_started": "När problemet började",
    "error_code": "Eventuell felkod på display/app",
    "safety_state": "Om något känns osäkert el- eller brandsäkerhetsmässigt",
    "case_reference": "Ärendenummer eller tidigare referens om du har",
    "customer_identifier": "Adress eller namn kopplat till ärendet",
    "status_dimension": "Vad du vill få status på (offert, bokning, ärende)",
    "issue_summary": "Kort sammanfattning av ärendet",
    "original_case": "Ursprungligt ärende eller orderreferens",
    "issue_description": "Beskrivning av reklamationen",
    "discovery_time": "När problemet upptäcktes",
    "evidence": "Bilder eller dokument som stödjer ärendet",
    "safety_relevance": "Om felet kan påverka säkerheten",
    "requested_service": "Vilken tjänst du söker",
    "project_description": "Kort beskrivning av uppdraget",
    "attachment": "Bilder eller ritningar om du har",
    "phone_or_email": "Telefon eller e-post för uppföljning",
    "contact_name": "Ditt namn",
}


@dataclass(frozen=True)
class InformationValuePlan:
    candidate_questions: tuple[str, ...]
    selected_questions: tuple[str, ...]
    selected_question_labels: tuple[str, ...]
    excluded_questions: tuple[str, ...]
    selection_reasons: tuple[str, ...]
    already_known_facts: tuple[str, ...]
    question_budget: int
    playbook_id: str
    policy_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_questions": list(self.candidate_questions),
            "selected_questions": list(self.selected_questions),
            "selected_question_labels": list(self.selected_question_labels),
            "excluded_questions": list(self.excluded_questions),
            "selection_reasons": list(self.selection_reasons),
            "already_known_facts": list(self.already_known_facts),
            "question_budget": self.question_budget,
            "playbook_id": self.playbook_id,
            "policy_version": self.policy_version,
        }


def _combined_text(input_data: dict[str, Any]) -> str:
    return f"{input_data.get('subject') or ''} {input_data.get('message_text') or ''}".lower()


def _field_known(
    field: str,
    *,
    entities: dict[str, Any],
    text: str,
    extracted_known: set[str],
    fact_ids: set[str],
) -> bool:
    if field in extracted_known:
        return True
    if field == "case_reference":
        return normalize_case_reference(text) is not None
    if field == "status_dimension" and any(
        token in text for token in ("status", "läge", "hur ligger", "var står")
    ):
        return True
    if field == "discovery_time":
        return extract_discovery_time_phrase(text) is not None
    if field == "annual_consumption":
        if re.search(r"\b\d{4,5}\s*kwh\b", text, re.I):
            return True
        if "annual_consumption" in extracted_known or entities.get("annual_consumption"):
            return True
        return False
    if field == "address":
        if entities.get("address"):
            return True
        if re.search(r"\b\d{1,4}\b.*\b(gatan|vägen|street)\b", text, re.I) or re.search(
            r"\bstorgatan\b", text, re.I
        ):
            return True
        return False
    if field == "housing_association_context":
        if "property_type" in extracted_known or "housing_association_context" in extracted_known:
            return True
    if field == "load_balancing_need":
        if "load_balancing_stated" in extracted_known or "load_balancing_need" in extracted_known:
            return True
    if field == "requested_service":
        if "requested_service_explicit" in extracted_known or "requested_service" in extracted_known:
            return True
    if field == "attachment":
        state = attachment_state(text)
        if state in {"attachment_claimed_kwh", "attachment_present_kwh", "attachment_claimed"}:
            return True
        if state == "attachment_missing_drawing":
            return False
    return _profile_field_present(field, text, entities)


def _score_field(
    field: str,
    *,
    playbook: ReplyServicePlaybook,
    next_step_id: str,
    known: bool,
    text: str = "",
) -> int:
    if known:
        return -100
    if field in playbook.forbidden_email_questions:
        return -50
    required = playbook.required_facts_by_next_step.get(next_step_id, ())
    score = 0
    if field in required:
        score += 40
    try:
        score += (len(playbook.question_priority) - playbook.question_priority.index(field)) * 3
    except ValueError:
        score += 1
    if field == "contact_name":
        score -= 25
    if field == "phone_or_email":
        score -= 10
    if field in playbook.optional_high_value_facts:
        score += 5
    if field == "attachment":
        state = attachment_state(text)
        if state in {"attachment_claimed", "attachment_claimed_kwh", "attachment_present_kwh"}:
            return -100
        if any(
            token in text
            for token in ("saknar ritning", "not attached", "inte bifogat", "not attached yet")
        ):
            score += 60
    return score


def build_information_value_plan(
    *,
    playbook: ReplyServicePlaybook,
    next_step: OperationalNextStep,
    input_data: dict[str, Any],
    entities: dict[str, Any] | None = None,
    known_fact_fields: tuple[str, ...] = (),
    is_followup: bool = False,
    phone_required_by_profile: bool = False,
    language: str = "sv",
) -> InformationValuePlan:
    entities = dict(entities or {})
    text = _combined_text(input_data)
    extracted = extract_customer_facts(input_data=input_data, entities=entities)
    extracted_known = set(extracted.known_question_fields) | set(extracted.fact_ids)
    semantic_ids = set(extracted.fact_ids)
    evidence = build_fact_evidence(
        input_data=input_data,
        entities=entities,
        known_fact_fields=known_fact_fields,
    )
    evidenced_known: set[str] = set(evidence.evidenced_question_fields)
    consultation_intent = detect_consultation_intent(text)
    city_phrase = extracted.location_city or extract_city_phrase(
        text=input_data.get("message_text", "") + " " + input_data.get("subject", ""),
        entities=entities,
    )
    case_reference = extracted.case_reference or normalize_case_reference(text)
    status_requested = bool(
        re.search(r"\bstatus\b|uppdatera status|hur ligger|var står", text, re.I)
    )
    budget = (
        playbook.maximum_questions_followup
        if is_followup
        else playbook.maximum_questions_first_reply
    )

    if playbook.service_family == "job_status":
        if case_reference or status_requested:
            budget = 0

    known: list[str] = []
    candidates = list(playbook.question_priority)
    for required in playbook.required_facts_by_next_step.get(next_step.step_id, ()):
        if required not in candidates:
            candidates.append(required)

    if consultation_intent == "consultation_booking":
        budget = 0
    elif consultation_intent:
        budget = min(budget, 4)

    scored: list[tuple[int, str]] = []
    excluded: list[str] = []
    reasons: list[str] = []

    attach_state = attachment_state(text)
    solar_verified = existing_solar_verified(semantic_ids, extracted_known)

    for field in candidates:
        if field in evidenced_known:
            excluded.append(field)
            reasons.append(f"exclude:{field}:evidenced_known")
            continue

        if consultation_intent and field in {"project_description", "requested_service"}:
            excluded.append(field)
            reasons.append(f"exclude:{field}:consultation_intent")
            continue

        if case_reference and field in {"case_reference", "customer_identifier", "status_dimension"}:
            evidenced_known.add(field)
            excluded.append(field)
            reasons.append(f"exclude:{field}:evidenced_known")
            continue
        if status_requested and field in {"status_dimension", "case_reference"}:
            evidenced_known.add(field)
            excluded.append(field)
            reasons.append(f"exclude:{field}:evidenced_known")
            continue

        if field in {"roof_type", "property_type"} and "battery_retrofit" in extracted_known:
            excluded.append(field)
            reasons.append(f"exclude:{field}:battery_retrofit")
            continue
        if field == "existing_solar_system" and not solar_verified:
            excluded.append(field)
            reasons.append(f"exclude:{field}:no_verified_solar")
            continue
        if field == "current_inverter" and not solar_verified:
            excluded.append(field)
            reasons.append(f"exclude:{field}:no_verified_solar")
            continue
        if field == "existing_installation" and solar_verified:
            evidenced_known.add("existing_installation")
            excluded.append(field)
            reasons.append(f"exclude:{field}:evidenced_known")
            continue
        if field == "attachment" and attach_state in {
            "attachment_claimed_kwh",
            "attachment_present_kwh",
        }:
            evidenced_known.add("attachment")
            excluded.append(field)
            reasons.append(f"exclude:{field}:evidenced_known")
            continue
        if field == "annual_consumption" and attach_state in {
            "attachment_claimed_kwh",
            "attachment_present_kwh",
        }:
            evidenced_known.add("annual_consumption")
            excluded.append(field)
            reasons.append(f"exclude:{field}:evidenced_known")
            continue

        present = _field_known(
            field,
            entities=entities,
            text=text,
            extracted_known=extracted_known,
            fact_ids=semantic_ids,
        )
        if present:
            evidenced_known.add(field)
            excluded.append(field)
            reasons.append(f"exclude:{field}:evidenced_known")
            continue

        score = _score_field(
            field,
            playbook=playbook,
            next_step_id=next_step.step_id,
            known=False,
            text=text,
        )
        if field == "phone_or_email" and not phone_required_by_profile:
            if entities.get("email") or "@" in text:
                excluded.append(field)
                reasons.append("exclude:phone_or_email:email_present")
                continue
            if next_step.step_id not in {"collect_contact_preference"}:
                score -= 15
        if field == "contact_name":
            if entities.get("customer_name") or entities.get("company_name"):
                excluded.append(field)
                reasons.append("exclude:contact_name:known")
                continue
            score -= 20
        if (
            field == "existing_installation"
            and playbook.service_family == "battery_installation"
            and not solar_verified
        ):
            score += 45
        if consultation_intent and field in {"annual_consumption", "existing_installation", "intended_purpose"}:
            score += 25
        scored.append((score, field))

    scored.sort(key=lambda item: (-item[0], item[1]))
    selected = [field for score, field in scored if score > 0][:budget]
    selected = [field for field in selected if field not in evidenced_known]
    final_evidence = build_fact_evidence(
        input_data=input_data,
        entities=entities,
        known_fact_fields=tuple(sorted(evidenced_known)),
    )
    known = list(final_evidence.evidenced_question_fields)
    labels = [
        contextual_question_surface(field, language=language, city_phrase=city_phrase)
        for field in selected
    ]
    for field in selected:
        reasons.append(f"select:{field}:operational_value")

    return InformationValuePlan(
        candidate_questions=tuple(candidates),
        selected_questions=tuple(selected),
        selected_question_labels=tuple(labels),
        excluded_questions=tuple(excluded),
        selection_reasons=tuple(reasons),
        already_known_facts=tuple(known),
        question_budget=budget,
        playbook_id=playbook.playbook_id,
        policy_version=POLICY_VERSION,
    )
