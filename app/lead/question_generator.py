"""Question Generator.

Generates a customer-facing Swedish message asking for missing fields.
Triggered when completeness_score < 0.7.

When a TenantLeadContext is provided the message uses:
- the tenant's company name
- tone/language preferences
- service-specific field labels

When a ServiceProfile is provided the message uses the profile's
follow_up_intro and follow_up_questions for richer, service-specific phrasing.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.lead.tenant_context import TenantLeadContext
    from app.service_profiles.models import ServiceProfile

# Swedish question templates per field
_FIELD_QUESTIONS: dict[str, str] = {
    "address":                   "Adress (gatuadress och ort)",
    "roof_type":                  "Taktyp (t.ex. betongpannor, plåt, tegelpannor)",
    "annual_consumption":         "Ungefärlig årsförbrukning (kWh/år)",
    "installation_timeline":      "När vill du komma igång ungefär?",
    "battery_interest":           "Är du intresserad av batterilager?",
    "roof_angle":                 "Takvinkel (ungefärlig lutning i grader)",
    "current_electricity_cost":   "Nuvarande elkostnad (kr/kWh eller elräkning per år)",
    "solar_exists":               "Har du redan solceller installerade?",
    "battery_capacity_preference":"Önskad batterikapacitet (kWh)",
    "property_type":              "Fastighetstyp (villa, radhus, lägenhet, lokal m.m.)",
    "charger_count":              "Antal laddpunkter du behöver",
    "main_fuse":                  "Huvudsäkringens storlek (ampere)",
    "work_description":           "Vad vill du ha hjälp med? Beskriv gärna ditt ärende",
    "current_panel_age":          "Hur gammal är din elcentral ungefär?",
    "roof_material":              "Taktäckningsmaterial (t.ex. betong, plåt, shingel)",
    "approximate_area":           "Ungefärlig takyta (kvm)",
    "roof_condition":             "Takets nuvarande skick (t.ex. mossa, alger, sprickor)",
    "preferred_color":            "Önskad färg eller kulör",
    "moss_level":                 "Ungefärlig mängd mossa/lav (lite/måttlig/kraftig)",
    "previous_cleaning":          "Har taket tvättats tidigare, och i så fall när?",
    "preferred_brand":            "Har du något föredraget laddboxsmärke?",
    "parking_type":               "Parkeringstyp (garage, carport, utomhus)",
    "contact_name":               "Ditt namn",
    "contact_phone":              "Telefonnummer",
    "contact_email":              "E-postadress",
    "notes":                      "Övrig information du vill dela",
}

_COMPLETENESS_THRESHOLD = 0.7


def generate_question_message(
    missing_fields: list[str],
    tenant_ctx: "TenantLeadContext | None" = None,
    lead_type: str | None = None,
    service_profile: "ServiceProfile | None" = None,
) -> str | None:
    """Return a Swedish customer message asking for missing_fields, or None if list is empty.

    When *service_profile* is provided its follow_up_intro and follow_up_questions
    are used for service-specific phrasing.  Tenant field-label overrides are
    still applied on top when available.
    """
    if not missing_fields:
        return None

    # Resolve company name from tenant context
    company_name: str | None = None
    if tenant_ctx and tenant_ctx.context_available:
        company_name = tenant_ctx.company_name

    # Resolve field label overrides from tenant service config
    custom_labels: dict[str, str] = {}
    if tenant_ctx and lead_type:
        for svc in tenant_ctx.services:
            if svc.get("lead_type") == lead_type:
                custom_labels = svc.get("field_labels") or {}
                break

    # Service-profile questions have priority over generic _FIELD_QUESTIONS
    profile_questions: dict[str, str] = {}
    if service_profile is not None:
        profile_questions = service_profile.follow_up_questions

    # Build question list
    questions = []
    for f in missing_fields:
        label = (
            custom_labels.get(f)
            or profile_questions.get(f)
            or _FIELD_QUESTIONS.get(f)
            or f.replace("_", " ").capitalize()
        )
        questions.append(f"• {label}")
    body = "\n".join(questions)

    # Opening line — use profile intro when available
    if service_profile is not None:
        opening = service_profile.follow_up_intro
        if company_name:
            opening = opening.replace("vi gärna:", f"vi på {company_name} gärna:")
            opening = opening.replace("vi:", f"vi på {company_name}:")
    elif company_name:
        opening = f"För att vi på {company_name} ska kunna ta fram ett bra förslag behöver vi bara lite mer information:"
    else:
        opening = "För att kunna ta fram ett bra förslag behöver vi bara lite mer information:"

    return f"{opening}\n\n{body}\n\nSkicka gärna svar på det du kan, så hör vi av oss snart."


def should_ask_questions(completeness_score: float) -> bool:
    return completeness_score < _COMPLETENESS_THRESHOLD
