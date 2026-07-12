"""Support Question Generator.

Generates a Swedish customer-facing message asking for missing required fields.
Triggered when support completeness_score < 0.7.

Rules:
- Emergency/critical: lead with urgency, ask phone/address first, add safety disclaimer.
- Safety disclaimer injected for el/electricity-related issues.
- Tenant company name used in opening when available.
- Optional fields mentioned only for emergency/warranty.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.support.tenant_context import TenantSupportContext

_COMPLETENESS_THRESHOLD = 0.7

_SAFETY_DISCLAIMER = (
    "Om det finns direkt fara, bryt strömmen om det kan göras säkert "
    "och kontakta behörig hjälp eller jourtjänst omedelbart."
)

_FIELD_LABELS: dict[str, str] = {
    "address": "Fullständig adress (gatuadress och ort)",
    "phone": "Telefonnummer (så vi kan nå dig snabbt)",
    "email": "E-postadress",
    "issue_description": "Beskriv problemet så detaljerat du kan",
    "product_model": "Produktmodell eller fabrikat",
    "error_code": "Felkod eller larmkod (visas på display/app)",
    "photos": "Bilder om möjligt (bifoga eller länka)",
    "when_started": "När uppstod problemet?",
    "installation_date": "Datum för installationen",
    "invoice_number": "Fakturanummer",
    "customer_number": "Kundnummer",
    "preferred_time": "Önskat datum/tid för besök",
}

_SAFETY_TRIGGER_KEYWORDS = [
    "el", "ström", "kortslutning", "rök", "brand", "läck",
    "farligt", "stöt", "gnistor", "spänning",
]


def _has_safety_risk(ticket_type: str, input_data: dict) -> bool:
    if ticket_type in ("emergency", "safety"):
        return True
    text = (
        (input_data.get("subject") or "")
        + " "
        + (input_data.get("message_text") or "")
    ).lower()
    import re
    return any(
        re.search(r"\b" + re.escape(kw) + r"\b", text)
        for kw in _SAFETY_TRIGGER_KEYWORDS
    )


def generate_support_question_message(
    missing_fields: list[str],
    ticket_type: str = "other",
    tenant_ctx: "TenantSupportContext | None" = None,
    input_data: dict | None = None,
    service_profile=None,
) -> str | None:
    """Return a Swedish message asking for missing fields, or None if list is empty.

    When *service_profile* is provided and the ticket is not an emergency/safety
    case, the profile's own follow-up intro and field labels are used (via
    build_profile_question_message). Falls back to generic support logic for
    emergency tickets, safety risks, or when no profile is given.
    """
    if not missing_fields:
        return None

    input_data = input_data or {}
    company_name: str | None = None
    if tenant_ctx and tenant_ctx.context_available:
        company_name = tenant_ctx.company_name

    is_emergency = ticket_type == "emergency"
    is_safety = _has_safety_risk(ticket_type, input_data)

    # For non-emergency tickets: prefer the service profile's intro and question
    # labels — they are more actionable (e.g. VVS water shutoff, inverter model).
    # For emergency tickets: keep the AKUT header (tested contract) but still use
    # profile-specific field labels where available for better quality.
    if service_profile is not None and not is_emergency:
        from app.service_profiles.qualification import build_profile_question_message
        profile_msg = build_profile_question_message(service_profile, missing_fields, company_name)
        if profile_msg:
            if is_safety:
                profile_msg += f"\n\n⚠️ {_SAFETY_DISCLAIMER}"
            return profile_msg

    # Build question list — use profile field labels where available.
    profile_questions: dict[str, str] = (
        service_profile.follow_up_questions if service_profile is not None else {}
    )
    seen: set[str] = set()
    questions = []
    for f in missing_fields:
        label = (
            profile_questions.get(f)
            or _FIELD_LABELS.get(f)
            or f.replace("_", " ").capitalize()
        )
        if label not in seen:
            seen.add(label)
            questions.append(f"• {label}")
    body = "\n".join(questions)

    # Opening
    if is_emergency:
        if company_name:
            opening = (
                f"Vi på {company_name} behandlar ditt ärende som AKUT. "
                f"För att hjälpa dig omedelbart behöver vi dessa uppgifter:"
            )
        else:
            opening = "Ditt ärende behandlas som AKUT. Vi behöver dessa uppgifter för att hjälpa dig omedelbart:"
    else:
        if company_name:
            opening = (
                f"För att vi på {company_name} ska kunna hantera ditt ärende "
                f"behöver vi lite mer information:"
            )
        else:
            opening = "För att hantera ditt ärende behöver vi lite mer information:"

    # Closing
    closing = "Skicka gärna svar på det du kan, så hör vi av oss snart."
    if is_emergency:
        closing = "Svara omgående eller ring oss direkt — vi prioriterar ditt ärende."

    # Safety disclaimer
    disclaimer = ""
    if is_safety:
        disclaimer = f"\n\n⚠️ {_SAFETY_DISCLAIMER}"

    return f"{opening}\n\n{body}\n\n{closing}{disclaimer}"


def should_ask_questions(completeness_score: float) -> bool:
    return completeness_score < _COMPLETENESS_THRESHOLD
