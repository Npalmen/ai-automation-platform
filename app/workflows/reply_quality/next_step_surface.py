"""Plan-driven next-step surface contracts for coworker replies."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


POLICY_VERSION = "next_step_surface_v2"

_GENERIC_NEXT_STEP_SV = (
    "När vi har det underlaget går vi igenom förutsättningarna och återkommer."
)
_GENERIC_NEXT_STEP_EN = (
    "Once we have that information, we will review the site conditions and get back to you."
)


@dataclass(frozen=True)
class NextStepSurfaceContract:
    """Structured contract exposed to the LLM renderer."""

    statement: str
    operational_summary: str
    actor: str
    prerequisite: str
    must_not_promise: tuple[str, ...]
    policy_version: str = POLICY_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "operational_summary": self.operational_summary,
            "actor": self.actor,
            "prerequisite": self.prerequisite,
            "must_not_promise": list(self.must_not_promise),
            "policy_version": self.policy_version,
        }


def _is_followup_family(scenario_family: str | None) -> bool:
    return bool(scenario_family and scenario_family.endswith("_followup"))


def build_next_step_surface(
    *,
    step_id: str,
    service_family: str,
    business_intent: str,
    thread_state: str,
    is_continuation: bool,
    has_questions: bool,
    language: str,
    scenario_family: str | None = None,
    mentions_attachment_gap: bool = False,
    attachment_state: str | None = None,
) -> NextStepSurfaceContract:
    """Return a service-specific next-step contract; avoid generic filler when possible."""
    lang = "en" if (language or "sv").lower().startswith("en") else "sv"
    followup = _is_followup_family(scenario_family)

    if attachment_state in {"attachment_claimed_kwh", "attachment_present_kwh"}:
        if lang == "en":
            stmt = "We will review the consumption details and continue the assessment."
        else:
            stmt = "Vi går igenom förbrukningsuppgifterna och fortsätter bedömningen."
        return NextStepSurfaceContract(
            statement=stmt,
            operational_summary="review attached consumption data",
            actor="operator",
            prerequisite="annual consumption details",
            must_not_promise=("quote_amount", "installation_date"),
        )

    if attachment_state == "attachment_promised":
        if lang == "en":
            stmt = "Please attach the file when you can and we will continue once it arrives."
        else:
            stmt = "Bifoga gärna filen när ni kan så fortsätter vi så fort den kommit in."
        return NextStepSurfaceContract(
            statement=stmt,
            operational_summary="await promised attachment",
            actor="customer",
            prerequisite="promised attachment",
            must_not_promise=("quote_amount", "installation_date"),
        )

    if mentions_attachment_gap or step_id == "request_missing_attachment":
        if attachment_state == "attachment_missing_drawing":
            if lang == "en":
                return NextStepSurfaceContract(
                    statement="Please attach the roof drawing when you can and we will continue the quote assessment.",
                    operational_summary="request missing roof drawing before proceeding",
                    actor="customer",
                    prerequisite="roof drawing attachment",
                    must_not_promise=("booking", "quote_amount", "installation_date"),
                )
            return NextStepSurfaceContract(
                statement="Bifoga gärna takritningen så fort det går så fortsätter vi offertbedömningen.",
                operational_summary="be om saknad takritning innan vidare hantering",
                actor="customer",
                prerequisite="saknad takritning",
                must_not_promise=("bokning", "offertbelopp", "installationsdatum"),
            )
        if is_continuation:
            if lang == "en":
                return NextStepSurfaceContract(
                    statement="Please resend the file and we will continue once it arrives.",
                    operational_summary="request missing attachment before proceeding",
                    actor="customer",
                    prerequisite="missing attachment",
                    must_not_promise=("booking", "quote_amount", "installation_date"),
                )
            return NextStepSurfaceContract(
                statement="Skicka gärna filen igen så fortsätter vi behandlingen när den kommit in.",
                operational_summary="be om saknad bilaga innan vidare hantering",
                actor="customer",
                prerequisite="saknad bilaga",
                must_not_promise=("bokning", "offertbelopp", "installationsdatum"),
            )
        if lang == "en":
            return NextStepSurfaceContract(
                statement="Please attach the missing file when you can and we will continue the assessment.",
                operational_summary="request first-time attachment before proceeding",
                actor="customer",
                prerequisite="missing attachment",
                must_not_promise=("booking", "quote_amount", "installation_date"),
            )
        return NextStepSurfaceContract(
            statement="Bifoga gärna den saknade filen så fort det går så fortsätter vi bedömningen.",
            operational_summary="be om första bilaga innan vidare hantering",
            actor="customer",
            prerequisite="saknad bilaga",
            must_not_promise=("bokning", "offertbelopp", "installationsdatum"),
        )

    if service_family == "job_status" or step_id == "provide_status_acknowledgement":
        if scenario_family == "job_status_no_contact":
            if lang == "en":
                stmt = "We will check the case status and get back to you."
            else:
                stmt = "Vi kontrollerar ärendets status och återkommer till dig."
            return NextStepSurfaceContract(
                statement=stmt,
                operational_summary="check status without requesting contact details",
                actor="operator",
                prerequisite="case reference",
                must_not_promise=("exact_completion_time", "guaranteed_outcome"),
            )
        if lang == "en":
            return NextStepSurfaceContract(
                statement="We will check the current case status and get back to you.",
                operational_summary="check case status and respond",
                actor="operator",
                prerequisite="case reference if available",
                must_not_promise=("exact_completion_time", "guaranteed_outcome"),
            )
        return NextStepSurfaceContract(
            statement="Vi kontrollerar ärendets aktuella status och återkommer till dig.",
            operational_summary="kontrollera ärendestatus och återkomma",
            actor="operator",
            prerequisite="ärendereferens om tillgänglig",
            must_not_promise=("exakt färdigtid", "garanterat utfall"),
        )

    if service_family == "complaint_warranty" or step_id == "route_to_manual_technical_review":
        if business_intent == "support_complaint" or service_family == "complaint_warranty":
            if lang == "en":
                return NextStepSurfaceContract(
                    statement=(
                        "Once we have the details, a colleague will review the case "
                        "technically and administratively."
                    ),
                    operational_summary="manual complaint review after documentation",
                    actor="operator",
                    prerequisite="complaint documentation",
                    must_not_promise=("warranty_decision", "refund_amount"),
                )
            return NextStepSurfaceContract(
                statement=(
                    "När vi har underlaget gör vi en teknisk och administrativ bedömning "
                    "av reklamationen."
                ),
                operational_summary="manuell reklamationsgranskning efter underlag",
                actor="operator",
                prerequisite="reklamationsunderlag",
                must_not_promise=("garantibeslut", "ersättningsbelopp"),
            )

    if service_family == "existing_installation_support":
        if is_continuation:
            if followup:
                if lang == "en":
                    stmt = (
                        "We will review the new information and decide whether manual "
                        "technical handling is needed."
                    )
                else:
                    stmt = (
                        "Vi ser över den nya informationen och avgör om manuell teknisk "
                        "hantering behövs."
                    )
            elif lang == "en":
                stmt = (
                    "We will review the fault picture and decide the next troubleshooting step."
                )
            else:
                stmt = "Vi går igenom felbilden och bedömer nästa felsökningssteg."
            return NextStepSurfaceContract(
                statement=stmt,
                operational_summary="review fault and decide troubleshooting path",
                actor="operator",
                prerequisite="symptom details",
                must_not_promise=("remote_fix_guarantee", "same_day_resolution"),
            )
        if followup:
            if lang == "en":
                stmt = (
                    "We will review the fault from the start and let you know if we need "
                    "more details."
                )
            else:
                stmt = (
                    "Vi går igenom felbilden från början och återkommer om vi behöver "
                    "mer underlag."
                )
        elif lang == "en":
            stmt = (
                "Once we have the details, we will review the fault and decide how to proceed."
            )
        else:
            stmt = (
                "När vi har uppgifterna går vi igenom felbilden och bedömer nästa "
                "felsökningssteg."
            )
        return NextStepSurfaceContract(
            statement=stmt,
            operational_summary="collect symptom facts and plan troubleshooting",
            actor="operator",
            prerequisite="symptom and safety details",
            must_not_promise=("remote_fix_guarantee", "same_day_resolution"),
        )

    if (
        service_family == "general_consultation"
        and step_id == "collect_contact_preference"
        and not has_questions
    ):
        if lang == "en":
            stmt = (
                "Please send a couple of times that work for you and a brief note on "
                "what you mainly want to discuss during the consultation."
            )
        else:
            stmt = (
                "Skicka gärna ett par tider som passar samt en kort rad om vilka frågor "
                "ni främst vill gå igenom."
            )
        return NextStepSurfaceContract(
            statement=stmt,
            operational_summary="collect preferred call times for consultation",
            actor="customer",
            prerequisite="call scheduling preference",
            must_not_promise=("booking_confirmation", "quote_amount"),
        )

    if not has_questions:
        if lang == "en":
            return NextStepSurfaceContract(
                statement="We will review the details and get back to you.",
                operational_summary="review available details",
                actor="operator",
                prerequisite="available case details",
                must_not_promise=("quote_amount", "installation_date"),
            )
        return NextStepSurfaceContract(
            statement="Vi går igenom underlaget och återkommer.",
            operational_summary="granska tillgängligt underlag",
            actor="operator",
            prerequisite="tillgängliga ärendeuppgifter",
            must_not_promise=("offertbelopp", "installationsdatum"),
        )

    if service_family == "solar_installation" or service_family == "solar_battery_combined":
        if is_continuation:
            if followup:
                if lang == "en":
                    stmt = "We will update the documentation and get back when the assessment is ready."
                else:
                    stmt = "Vi uppdaterar underlaget och återkommer när bedömningen är klar."
            elif lang == "en":
                stmt = (
                    "Once we have the supplement, we will assess the roof and energy needs "
                    "for an updated evaluation."
                )
            else:
                stmt = (
                    "När vi fått de sista uppgifterna bedömer vi tak och energibehov "
                    "för en uppdaterad bedömning."
                )
        elif followup:
            if lang == "en":
                stmt = (
                    "We will review the details and get back with the next step in the quote process."
                )
            else:
                stmt = "Vi tar emot uppgifterna och återkommer med nästa steg i offertprocessen."
        elif lang == "en":
            stmt = (
                "Once we have the details, we will assess roof conditions, energy needs, "
                "and a possible system design."
            )
        else:
            stmt = (
                "När vi har underlaget bedömer vi takets förutsättningar, ert energibehov "
                "och en möjlig systemutformning."
            )
        return NextStepSurfaceContract(
            statement=stmt,
            operational_summary="assess roof, consumption, and system design",
            actor="operator",
            prerequisite="site and roof details",
            must_not_promise=("quote_amount", "installation_date", "production_guarantee"),
        )

    if service_family == "battery_installation":
        if lang == "en":
            stmt = (
                "Once we have the details, we will assess compatibility with your existing system, "
                "usage goals, and preliminary sizing."
            )
        else:
            stmt = (
                "När vi har underlaget bedömer vi kompatibilitet med befintligt system, "
                "användningsmål och preliminär dimensionering."
            )
        return NextStepSurfaceContract(
            statement=stmt,
            operational_summary="assess battery compatibility and sizing",
            actor="operator",
            prerequisite="existing system and usage details",
            must_not_promise=("quote_amount", "installation_date"),
        )

    if service_family == "ev_charger":
        if lang == "en":
            stmt = (
                "Once we have the details, we will review installation conditions, "
                "electrical capacity, and placement."
            )
        else:
            stmt = (
                "När vi har underlaget går vi igenom installationsförutsättningar, "
                "elkapacitet och placering."
            )
        return NextStepSurfaceContract(
            statement=stmt,
            operational_summary="assess charger installation prerequisites",
            actor="operator",
            prerequisite="property and electrical details",
            must_not_promise=("quote_amount", "installation_date"),
        )

    if service_family == "general_consultation" or step_id == "clarify_service_scope":
        if lang == "en":
            stmt = "Tell us a bit more so we can guide you to the right service."
        else:
            stmt = "Berätta gärna lite mer så vi kan vägleda er till rätt tjänst."
        return NextStepSurfaceContract(
            statement=stmt,
            operational_summary="clarify requested service scope",
            actor="customer",
            prerequisite="service scope description",
            must_not_promise=("quote_amount", "booking"),
        )

    if step_id == "confirm_case_receipt_only":
        if lang == "en":
            stmt = "We have noted your update and will get back if we need more."
        else:
            stmt = "Vi har noterat er uppdatering och återkommer om vi behöver mer."
        return NextStepSurfaceContract(
            statement=stmt,
            operational_summary="acknowledge update only",
            actor="operator",
            prerequisite="customer update",
            must_not_promise=("immediate_resolution",),
        )

    return NextStepSurfaceContract(
        statement=_GENERIC_NEXT_STEP_EN if lang == "en" else _GENERIC_NEXT_STEP_SV,
        operational_summary="generic review after documentation",
        actor="operator",
        prerequisite="requested documentation",
        must_not_promise=("quote_amount", "installation_date"),
    )


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
    attachment_state: str | None = None,
) -> str:
    """Backward-compatible wrapper returning only the customer-facing statement."""
    return build_next_step_surface(
        step_id=step_id,
        service_family=service_family,
        business_intent=business_intent,
        thread_state=thread_state,
        is_continuation=is_continuation,
        has_questions=has_questions,
        language=language,
        scenario_family=scenario_family,
        mentions_attachment_gap=mentions_attachment_gap,
        attachment_state=attachment_state,
    ).statement
