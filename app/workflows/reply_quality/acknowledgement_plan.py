"""Evidence-backed acknowledgement planning for customer replies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.workflows.reply_quality.semantic_fact_predicates import (
    detect_consultation_intent,
    is_battery_retrofit_intent,
)
from app.workflows.reply_quality.thread_context import ThreadReplyContext

POLICY_VERSION = "acknowledgement_plan_v2"

_FOLLOWUP_ACK_TOKENS_SV = ("igen", "återkomst", "uppföljning", "kompletterande")
_FOLLOWUP_ACK_TOKENS_EN = ("again", "follow-up", "follow up", "additional information")


def _continuation_ack_allowed(*, thread: ThreadReplyContext, message_text: str = "") -> bool:
    """Follow-up acknowledgement wording requires verified continuation evidence."""
    if thread.is_continuation:
        return True
    lowered = (message_text or "").lower()
    if any(token in lowered for token in ("kompletterande", "following up", "follow-up", "follow up", "bifogar nu")):
        return True
    return False


def _contains_followup_ack_tokens(statement: str, *, language: str) -> bool:
    lowered = (statement or "").lower()
    tokens = _FOLLOWUP_ACK_TOKENS_EN if language == "en" else _FOLLOWUP_ACK_TOKENS_SV
    return any(token in lowered for token in tokens)


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
    pronoun_register: str = "ni",
    mentions_battery: bool = False,
    mentions_attachment_gap: bool = False,
    attachment_state: str | None = None,
    scenario_family: str | None = None,
    message_text: str = "",
) -> AcknowledgementPlan:
    family = playbook.service_family
    service = _service_phrase(family=family, language=language)
    claims: list[str] = []
    evidence: list[str] = []
    register = pronoun_register if language == "sv" else "you"

    if family == "job_status" and case_reference_phrase:
        if language == "en":
            statement = (
                f"Thank you for your question about the status of case {case_reference_phrase}."
            )
        else:
            statement = (
                f"Vi har tagit emot er fråga om status för ärende {case_reference_phrase}."
                if register == "ni"
                else f"Vi har tagit emot din fråga om status för ärende {case_reference_phrase}."
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
            else (
                "Vi har tagit emot er statusförfrågan och kontrollerar ärendet."
                if register == "ni"
                else "Vi har tagit emot din statusförfrågan och kontrollerar ärendet."
            )
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
            else (
                "Tack för att ni kontaktar oss om reklamationen."
                if register == "ni"
                else "Tack för att du kontaktar oss om reklamationen."
            )
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
        followup_family = bool(
            scenario_family
            and scenario_family.endswith("_followup")
            and _continuation_ack_allowed(thread=thread, message_text=message_text)
        )
        if thread.is_continuation:
            if language == "en":
                statement = (
                    "Thanks for following up on the support case."
                    if followup_family
                    else "Thanks for the follow-up about the fault on your installation."
                )
            elif followup_family:
                statement = (
                    "Tack för att du följer upp det befintliga supportärendet."
                    if register == "du"
                    else "Tack för att ni följer upp det befintliga supportärendet."
                )
            else:
                statement = "Tack för uppföljningen om felet på den befintliga anläggningen."
            claims.append("support_follow_up")
            evidence.append("thread:continuation")
        else:
            if language == "en":
                statement = (
                    "Thank you for contacting us again about the fault."
                    if followup_family
                    else "Thank you for contacting us about your existing installation."
                )
            elif followup_family:
                statement = (
                    "Tack för att du hör av dig igen om felet på den befintliga anläggningen."
                    if register == "du"
                    else "Tack för att ni hör av er igen om felet på den befintliga anläggningen."
                )
            elif register == "du":
                statement = "Tack för att du hör av dig om din befintliga anläggning."
            else:
                statement = "Tack för att ni hör av er om er befintliga anläggning."
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
        followup_family = bool(scenario_family and scenario_family.endswith("_followup"))
        if family == "solar_installation":
            if followup_family:
                statement = (
                    "Thanks for following up on your solar quote request."
                    if language == "en"
                    else (
                        "Tack för att ni följer upp er solcellsförfrågan."
                        if register == "ni"
                        else "Tack för att du följer upp din solcellsförfrågan."
                    )
                )
            elif mentions_battery:
                statement = (
                    "Thanks for following up on your solar and battery enquiry."
                    if language == "en"
                    else (
                        "Tack för er uppföljning om solceller och batteri."
                        if register == "ni"
                        else "Tack för din uppföljning om solceller och batteri."
                    )
                )
            else:
                statement = (
                    "Thanks for following up on your solar enquiry."
                    if language == "en"
                    else (
                        "Tack för er uppföljning om solcellerna."
                        if register == "ni"
                        else "Tack för din uppföljning om solcellerna."
                    )
                )
        elif family == "battery_installation":
            statement = (
                "Thanks for following up on the battery enquiry."
                if language == "en"
                else (
                "Tack för er uppföljning om batterilösningen."
                if register == "ni"
                else "Tack för din uppföljning om batterilösningen."
            )
            )
        elif family == "ev_charger":
            statement = (
                "Thanks for following up on the charger enquiry."
                if language == "en"
                else (
                "Tack för er uppföljning om laddboxen."
                if register == "ni"
                else "Tack för din uppföljning om laddboxen."
            )
            )
        else:
            statement = (
                "Thanks for your follow-up."
                if language == "en"
                else (
                "Tack för att ni följer upp ärendet."
                if register == "ni"
                else "Tack för att du följer upp ärendet."
            )
            )
        if family == "general_consultation":
            statement = (
                "Thanks for your follow-up message."
                if language == "en"
                else (
                "Tack för er uppföljning av meddelandet."
                if register == "ni"
                else "Tack för din uppföljning av meddelandet."
            )
            )
        claims.append("thread_follow_up")
        evidence.append("thread:continuation")
        return AcknowledgementPlan(
            statement=statement,
            claims=tuple(claims),
            evidence=tuple(evidence),
            policy_version=POLICY_VERSION,
        )

    if mentions_attachment_gap and family in {"solar_installation", "ev_charger"}:
        if family == "ev_charger":
            statement = (
                "Thank you for your charger enquiry. We note the photos are not attached yet."
                if language == "en"
                else (
                    "Tack för er förfrågan om laddbox. Vi ser att bilderna ännu inte är bifogade."
                    if register == "ni"
                    else "Tack för din förfrågan om laddbox. Vi ser att bilderna ännu inte är bifogade."
                )
            )
        else:
            statement = (
                "Thank you for your enquiry. We note the drawing is not attached yet."
                if language == "en"
                else (
                    "Tack för er förfrågan. Vi ser att ritningen ännu inte är bifogad."
                    if register == "ni"
                    else "Tack för din förfrågan. Vi ser att ritningen ännu inte är bifogad."
                )
            )
        claims.append("attachment_gap_acknowledged")
        evidence.append("input:missing_attachment")
        return AcknowledgementPlan(
            statement=statement,
            claims=tuple(claims),
            evidence=tuple(evidence),
            policy_version=POLICY_VERSION,
        )

    if attachment_state == "attachment_promised":
        if family == "ev_charger":
            statement = (
                "Thank you for your charger enquiry. We note you will attach supporting documents."
                if language == "en"
                else (
                    "Tack för er förfrågan om laddbox. Vi noterar att ni återkommer med bifogat underlag."
                    if register == "ni"
                    else "Tack för din förfrågan om laddbox. Vi noterar att du återkommer med bifogat underlag."
                )
            )
        else:
            statement = (
                "Thank you for your enquiry. We note you will attach supporting documents."
                if language == "en"
                else (
                    "Tack för er förfrågan. Vi noterar att ni återkommer med bifogat underlag."
                    if register == "ni"
                    else "Tack för din förfrågan. Vi noterar att du återkommer med bifogat underlag."
                )
            )
        claims.append("attachment_promised_acknowledged")
        evidence.append("input:attachment_promised")
        return AcknowledgementPlan(
            statement=statement,
            claims=tuple(claims),
            evidence=tuple(evidence),
            policy_version=POLICY_VERSION,
        )

    if detect_consultation_intent(message_text) == "consultation_booking":
        statement = (
            "We'd be happy to help prepare a short consultation call about solar, battery and charging."
            if language == "en"
            else (
                "Vi hjälper gärna till att förbereda ett kort samtal om solceller, batteri och laddning."
                if register == "ni"
                else "Vi hjälper gärna till att förbereda ett kort samtal om solceller, batteri och laddning."
            )
        )
        claims.append("booking_request_acknowledged")
        evidence.append("intent:consultation_booking")
        return AcknowledgementPlan(
            statement=statement,
            claims=tuple(claims),
            evidence=tuple(evidence),
            policy_version=POLICY_VERSION,
        )

    if family == "general_consultation":
        statement = (
            "Thank you for your consultation enquiry."
            if language == "en"
            else (
                "Tack för er förfrågan om rådgivning."
                if register == "ni"
                else "Tack för din förfrågan om rådgivning."
            )
        )
        claims.append("consultation_received")
        evidence.append("intent:general_consultation")
        return AcknowledgementPlan(
            statement=statement,
            claims=tuple(claims),
            evidence=tuple(evidence),
            policy_version=POLICY_VERSION,
        )

    if location_phrase and family == "solar_installation":
        if mentions_battery:
            statement = (
                f"Thank you for getting in touch about solar panels and battery storage in {location_phrase}."
                if language == "en"
                else f"Tack för att ni hör av er om solceller och batteri i {location_phrase}."
            )
        else:
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
            else (
            "Tack för er statusförfrågan."
            if register == "ni"
            else "Tack för din statusförfrågan."
        )
        )
    elif family == "battery_installation":
        if is_battery_retrofit_intent(message_text):
            if location_phrase:
                statement = (
                    f"Thank you for getting in touch about adding battery storage to your solar panels in {location_phrase}."
                    if language == "en"
                    else f"Tack för att ni hör av er om att komplettera solcellerna med batteri i {location_phrase}."
                )
            else:
                statement = (
                    "Thank you for getting in touch about adding battery storage to your existing solar installation."
                    if language == "en"
                    else (
                        "Tack för att ni hör av er om att komplettera befintliga solceller med batterilager."
                        if register == "ni"
                        else "Tack för att du hör av dig om att komplettera befintliga solceller med batterilager."
                    )
                )
        else:
            statement = (
                "Thank you for your enquiry about battery storage."
                if language == "en"
                else (
                    "Tack för att ni hör av er om batterilager."
                    if register == "ni"
                    else "Tack för att du hör av dig om batterilager."
                )
            )
    elif family == "ev_charger":
        statement = (
            "Thank you for your enquiry about an EV charger."
            if language == "en"
            else (
            "Tack för er förfrågan om laddbox."
            if register == "ni"
            else "Tack för din förfrågan om laddbox."
        )
        )
    elif family == "solar_installation":
        followup_family = bool(
            scenario_family
            and scenario_family.endswith("_followup")
            and _continuation_ack_allowed(thread=thread, message_text=message_text)
        )
        if followup_family:
            statement = (
                "Thank you for getting back to us about the solar quote."
                if language == "en"
                else (
                    "Tack för er återkomst om solcellsofferten."
                    if register == "ni"
                    else "Tack för din återkomst om solcellsofferten."
                )
            )
        else:
            statement = (
                "Thank you for your solar installation enquiry."
                if language == "en"
                else (
                    "Tack för er förfrågan om solcellsinstallation."
                    if register == "ni"
                    else "Tack för din förfrågan om solcellsinstallation."
                )
            )
    else:
        statement = (
            "Thank you for your message."
            if language == "en"
            else (
            "Tack för ert meddelande."
            if register == "ni"
            else "Tack för ditt meddelande."
        )
        )

    claims.append("first_contact_acknowledgement")
    evidence.append(f"mode:{acknowledgement_mode}")
    if not _continuation_ack_allowed(thread=thread, message_text=message_text) and _contains_followup_ack_tokens(
        statement, language=language
    ):
        if family == "solar_installation":
            statement = (
                "Thank you for your solar installation enquiry."
                if language == "en"
                else (
                    "Tack för er förfrågan om solcellsinstallation."
                    if register == "ni"
                    else "Tack för din förfrågan om solcellsinstallation."
                )
            )
        elif family == "existing_installation_support":
            statement = (
                "Thank you for contacting us about your existing installation."
                if language == "en"
                else (
                    "Tack för att ni hör av er om er befintliga anläggning."
                    if register == "ni"
                    else "Tack för att du hör av dig om din befintliga anläggning."
                )
            )
        evidence.append("thread:new_thread_no_followup_wording")
    return AcknowledgementPlan(
        statement=statement,
        claims=tuple(claims),
        evidence=tuple(evidence),
        policy_version=POLICY_VERSION,
    )
