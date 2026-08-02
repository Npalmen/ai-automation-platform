"""Unified reply pipeline routing before plan surfaces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.workflows.reply_quality.fact_evidence import FactEvidenceSnapshot, build_fact_evidence
from app.workflows.reply_quality.operational_next_step import OperationalNextStep, select_operational_next_step
from app.workflows.reply_quality.semantic_fact_predicates import (
    detect_consultation_intent,
    is_battery_retrofit_intent,
)
from app.workflows.reply_quality.service_playbooks import (
    ReplyServicePlaybook,
    get_consultation_playbook,
    get_reply_playbook,
)

POLICY_VERSION = "pipeline_routing_v1"


@dataclass(frozen=True)
class ReplyPipelineContext:
    service_type: str
    playbook: ReplyServicePlaybook
    next_step: OperationalNextStep
    consultation_intent: str | None
    fact_evidence: FactEvidenceSnapshot
    business_intent: str
    policy_version: str = POLICY_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "service_type": self.service_type,
            "playbook_id": self.playbook.playbook_id,
            "service_family": self.playbook.service_family,
            "next_step": self.next_step.to_dict(),
            "consultation_intent": self.consultation_intent,
            "fact_evidence": self.fact_evidence.to_dict(),
            "business_intent": self.business_intent,
            "policy_version": self.policy_version,
        }


def resolve_routed_service_type(
    *,
    base_service_type: str,
    message_text: str,
    subject: str = "",
) -> str:
    combined = f"{subject or ''} {message_text or ''}"
    if is_battery_retrofit_intent(combined):
        return "battery_storage"
    return base_service_type


def resolve_reply_pipeline_context(
    *,
    base_service_type: str,
    business_intent: str | None,
    input_data: dict[str, Any],
    entities: dict[str, Any] | None = None,
    known_fact_fields: tuple[str, ...] = (),
    thread_state: str = "new_thread",
    is_continuation: bool = False,
) -> ReplyPipelineContext:
    entities = dict(entities or {})
    combined = f"{input_data.get('subject') or ''} {input_data.get('message_text') or ''}"
    intent = business_intent or "lead"
    consultation_intent = detect_consultation_intent(combined)
    service_type = resolve_routed_service_type(
        base_service_type=base_service_type,
        message_text=input_data.get("message_text", "") or "",
        subject=input_data.get("subject", "") or "",
    )
    if consultation_intent:
        playbook = get_consultation_playbook(consultation_intent)
    else:
        playbook = get_reply_playbook(service_type, business_intent=intent)
    next_step = select_operational_next_step(
        service_type=service_type,
        business_intent=intent,
        thread_state=thread_state,
        is_continuation=is_continuation,
    )
    if next_step.service_family != playbook.service_family:
        next_step = OperationalNextStep(
            step_id=next_step.step_id,
            service_family=playbook.service_family,
            business_intent=next_step.business_intent,
            rationale=f"{next_step.rationale};family_aligned={playbook.playbook_id}",
            policy_version=next_step.policy_version,
        )
    evidence = build_fact_evidence(
        input_data=input_data,
        entities=entities,
        known_fact_fields=known_fact_fields,
    )
    return ReplyPipelineContext(
        service_type=service_type,
        playbook=playbook,
        next_step=next_step,
        consultation_intent=consultation_intent,
        fact_evidence=evidence,
        business_intent=intent,
    )
