"""Offer Draft Engine — safe preliminary drafts only.

Produces a structured offer outline when completeness_score >= 0.7.
No exact pricing — only safe placeholder ranges per lead_type.
"""
from __future__ import annotations

from app.lead.models import LeadAnalysis, MissingInfoResult, OfferDraft


# Safe static price ranges per lead_type (SEK, rough market references).
# Clearly marked as estimates, not binding quotes.
_PRICE_RANGES: dict[str, str] = {
    "solar_installation": "80 000 – 200 000 kr (beroende på systemstorlek och takyta)",
    "battery_storage":    "40 000 – 120 000 kr (beroende på kapacitet)",
    "ev_charger":         "8 000 – 25 000 kr inkl. installation",
    "electrical_work":    "5 000 – 50 000 kr (beroende på arbetets omfattning)",
    "roof_painting":      "15 000 – 60 000 kr (beroende på yta och material)",
    "roof_cleaning":      "8 000 – 35 000 kr (beroende på yta och skick)",
}

_OFFER_SECTIONS: dict[str, list[str]] = {
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

_ASSUMPTIONS: dict[str, list[str]] = {
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
_DEFAULT_ASSUMPTIONS = ["Baserat på angiven information — besiktning kan ändra förutsättningar"]


def build_offer_draft(
    analysis: LeadAnalysis,
    missing_info: MissingInfoResult,
    entities: dict,
) -> OfferDraft | None:
    """Return an OfferDraft if completeness >= 0.7, else None."""
    if missing_info.completeness_score < 0.7:
        return None

    lt = analysis.lead_type
    customer = entities.get("customer_name") or entities.get("company_name") or "kunden"

    summary = (
        f"Preliminärt underlag för {lt.replace('_', ' ')} "
        f"åt {customer}. "
        f"Baserat på tillgänglig information — exakt offert tas fram efter besiktning."
    )

    recommended_next_step = (
        "Boka besiktning/mätning på plats för att ta fram en exakt offert."
    )

    sections = _OFFER_SECTIONS.get(lt, _DEFAULT_SECTIONS)
    assumptions = _ASSUMPTIONS.get(lt, _DEFAULT_ASSUMPTIONS)
    price_range = _PRICE_RANGES.get(lt)

    # Lower confidence when lead_type is unknown or completeness is marginal
    confidence = 0.5
    if lt != "unknown":
        confidence += 0.25
    if missing_info.completeness_score >= 0.85:
        confidence += 0.20
    elif missing_info.completeness_score >= 0.7:
        confidence += 0.10
    confidence = min(confidence, 0.95)

    return OfferDraft(
        summary=summary,
        recommended_next_step=recommended_next_step,
        assumptions=assumptions,
        suggested_offer_sections=sections,
        estimated_price_range=price_range,
        confidence=round(confidence, 3),
    )
