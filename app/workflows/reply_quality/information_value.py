"""Information-value question planning (Todo C)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.service_profiles.qualification import _profile_field_present

from app.workflows.reply_quality.customer_surface import (
    contextual_question_surface,
    extract_case_reference,
    extract_city_phrase,
    extract_discovery_time_phrase,
)
from app.workflows.reply_quality.operational_next_step import OperationalNextStep
from app.workflows.reply_quality.service_playbooks import ReplyServicePlaybook

POLICY_VERSION = "information_value_plan_v2"

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


def _field_known(field: str, *, entities: dict[str, Any], text: str) -> bool:
    if field == "case_reference":
        return extract_case_reference(text) is not None
    if field == "status_dimension" and any(
        token in text for token in ("status", "läge", "hur ligger", "var står")
    ):
        return True
    if field == "discovery_time":
        return extract_discovery_time_phrase(text) is not None
    if field == "address":
        city = extract_city_phrase(text=text, entities=entities)
        if city and re.search(r"\b\d{1,4}\b|\bgatan\b|\bvägen\b|\bstreet\b", text, re.I):
            return _profile_field_present(field, text, entities)
        if city and field == "address":
            return False
    return _profile_field_present(field, text, entities)


def _score_field(
    field: str,
    *,
    playbook: ReplyServicePlaybook,
    next_step_id: str,
    known: bool,
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
    city_phrase = extract_city_phrase(text=input_data.get("message_text", "") + " " + input_data.get("subject", ""), entities=entities)
    case_reference = extract_case_reference(text)
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

    known: list[str] = list(known_fact_fields)
    candidates = list(playbook.question_priority)
    for required in playbook.required_facts_by_next_step.get(next_step.step_id, ()):
        if required not in candidates:
            candidates.append(required)

    scored: list[tuple[int, str]] = []
    excluded: list[str] = []
    reasons: list[str] = []

    for field in candidates:
        present = field in known or _field_known(field, entities=entities, text=text)
        if case_reference and field in {"case_reference", "customer_identifier", "status_dimension"}:
            present = True
        if status_requested and field in {"status_dimension", "case_reference"}:
            present = True
        if entities.get("email") and field == "customer_identifier":
            present = True
        if city_phrase and field == "address" and not re.search(
            r"\b\d{1,4}\b|\bgatan\b|\bvägen\b|\bstreet\b", text, re.I
        ):
            present = False
        if present:
            known.append(field)
            excluded.append(field)
            reasons.append(f"exclude:{field}:already_known")
            continue
        score = _score_field(
            field,
            playbook=playbook,
            next_step_id=next_step.step_id,
            known=False,
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
        scored.append((score, field))

    scored.sort(key=lambda item: (-item[0], item[1]))
    selected = [field for score, field in scored if score > 0][:budget]
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
        already_known_facts=tuple(sorted(set(known))),
        question_budget=budget,
        playbook_id=playbook.playbook_id,
        policy_version=POLICY_VERSION,
    )
