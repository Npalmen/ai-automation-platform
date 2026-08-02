"""Operational next-step selection (Todo B)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.workflows.reply_quality.service_playbooks import ReplyServicePlaybook, get_reply_playbook

POLICY_VERSION = "operational_next_step_v1"


@dataclass(frozen=True)
class OperationalNextStep:
    step_id: str
    service_family: str
    business_intent: str
    rationale: str
    policy_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "service_family": self.service_family,
            "business_intent": self.business_intent,
            "rationale": self.rationale,
            "policy_version": self.policy_version,
        }


def select_operational_next_step(
    *,
    service_type: str,
    business_intent: str | None,
    thread_state: str = "new_thread",
    is_continuation: bool = False,
    threat_class: str | None = None,
) -> OperationalNextStep:
    playbook = get_reply_playbook(service_type, business_intent=business_intent)
    intent = business_intent or "lead"
    family = playbook.service_family

    if threat_class in {"phishing", "injection", "malware"}:
        return OperationalNextStep(
            step_id="decline_or_no_reply",
            service_family=family,
            business_intent=intent,
            rationale=f"threat:{threat_class}",
            policy_version=POLICY_VERSION,
        )

    if family == "job_status":
        step = "provide_status_acknowledgement"
    elif family == "complaint_warranty":
        step = "route_to_manual_technical_review"
    elif family == "existing_installation_support":
        step = "collect_symptom_facts"
    elif is_continuation or thread_state in {"continuation", "out_of_order"}:
        step = "collect_minimum_site_facts" if intent.startswith("lead") else "confirm_case_receipt_only"
    elif intent in {"ambiguous_short", "ambiguous_mixed"}:
        step = "clarify_service_scope"
    else:
        step = playbook.next_step_options[0]

    return OperationalNextStep(
        step_id=step,
        service_family=family,
        business_intent=intent,
        rationale=f"playbook={playbook.playbook_id};thread={thread_state}",
        policy_version=POLICY_VERSION,
    )


def next_step_wording(step: OperationalNextStep, *, language: str = "sv") -> str:
    phrases = {
        "collect_minimum_site_facts": (
            "Nästa steg är att samla in underlag så vi kan bedöma förutsättningarna."
        ),
        "collect_symptom_facts": (
            "För att felsöka vidare behöver vi lite mer information om felet."
        ),
        "clarify_service_scope": (
            "Berätta gärna lite mer om vad du behöver hjälp med så vi kan vägleda rätt."
        ),
        "provide_status_acknowledgement": (
            "Vi tar emot din statusförfrågan och återkommer när vi har kollat ärendet."
        ),
        "route_to_manual_technical_review": (
            "Vi tar emot ärendet och en kollega tittar på det manuellt."
        ),
        "confirm_case_receipt_only": (
            "Vi har noterat din uppdatering och återkommer om vi behöver mer."
        ),
        "collect_contact_preference": (
            "Skicka gärna hur vi bäst når dig om vi behöver följa upp."
        ),
        "decline_or_no_reply": (
            "Ärendet hanteras inte automatiskt."
        ),
    }
    return phrases.get(step.step_id, "Vi återkommer när vi har gått igenom underlaget.")
