"""Profile-aware deterministic renderer and validation (Todos E-F)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.workflows.reply_candidate_safety import assess_reply_candidate_safety
from app.workflows.reply_quality.plan_v2 import CustomerReplyPlanV2
from app.workflows.reply_quality.provenance import (
    DETERMINISTIC_RENDERER,
    RENDERER_POLICY_VERSION,
    ReplyRenderProvenance,
    hash_body,
    hash_plan,
)

TEMPLATE_VERSION = "digital_coworker_structured_v2"

_FAMILY_COPY: dict[str, dict[str, dict[str, str]]] = {
    "solar_installation": {
        "sv": {
            "information_request": "Tack för din förfrågan om solcellsinstallation.",
            "continuation": "Tack för din uppföljning och kompletteringen om solceller.",
            "context": "Vi tittar på förutsättningarna för sol på er fastighet.",
        },
        "en": {
            "information_request": "Thank you for your solar installation enquiry.",
            "continuation": "Thanks for the follow-up on your solar request.",
            "context": "We are reviewing the solar site prerequisites.",
        },
    },
    "battery_installation": {
        "sv": {
            "information_request": "Tack för att du hör av dig om batterilager.",
            "continuation": "Tack för din uppföljning om batterilösningen.",
            "context": "Vi bedömer batterialternativ utifrån er befintliga eller planerade solcellsanläggning.",
        },
        "en": {
            "information_request": "Thank you for your battery storage enquiry.",
            "continuation": "Thanks for the follow-up on the battery request.",
            "context": "We are reviewing battery options for your property.",
        },
    },
    "ev_charger": {
        "sv": {
            "information_request": "Tack för din förfrågan om laddbox.",
            "continuation": "Tack för din uppföljning om laddboxen.",
            "context": "Vi tittar på förutsättningarna för laddboxinstallationen.",
        },
        "en": {
            "information_request": "Thank you for your EV charger enquiry.",
            "continuation": "Thanks for the follow-up on the charger request.",
            "context": "We are reviewing the charger installation prerequisites.",
        },
    },
    "existing_installation_support": {
        "sv": {
            "support_acknowledgement": "Tack för att du hör av dig om er befintliga anläggning.",
            "information_request": "Vi vill förstå felet bättre på den befintliga anläggningen.",
            "continuation": "Tack för uppföljningen om felet på den befintliga anläggningen.",
            "context": "Vi felsöker vidare på befintlig anläggning utifrån symptomen du beskriver.",
        },
        "en": {
            "support_acknowledgement": "Thank you for contacting us about your existing installation.",
            "information_request": "We need a clearer picture of the fault on the existing installation.",
            "continuation": "Thanks for the follow-up about the fault on the existing installation.",
            "context": "We are continuing fault triage on the existing installation.",
        },
    },
    "job_status": {
        "sv": {
            "status_acknowledgement": "Tack för din statusförfrågan.",
            "continuation": "Tack för din uppföljning om ärendestatus.",
            "context": "Vi tar fram status på ert ärende.",
        },
        "en": {
            "status_acknowledgement": "Thank you for your status request.",
            "continuation": "Thanks for following up on the case status.",
            "context": "We are checking the status of your case.",
        },
    },
    "complaint_warranty": {
        "sv": {
            "support_acknowledgement": "Tack för att du kontaktar oss om reklamationen.",
            "context": "Vi tar emot reklamationen och går igenom underlaget.",
        },
        "en": {
            "support_acknowledgement": "Thank you for contacting us about the complaint.",
            "context": "We have received the complaint and will review the details.",
        },
    },
    "general_consultation": {
        "sv": {
            "information_request": "Tack för ditt meddelande.",
            "context": "Vi behöver förstå lite mer om vad du vill ha hjälp med.",
        },
        "en": {
            "information_request": "Thank you for your message.",
            "context": "We need a bit more context about what you need help with.",
        },
    },
    "unknown_service": {
        "sv": {
            "information_request": "Tack för ditt meddelande.",
            "context": "Vi behöver veta mer om vilken tjänst det gäller.",
        },
        "en": {
            "information_request": "Thank you for your message.",
            "context": "We need to understand which service you are asking about.",
        },
    },
}

_QUESTION_INTRO: dict[str, dict[str, str]] = {
    "solar_installation": {
        "sv": "För solcellsoffert behöver vi:",
        "en": "For the solar quote we need:",
    },
    "battery_installation": {
        "sv": "För batteribedömning behöver vi:",
        "en": "For the battery assessment we need:",
    },
    "ev_charger": {
        "sv": "För laddboxprojektet behöver vi:",
        "en": "For the charger project we need:",
    },
    "existing_installation_support": {
        "sv": "För att felsöka vidare behöver vi:",
        "en": "To troubleshoot further we need:",
    },
    "job_status": {
        "sv": "För att hitta rätt status behöver vi:",
        "en": "To locate the right status we need:",
    },
    "complaint_warranty": {
        "sv": "För reklamationsärendet behöver vi:",
        "en": "For the complaint case we need:",
    },
    "general_consultation": {
        "sv": "Kan du återkomma med:",
        "en": "Could you reply with:",
    },
    "unknown_service": {
        "sv": "Kan du återkomma med:",
        "en": "Could you reply with:",
    },
}


@dataclass(frozen=True)
class RenderResult:
    body: str
    provenance: ReplyRenderProvenance
    validation: dict[str, Any]


def _lang(plan: CustomerReplyPlanV2) -> str:
    return "en" if (plan.language or "sv").lower().startswith("en") else "sv"


def _copy(plan: CustomerReplyPlanV2) -> dict[str, str]:
    family = plan.service_family
    language = _lang(plan)
    return _FAMILY_COPY.get(family, _FAMILY_COPY["unknown_service"]).get(
        language,
        _FAMILY_COPY.get(family, _FAMILY_COPY["unknown_service"])["sv"],
    )


def _opener(plan: CustomerReplyPlanV2) -> str:
    copy = _copy(plan)
    thread = plan.thread_context
    if thread.is_continuation:
        return copy.get("continuation") or copy.get("information_request", "")
    if plan.acknowledgement_mode == "status_acknowledgement":
        return copy.get("status_acknowledgement", copy.get("information_request", ""))
    if plan.acknowledgement_mode == "support_acknowledgement":
        return copy.get("support_acknowledgement", copy.get("information_request", ""))
    return copy.get("information_request", "Tack för ditt meddelande.")


def _context_line(plan: CustomerReplyPlanV2) -> str:
    copy = _copy(plan)
    base = copy.get("context", "")
    if plan.business_intent == "ambiguous_short":
        if _lang(plan) == "en":
            base = f"{base} Please attach an image or drawing if you have one.".strip()
        else:
            base = f"{base} Skicka gärna bild eller ritning om du har.".strip()
    if plan.verified_facts:
        facts = ", ".join(plan.verified_facts[:2])
        return f"{base} {facts}.".strip()
    return base


def render_deterministic_coworker_reply(plan: CustomerReplyPlanV2) -> str:
    opener = _opener(plan)
    context = _context_line(plan)
    questions = list(plan.selected_question_labels)
    language = _lang(plan)
    intro = _QUESTION_INTRO.get(plan.service_family, _QUESTION_INTRO["general_consultation"])[language]

    closing = (
        f"\n\n{'Kind regards' if language == 'en' else 'Vänliga hälsningar'}\n{plan.signature_name}"
        if plan.signature_name
        else ""
    )

    if questions:
        question_block = "\n".join(f"- {q}" for q in questions)
        body_middle = (
            f"{opener}\n\n"
            f"{context}\n\n"
            f"{plan.next_step_statement}\n\n"
            f"{intro}\n"
            f"{question_block}"
        )
    else:
        body_middle = (
            f"{opener}\n\n"
            f"{context}\n\n"
            f"{plan.next_step_statement}"
        )

    return f"{plan.greeting}\n\n{body_middle}{closing}"


def _render_safe_fallback(plan: CustomerReplyPlanV2) -> str:
    language = _lang(plan)
    closing = (
        f"\n\n{'Kind regards' if language == 'en' else 'Vänliga hälsningar'}\n{plan.signature_name}"
        if plan.signature_name
        else ""
    )
    ack = (
        "Thank you for your message. We have received it and will get back to you."
        if language == "en"
        else "Tack för ditt meddelande. Vi har tagit emot det och återkommer."
    )
    return f"{plan.greeting}\n\n{ack}\n\n{plan.next_step_statement}{closing}"


def validate_rendered_reply(
    *,
    plan: CustomerReplyPlanV2,
    body: str,
) -> dict[str, Any]:
    issues: list[str] = []
    normalized = body.lower()

    if "intern operatör" in normalized:
        issues.append("internal_note_leak")

    planned_labels = {q.lower() for q in plan.selected_question_labels}
    bullet_lines = [
        line.strip(" -•\t").lower()
        for line in body.splitlines()
        if line.strip().startswith(("-", "•"))
    ]
    for line in bullet_lines:
        if not line:
            continue
        if not any(label in line or line in label for label in planned_labels):
            if "namn" in line and "contact_name" not in plan.selected_questions:
                issues.append("extra_question:name")
            elif "telefon" in line and "phone_or_email" not in plan.selected_questions:
                issues.append("extra_question:phone")

    safety = assess_reply_candidate_safety(body)
    if not safety.get("passed"):
        issues.extend(safety.get("violations") or [])

    return {
        "passed": not issues and safety.get("passed", False),
        "issues": issues,
        "safety": safety,
    }


def render_coworker_reply_with_validation(
    plan: CustomerReplyPlanV2,
    *,
    draft_body: str | None = None,
    sent_body: str | None = None,
) -> RenderResult:
    fallback_reason: str | None = plan.fallback_reason
    body = render_deterministic_coworker_reply(plan)
    validation = validate_rendered_reply(plan=plan, body=body)

    if not validation["passed"]:
        fallback_reason = ",".join(validation["issues"][:3]) or "validation_failed"
        body = _render_safe_fallback(plan)
        validation = validate_rendered_reply(plan=plan, body=body)

    provenance = ReplyRenderProvenance(
        renderer_type=DETERMINISTIC_RENDERER,
        llm_used=False,
        model_id=None,
        prompt_version=None,
        template_version=TEMPLATE_VERSION,
        use_fallback=bool(fallback_reason),
        fallback_reason=fallback_reason,
        plan_hash=hash_plan(plan.to_dict()),
        body_hash=hash_body(body),
        draft_body_hash=hash_body(draft_body) if draft_body else None,
        sent_body_hash=hash_body(sent_body) if sent_body else None,
        policy_version=RENDERER_POLICY_VERSION,
    )
    return RenderResult(body=body, provenance=provenance, validation=validation)
