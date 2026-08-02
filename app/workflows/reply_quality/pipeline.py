"""End-to-end digital coworker reply build and render pipeline."""

from __future__ import annotations

import re
from typing import Any

from app.workflows.missing_fact_plan import MissingFactPlan
from app.workflows.reply_planning import _resolve_location_hint, _resolve_service_hint
from app.workflows.reply_quality.acknowledgement_plan import build_acknowledgement_plan
from app.workflows.reply_quality.customer_surface import (
    build_question_surface_labels,
    extract_city_phrase,
    extract_discovery_time_phrase,
    pronoun_register_for_plan,
)
from app.workflows.reply_quality.fact_extraction import extract_customer_facts, normalize_case_reference
from app.workflows.reply_quality.plan_invariants import (
    validate_evidence_based_known_facts,
    validate_pipeline_playbook_consistency,
    validate_selected_known_invariant,
)
from app.workflows.reply_quality.information_value import build_information_value_plan
from app.workflows.reply_quality.plan_v2 import (
    CustomerReplyPlanV2,
    adapt_plan_v2_to_v1,
    build_customer_reply_plan_v2,
)
from app.workflows.reply_quality.renderer import RenderResult, render_coworker_reply_with_validation
from app.workflows.reply_quality.reply_language import decide_reply_language, localized_greeting
from app.workflows.reply_quality.fact_evidence import (
    FactEvidenceSnapshot,
    verified_fact_labels_from_evidence,
)
from app.workflows.reply_quality.pipeline_routing import resolve_reply_pipeline_context
from app.workflows.reply_quality.semantic_fact_predicates import (
    attachment_state,
    detect_semantic_fact_ids,
    existing_solar_verified,
)
from app.workflows.reply_quality.thread_context import (
    acknowledgement_mode_for_thread,
    build_thread_reply_context,
)
from app.workflows.safe_ack_eligibility import SafeAckEligibilityResult


def _continuation_has_new_substance(message_text: str) -> bool:
    lowered = (message_text or "").lower()
    markers = (
        "här kommer",
        "kompletterande info",
        "bifogar",
        "kompletterar med",
        "bekräfta",
        "villa",
        "brf",
        "årsförbrukning",
        " kwh",
        "kvm",
        "takbilder",
        "takytan",
        "adress",
        "storgatan",
        "enclosure",
        "attached",
        "following up with",
    )
    if any(marker in lowered for marker in markers):
        return True
    return bool(re.search(r"\d{3,}", lowered))


def _internal_verified_fact_ids(
    *,
    service_type: str,
    evidence: FactEvidenceSnapshot,
    case_reference_phrase: str | None,
) -> tuple[str, ...]:
    return verified_fact_labels_from_evidence(
        service_type=service_type,
        evidence=evidence,
        case_reference_phrase=case_reference_phrase,
    )


def build_coworker_reply_plan_v2(
    *,
    greeting: str,
    signature_name: str,
    missing_fact_plan: MissingFactPlan,
    eligibility: SafeAckEligibilityResult,
    input_data: dict[str, Any],
    entities: dict[str, Any] | None = None,
    fact_map: dict[str, str | None] | None = None,
    business_intent: str | None = None,
    thread_state: str = "new_thread",
    tone_profile: str = "professional_concise",
    language: str = "sv",
    profile_default_language: str = "sv",
) -> CustomerReplyPlanV2 | None:
    if not eligibility.eligible:
        return None

    entities = dict(entities or {})
    fact_map = dict(fact_map or {})
    combined_text = f"{input_data.get('subject') or ''} {input_data.get('message_text') or ''}"
    scenario_family = input_data.get("_coworker_scenario_family")
    if isinstance(scenario_family, str):
        scenario_family = scenario_family.strip() or None
    else:
        scenario_family = None
    language_decision = decide_reply_language(
        input_data=input_data,
        profile_default_language=profile_default_language,
    )
    language = language_decision.language
    greeting = localized_greeting(language=language, signature_name=signature_name)

    service_type = str(input_data.get("_force_service_type") or missing_fact_plan.service_type)
    intent = business_intent or "lead"
    thread = build_thread_reply_context(
        thread_state=thread_state,
        prior_safe_ack=thread_state == "continuation",
        supplied_facts=missing_fact_plan.known_facts,
    )
    pipeline_ctx = resolve_reply_pipeline_context(
        base_service_type=service_type,
        business_intent=intent,
        input_data=input_data,
        entities=entities,
        known_fact_fields=missing_fact_plan.known_facts,
        thread_state=thread_state,
        is_continuation=thread.is_continuation,
    )
    service_type = pipeline_ctx.service_type
    playbook = pipeline_ctx.playbook
    next_step = pipeline_ctx.next_step
    info_plan = build_information_value_plan(
        playbook=playbook,
        next_step=next_step,
        input_data=input_data,
        entities=entities,
        known_fact_fields=missing_fact_plan.known_facts,
        is_followup=thread.is_continuation,
        phone_required_by_profile=False,
        language=language,
    )
    extracted = extract_customer_facts(input_data=input_data, entities=entities)
    invariant = validate_selected_known_invariant(
        selected_questions=info_plan.selected_questions,
        already_known_facts=info_plan.already_known_facts,
        extracted_known_fields=extracted.known_question_fields,
    )
    evidence_invariant = validate_evidence_based_known_facts(
        already_known_facts=info_plan.already_known_facts,
        evidence=pipeline_ctx.fact_evidence,
        selection_reasons=info_plan.selection_reasons,
    )
    playbook_invariant = validate_pipeline_playbook_consistency(
        playbook_id=playbook.playbook_id,
        service_family=playbook.service_family,
        next_step_service_family=next_step.service_family,
        information_plan_playbook_id=info_plan.playbook_id,
    )
    if not invariant.passed or not evidence_invariant.passed or not playbook_invariant.passed:
        return None

    location_phrase = extracted.location_city or extract_city_phrase(text=combined_text, entities=entities)
    if location_phrase and location_phrase.lower() in {"city", "known-city"}:
        location_phrase = None
    case_reference_phrase = extracted.case_reference or normalize_case_reference(combined_text)
    discovery_phrase = extract_discovery_time_phrase(combined_text)

    selected_questions = info_plan.selected_questions
    if discovery_phrase and "discovery_time" in selected_questions:
        selected_questions = tuple(q for q in selected_questions if q != "discovery_time")

    question_surface = build_question_surface_labels(
        selected_questions,
        language=language,
        city_phrase=location_phrase,
        pronoun_register=pronoun_register_for_plan(
            service_family=playbook.service_family,
            language=language,
        ),
        service_family=playbook.service_family,
    )
    ack_mode = acknowledgement_mode_for_thread(
        thread=thread,
        service_family=playbook.service_family,
        next_step_id=next_step.step_id,
    )
    mentions_battery = any(
        token in combined_text.lower() for token in ("batteri", "battery storage", "battery")
    )
    attach_state = attachment_state(combined_text)
    mentions_attachment_gap = attach_state in {"attachment_missing", "attachment_missing_drawing"}
    pronoun = pronoun_register_for_plan(service_family=playbook.service_family, language=language)
    acknowledgement = build_acknowledgement_plan(
        playbook=playbook,
        thread=thread,
        acknowledgement_mode=ack_mode,
        language=language,
        location_phrase=location_phrase,
        case_reference_phrase=case_reference_phrase,
        new_supplied_facts=thread.supplied_facts
        if thread.is_continuation and _continuation_has_new_substance(input_data.get("message_text", ""))
        else (),
        pronoun_register=pronoun,
        mentions_battery=mentions_battery,
        mentions_attachment_gap=mentions_attachment_gap,
        attachment_state=attach_state,
        scenario_family=scenario_family,
        message_text=combined_text,
    )
    verified = _internal_verified_fact_ids(
        service_type=service_type,
        evidence=pipeline_ctx.fact_evidence,
        case_reference_phrase=case_reference_phrase,
    )
    extracted_facts = extract_customer_facts(input_data=input_data, entities=entities)
    solar_verified = existing_solar_verified(
        detect_semantic_fact_ids(combined_text),
        set(extracted_facts.known_question_fields),
    )
    plan = build_customer_reply_plan_v2(
        greeting=greeting,
        signature_name=signature_name,
        playbook=playbook,
        next_step=next_step,
        information_plan=info_plan,
        thread_context=thread,
        acknowledgement_mode=ack_mode,
        verified_fact_labels=verified,
        business_intent=intent,
        tone_profile=tone_profile,
        language=language,
        forbidden_commitments=eligibility.forbidden_commitments,
        acknowledgement_statement=acknowledgement.statement,
        question_surface_labels=question_surface,
        location_phrase=location_phrase,
        case_reference_phrase=case_reference_phrase,
        language_decision_evidence=language_decision.evidence,
        pronoun_register=pronoun,
        scenario_family=scenario_family,
        mentions_attachment_gap=mentions_attachment_gap,
        attachment_state=attach_state,
        existing_solar_verified=solar_verified,
    )
    return plan


def build_and_render_coworker_reply(
    *,
    greeting: str,
    signature_name: str,
    missing_fact_plan: MissingFactPlan,
    eligibility: SafeAckEligibilityResult,
    input_data: dict[str, Any],
    entities: dict[str, Any] | None = None,
    fact_map: dict[str, str | None] | None = None,
    business_intent: str | None = None,
    thread_state: str = "new_thread",
    profile_default_language: str = "sv",
) -> tuple[str, CustomerReplyPlanV2, RenderResult, dict[str, Any]] | None:
    plan_v2 = build_coworker_reply_plan_v2(
        greeting=greeting,
        signature_name=signature_name,
        missing_fact_plan=missing_fact_plan,
        eligibility=eligibility,
        input_data=input_data,
        entities=entities,
        fact_map=fact_map,
        business_intent=business_intent,
        thread_state=thread_state,
        profile_default_language=profile_default_language,
    )
    if plan_v2 is None:
        return None

    render = render_coworker_reply_with_validation(plan_v2)
    service_hint = _resolve_service_hint(
        service_type=missing_fact_plan.service_type,
        entities=dict(entities or {}),
        fact_map=dict(fact_map or {}),
    )
    location_hint = _resolve_location_hint(dict(entities or {}), dict(fact_map or {}))
    plan_v1 = adapt_plan_v2_to_v1(plan_v2, service_hint=service_hint, location_hint=location_hint)
    metadata = {
        "_customer_reply_plan_v2": plan_v2.to_dict(),
        "_customer_reply_plan": plan_v1.to_dict(),
        "_reply_render_provenance": render.provenance.to_dict(),
        "_information_value_plan": {
            "selected_questions": list(plan_v2.selected_questions),
            "selected_question_labels": list(plan_v2.selected_question_labels),
            "question_surface_labels": list(plan_v2.question_surface_labels),
            "evidence": list(plan_v2.evidence),
        },
    }
    return render.body, plan_v2, render, metadata
