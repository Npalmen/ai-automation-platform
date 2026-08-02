"""End-to-end digital coworker reply build and render pipeline."""

from __future__ import annotations

from typing import Any

from app.workflows.missing_fact_plan import MissingFactPlan
from app.workflows.reply_planning import _resolve_location_hint, _resolve_service_hint
from app.workflows.reply_quality.information_value import build_information_value_plan
from app.workflows.reply_quality.operational_next_step import select_operational_next_step
from app.workflows.reply_quality.plan_v2 import (
    CustomerReplyPlanV2,
    adapt_plan_v2_to_v1,
    build_customer_reply_plan_v2,
)
from app.workflows.reply_quality.renderer import RenderResult, render_coworker_reply_with_validation
from app.workflows.reply_quality.service_playbooks import get_reply_playbook
from app.workflows.reply_quality.thread_context import (
    acknowledgement_mode_for_thread,
    build_thread_reply_context,
)
from app.workflows.safe_ack_eligibility import SafeAckEligibilityResult


def _verified_fact_labels(
    *,
    service_hint: str,
    location_hint: str,
    known_fields: tuple[str, ...],
) -> tuple[str, ...]:
    labels: list[str] = []
    if service_hint and service_hint != "din förfrågan":
        labels.append(f"service:{service_hint}")
    if location_hint:
        labels.append(f"location:{location_hint}")
    for field in known_fields:
        labels.append(field.replace("_", " "))
    return tuple(labels)


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
) -> CustomerReplyPlanV2 | None:
    language = str(input_data.get("language") or language)
    if scenario_input_language := input_data.get("_scenario_language"):
        language = str(scenario_input_language)
    if not eligibility.eligible:
        return None

    entities = dict(entities or {})
    fact_map = dict(fact_map or {})
    service_type = str(input_data.get("_force_service_type") or missing_fact_plan.service_type)
    intent = business_intent or "lead"

    playbook = get_reply_playbook(service_type, business_intent=intent)
    thread = build_thread_reply_context(
        thread_state=thread_state,
        prior_safe_ack=thread_state == "continuation",
        supplied_facts=missing_fact_plan.known_facts,
    )
    next_step = select_operational_next_step(
        service_type=service_type,
        business_intent=intent,
        thread_state=thread_state,
        is_continuation=thread.is_continuation,
    )
    info_plan = build_information_value_plan(
        playbook=playbook,
        next_step=next_step,
        input_data=input_data,
        entities=entities,
        known_fact_fields=missing_fact_plan.known_facts,
        is_followup=thread.is_continuation,
        phone_required_by_profile=False,
    )
    service_hint = _resolve_service_hint(
        service_type=service_type,
        entities=entities,
        fact_map=fact_map,
    )
    location_hint = _resolve_location_hint(entities, fact_map)
    ack_mode = acknowledgement_mode_for_thread(
        thread=thread,
        service_family=playbook.service_family,
        next_step_id=next_step.step_id,
    )
    verified = _verified_fact_labels(
        service_hint=service_hint,
        location_hint=location_hint,
        known_fields=info_plan.already_known_facts,
    )
    return build_customer_reply_plan_v2(
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
    )


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
            "evidence": list(plan_v2.evidence),
        },
    }
    return render.body, plan_v2, render, metadata
