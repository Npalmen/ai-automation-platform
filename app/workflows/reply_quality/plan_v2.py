"""CustomerReplyPlanV2 structured reply contract (Todo D)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.workflows.reply_planning import CustomerReplyPlan
from app.workflows.reply_quality.information_value import InformationValuePlan
from app.workflows.reply_quality.operational_next_step import OperationalNextStep
from app.workflows.reply_quality.service_playbooks import ReplyServicePlaybook
from app.workflows.reply_quality.thread_context import ThreadReplyContext

POLICY_VERSION = "customer_reply_plan_v2"


@dataclass(frozen=True)
class CustomerReplyPlanV2:
    response_objective: str
    acknowledgement_mode: str
    service_family: str
    business_intent: str
    verified_facts: tuple[str, ...]
    facts_not_allowed_to_repeat: tuple[str, ...]
    selected_questions: tuple[str, ...]
    selected_question_labels: tuple[str, ...]
    next_step_statement: str
    commitment_constraints: tuple[str, ...]
    tone_profile: str
    language: str
    greeting: str
    signature_name: str
    salutation_strategy: str
    closing_strategy: str
    thread_context: ThreadReplyContext
    rendering_constraints: tuple[str, ...]
    fallback_reason: str | None
    evidence: tuple[str, ...]
    playbook_id: str
    policy_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "response_objective": self.response_objective,
            "acknowledgement_mode": self.acknowledgement_mode,
            "service_family": self.service_family,
            "business_intent": self.business_intent,
            "verified_facts": list(self.verified_facts),
            "facts_not_allowed_to_repeat": list(self.facts_not_allowed_to_repeat),
            "selected_questions": list(self.selected_questions),
            "selected_question_labels": list(self.selected_question_labels),
            "next_step_statement": self.next_step_statement,
            "commitment_constraints": list(self.commitment_constraints),
            "tone_profile": self.tone_profile,
            "language": self.language,
            "greeting": self.greeting,
            "signature_name": self.signature_name,
            "salutation_strategy": self.salutation_strategy,
            "closing_strategy": self.closing_strategy,
            "thread_context": self.thread_context.to_dict(),
            "rendering_constraints": list(self.rendering_constraints),
            "fallback_reason": self.fallback_reason,
            "evidence": list(self.evidence),
            "playbook_id": self.playbook_id,
            "policy_version": self.policy_version,
        }


def build_customer_reply_plan_v2(
    *,
    greeting: str,
    signature_name: str,
    playbook: ReplyServicePlaybook,
    next_step: OperationalNextStep,
    information_plan: InformationValuePlan,
    thread_context: ThreadReplyContext,
    acknowledgement_mode: str,
    verified_fact_labels: tuple[str, ...],
    business_intent: str,
    tone_profile: str = "professional_concise",
    language: str = "sv",
    forbidden_commitments: tuple[str, ...] = (),
    fallback_reason: str | None = None,
) -> CustomerReplyPlanV2:
    from app.workflows.reply_quality.operational_next_step import next_step_wording

    return CustomerReplyPlanV2(
        response_objective=next_step.step_id,
        acknowledgement_mode=acknowledgement_mode,
        service_family=playbook.service_family,
        business_intent=business_intent,
        verified_facts=verified_fact_labels,
        facts_not_allowed_to_repeat=information_plan.already_known_facts,
        selected_questions=information_plan.selected_questions,
        selected_question_labels=information_plan.selected_question_labels,
        next_step_statement=next_step_wording(next_step, language=language),
        commitment_constraints=forbidden_commitments,
        tone_profile=tone_profile,
        language=language,
        greeting=greeting,
        signature_name=signature_name,
        salutation_strategy="first_name_when_known",
        closing_strategy="profile_signature",
        thread_context=thread_context,
        rendering_constraints=(
            "no_new_facts",
            "no_extra_questions",
            "no_forbidden_commitments",
            "no_internal_notes",
        ),
        fallback_reason=fallback_reason,
        evidence=information_plan.selection_reasons,
        playbook_id=playbook.playbook_id,
        policy_version=POLICY_VERSION,
    )


def adapt_plan_v2_to_v1(plan_v2: CustomerReplyPlanV2, *, service_hint: str, location_hint: str) -> CustomerReplyPlan:
    return CustomerReplyPlan(
        acknowledgement_intent=plan_v2.acknowledgement_mode,
        verified_facts=plan_v2.verified_facts,
        service_hint=service_hint,
        location_hint=location_hint,
        missing_questions=plan_v2.selected_question_labels,
        forbidden_commitments=plan_v2.commitment_constraints,
        language=plan_v2.language,
        tone=plan_v2.tone_profile,
        next_step_wording=plan_v2.next_step_statement,
        greeting=plan_v2.greeting,
        signature_name=plan_v2.signature_name,
        profile_service_type=plan_v2.service_family,
        fallback_template_key="digital_coworker_v1",
        plan_provenance=(
            f"plan_v2:{plan_v2.policy_version}",
            f"playbook:{plan_v2.playbook_id}",
            f"objective:{plan_v2.response_objective}",
            *plan_v2.evidence[:5],
        ),
        policy_version=POLICY_VERSION,
    )
