"""Offer Draft Engine — safe preliminary drafts only.

Produces a structured offer outline when completeness_score >= 0.7.
No exact pricing unless tenant pricing_guidelines explicitly provide a range.
When a TenantLeadContext is provided the draft uses tenant company name,
offer_principles, and per-service pricing/sections.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from app.lead.models import LeadAnalysis, MissingInfoResult, OfferDraft

if TYPE_CHECKING:
    from app.lead.tenant_context import TenantLeadContext


# ── default static data per lead_type ────────────────────────────────────────

_DEFAULT_PRICE_RANGES: dict[str, str] = {
    "solar_installation": "80 000 – 200 000 kr (beroende på systemstorlek och takyta)",
    "battery_storage":    "40 000 – 120 000 kr (beroende på kapacitet)",
    "ev_charger":         "8 000 – 25 000 kr inkl. installation",
    "electrical_work":    "5 000 – 50 000 kr (beroende på arbetets omfattning)",
    "roof_painting":      "15 000 – 60 000 kr (beroende på yta och material)",
    "roof_cleaning":      "8 000 – 35 000 kr (beroende på yta och skick)",
}

_DEFAULT_OFFER_SECTIONS: dict[str, list[str]] = {
    "solar_installation": [
        "Systemdimensionering (kW)",
        "Takanalys och placering",
        "Material och komponenter",
        "Installation och driftsättning",
        "Nätanmälan och ROT-avdrag",
        "Garanti och service",
    ],
    "battery_storage": [
        "Batterikapacitet och fabrikat",
        "Integration med befintligt elsystem",
        "Installation och driftsättning",
        "Garanti och support",
    ],
    "ev_charger": [
        "Val av laddbox (fabrikat/modell)",
        "Kabeldragning och elarbete",
        "Installation och provtagning",
        "App-konfiguration / smart laddning",
        "ROT-avdrag (om tillämpligt)",
    ],
    "electrical_work": [
        "Felbeskrivning och besiktning",
        "Material och reservdelar",
        "Elinstallation och driftsättning",
        "Protokoll och besiktning",
    ],
    "roof_painting": [
        "Förberedelse och rengöring",
        "Grundning",
        "Täckfärg (antal lager)",
        "Slutkontroll",
    ],
    "roof_cleaning": [
        "Rengöring med biowash/högtryck",
        "Behandling mot mossa och alger",
        "Skadebesiktning efter tvättning",
        "Rekommendationer för framtida underhåll",
    ],
}

_DEFAULT_ASSUMPTIONS: dict[str, list[str]] = {
    "solar_installation": [
        "Normalt tak utan hinder eller skuggning",
        "Befintlig elinstallation är godkänd",
        "Tillgång till nätanslutning",
    ],
    "battery_storage": [
        "Befintligt elsystem klarar batteriinstallation",
        "Inomhusinstallation i tekniskt utrymme",
    ],
    "ev_charger": [
        "Tillräcklig kapacitet i befintlig elcentral",
        "Kabel kan dras till parkeringsplats",
    ],
    "electrical_work": [
        "Befintlig installation följer gällande standard",
        "Arbetet kräver ingen rivning av väggar",
    ],
    "roof_painting": [
        "Taket är i sådant skick att det kan målas",
        "Tillgång för ställning eller skylift",
    ],
    "roof_cleaning": [
        "Taket är åtkomligt för tvätt",
        "Ingen strukturell skada som kräver reparation",
    ],
}

_DEFAULT_SECTIONS = ["Behovsinventering", "Offert", "Installation", "Uppföljning"]
_DEFAULT_ASSUMPTIONS_FALLBACK = ["Baserat på angiven information — besiktning kan ändra förutsättningar"]


# ── public API ────────────────────────────────────────────────────────────────

def build_offer_draft(
    analysis: LeadAnalysis,
    missing_info: MissingInfoResult,
    entities: dict,
    tenant_ctx: "TenantLeadContext | None" = None,
) -> OfferDraft | None:
    """Return an OfferDraft if completeness >= 0.7, else None."""
    if missing_info.completeness_score < 0.7:
        return None

    lt = analysis.lead_type
    customer = entities.get("customer_name") or entities.get("company_name") or "kunden"

    tenant_ctx_used = False
    ctx_sources: list[str] = []
    company_name: str | None = None

    # ── Tenant overrides ──────────────────────────────────────────────────────
    price_range: str | None = _DEFAULT_PRICE_RANGES.get(lt)
    sections = _DEFAULT_OFFER_SECTIONS.get(lt, _DEFAULT_SECTIONS)
    assumptions = _DEFAULT_ASSUMPTIONS.get(lt, _DEFAULT_ASSUMPTIONS_FALLBACK)
    offer_principles: list[str] = []
    risk_points: list[str] = []

    if tenant_ctx and tenant_ctx.context_available:
        tenant_ctx_used = True
        ctx_sources = list(tenant_ctx.sources_used)
        company_name = tenant_ctx.company_name

        # Pricing override from tenant config
        pricing = tenant_ctx.pricing_for(lt)
        if pricing:
            tenant_price = pricing.get("price_range")
            if tenant_price:
                price_range = tenant_price
            notes = pricing.get("notes")
            if notes:
                risk_points.append(notes)

        # Offer sections override
        for svc in tenant_ctx.services:
            if svc.get("lead_type") == lt:
                svc_sections = svc.get("offer_sections") or []
                if svc_sections:
                    sections = svc_sections
                svc_assumptions = svc.get("assumptions") or []
                if svc_assumptions:
                    assumptions = svc_assumptions
                break

        # Global offer principles
        offer_principles = tenant_ctx.offer_principles

        # Geographic constraint risk
        if tenant_ctx.served_areas:
            address = entities.get("address") or entities.get("city") or ""
            area_lower = [a.lower() for a in tenant_ctx.served_areas]
            import re
            in_area = any(re.search(r"\b" + re.escape(a) + r"\b", address.lower()) for a in area_lower)
            if not in_area and address:
                risk_points.append("Kontrollera att adressen är inom serviceområdet.")

    # Merge offer principles into assumptions suffix
    full_assumptions = list(assumptions)
    for p in offer_principles:
        if p not in full_assumptions:
            full_assumptions.append(p)

    # Summary line
    if company_name:
        summary = (
            f"Preliminärt underlag från {company_name} för "
            f"{lt.replace('_', ' ')} åt {customer}. "
            f"Baserat på tillgänglig information — exakt offert tas fram efter besiktning."
        )
    else:
        summary = (
            f"Preliminärt underlag för {lt.replace('_', ' ')} "
            f"åt {customer}. "
            f"Baserat på tillgänglig information — exakt offert tas fram efter besiktning."
        )

    recommended_next_step = "Boka besiktning/mätning på plats för att ta fram en exakt offert."

    # Confidence
    confidence = 0.5
    if lt != "unknown":
        confidence += 0.25
    if missing_info.completeness_score >= 0.85:
        confidence += 0.20
    elif missing_info.completeness_score >= 0.7:
        confidence += 0.10
    if tenant_ctx_used:
        confidence += 0.05
    confidence = min(confidence, 0.95)

    return OfferDraft(
        summary=summary,
        recommended_next_step=recommended_next_step,
        assumptions=full_assumptions,
        suggested_offer_sections=sections,
        estimated_price_range=price_range,
        confidence=round(confidence, 3),
        risk_points=risk_points,
        tenant_context_used=tenant_ctx_used,
        context_sources=ctx_sources,
        customer_name=entities.get("customer_name") or entities.get("company_name"),
        customer_email=entities.get("email"),
        customer_phone=entities.get("phone"),
        address=entities.get("address") or entities.get("city"),
        missing_fields=list(missing_info.missing_fields),
        human_approval_required=True,
    )
