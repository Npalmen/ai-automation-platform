"""Evidence-backed acknowledgement planning for customer replies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.workflows.reply_quality.service_playbooks import ReplyServicePlaybook
from app.workflows.reply_quality.thread_context import ThreadReplyContext

POLICY_VERSION = "acknowledgement_plan_v1"


@dataclass(frozen=True)
class AcknowledgementPlan:
    statement: str
    claims: tuple[str, ...]
    evidence: tuple[str, ...]
    policy_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "claims": list(self.claims),
            "evidence": list(self.evidence),
            "policy_version": self.policy_version,
        }


def _service_phrase(*, family: str, language: str) -> str:
    phrases = {
        "solar_installation": ("solceller", "solar panels"),
        "battery_installation": ("batterilager", "battery storage"),
        "ev_charger": ("laddbox", "an EV charger"),
        "existing_installation_support": ("er befintliga anläggning", "your existing installation"),
        "job_status": ("ärendet", "your case"),
        "complaint_warranty": ("reklamationen", "the complaint"),
        "general_consultation": ("ditt meddelande", "your message"),
        "unknown_service": ("ditt meddelande", "your message"),
    }
    sv, en = phrases.get(family, phrases["unknown_service"])
    return en if language == "en" else sv


def build_acknowledgement_plan(
    *,
    playbook: ReplyServicePlaybook,
    thread: ThreadReplyContext,
    acknowledgement_mode: str,
    language: str,
    location_phrase: str | None = None,
    case_reference_phrase: str | None = None,
    new_supplied_facts: tuple[str, ...] = (),
) -> AcknowledgementPlan:
    family = playbook.service_family
    service = _service_phrase(family=family, language=language)
    claims: list[str] = []
    evidence: list[str] = []

    if family == "job_status" and case_reference_phrase:
        if language == "en":
            statement = (
                f"Thank you for your question about the status of case {case_reference_phrase}."
            )
        else:
            statement = (
                f"Vi har tagit emot din fråga om status för ärende {case_reference_phrase}."
            )
        claims.append("status_request_with_case_reference")
        evidence.append(f"case_reference:{case_reference_phrase}")
        return AcknowledgementPlan(
            statement=statement,
            claims=tuple(claims),
            evidence=tuple(evidence),
            policy_version=POLICY_VERSION,
        )

    if family == "job_status":
        statement = (
            "We have received your status request and will check the case."
            if language == "en"
            else "Vi har tagit emot din statusförfrågan och kontrollerar ärendet."
        )
        claims.append("status_request")
        evidence.append("intent:job_status")
        return AcknowledgementPlan(
            statement=statement,
            claims=tuple(claims),
            evidence=tuple(evidence),
            policy_version=POLICY_VERSION,
        )

    if family == "complaint_warranty":
        statement = (
            "Thank you for contacting us about the complaint."
            if language == "en"
            else "Tack för att du kontaktar oss om reklamationen."
        )
        claims.append("complaint_received")
        evidence.append("intent:complaint_warranty")
        return AcknowledgementPlan(
            statement=statement,
            claims=tuple(claims),
            evidence=tuple(evidence),
            policy_version=POLICY_VERSION,
        )

    if family == "existing_installation_support":
        if thread.is_continuation:
            statement = (
                "Thanks for the follow-up about the fault on your installation."
                if language == "en"
                else "Tack för uppföljningen om felet på den befintliga anläggningen."
            )
            claims.append("support_follow_up")
            evidence.append("thread:continuation")
        else:
            statement = (
                "Thank you for contacting us about your existing installation."
                if language == "en"
                else "Tack för att du hör av dig om er befintliga anläggning."
            )
            claims.append("support_new_contact")
            evidence.append("thread:new_thread")
        return AcknowledgementPlan(
            statement=statement,
            claims=tuple(claims),
            evidence=tuple(evidence),
            policy_version=POLICY_VERSION,
        )

    if thread.is_continuation and new_supplied_facts:
        if language == "en":
            statement = "Thanks for the additional information."
        else:
            statement = "Tack för den kompletterande informationen."
        claims.append("continuation_with_new_facts")
        evidence.extend(f"new_fact:{fact}" for fact in new_supplied_facts)
        return AcknowledgementPlan(
            statement=statement,
            claims=tuple(claims),
            evidence=tuple(evidence),
            policy_version=POLICY_VERSION,
        )

    if thread.is_continuation:
        if family == "solar_installation":
            statement = (
                "Thanks for following up on your solar enquiry."
                if language == "en"
                else "Tack för din uppföljning om solcellerna."
            )
        elif family == "battery_installation":
            statement = (
                "Thanks for following up on the battery enquiry."
                if language == "en"
                else "Tack för din uppföljning om batterilösningen."
            )
        elif family == "ev_charger":
            statement = (
                "Thanks for following up on the charger enquiry."
                if language == "en"
                else "Tack för din uppföljning om laddboxen."
            )
        else:
            statement = (
                "Thanks for your follow-up."
                if language == "en"
                else "Tack för att du följer upp ärendet."
            )
        if family == "general_consultation":
            statement = (
                "Thanks for your follow-up message."
                if language == "en"
                else "Tack för din uppföljning av meddelandet."
            )
        claims.append("thread_follow_up")
        evidence.append("thread:continuation")
        return AcknowledgementPlan(
            statement=statement,
            claims=tuple(claims),
            evidence=tuple(evidence),
            policy_version=POLICY_VERSION,
        )

    if location_phrase and family == "solar_installation":
        statement = (
            f"Thank you for getting in touch about solar panels in {location_phrase}."
            if language == "en"
            else f"Tack för att ni hör av er om solceller i {location_phrase}."
        )
        claims.append("solar_lead_with_location")
        evidence.append(f"location:{location_phrase}")
        return AcknowledgementPlan(
            statement=statement,
            claims=tuple(claims),
            evidence=tuple(evidence),
            policy_version=POLICY_VERSION,
        )

    if acknowledgement_mode == "status_acknowledgement":
        statement = (
            "Thank you for your status request."
            if language == "en"
            else "Tack för din statusförfrågan."
        )
    elif family == "battery_installation":
        statement = (
            "Thank you for your enquiry about battery storage."
            if language == "en"
            else "Tack för att du hör av dig om batterilager."
        )
    elif family == "ev_charger":
        statement = (
            "Thank you for your enquiry about an EV charger."
            if language == "en"
            else "Tack för din förfrågan om laddbox."
        )
    elif family == "solar_installation":
        statement = (
            "Thank you for your solar installation enquiry."
            if language == "en"
            else "Tack för din förfrågan om solcellsinstallation."
        )
    else:
        statement = (
            "Thank you for your message."
            if language == "en"
            else "Tack för ditt meddelande."
        )

    claims.append("first_contact_acknowledgement")
    evidence.append(f"mode:{acknowledgement_mode}")
    return AcknowledgementPlan(
        statement=statement,
        claims=tuple(claims),
        evidence=tuple(evidence),
        policy_version=POLICY_VERSION,
    )
