"""Rule-based lead analyzer.

Deterministic — no LLM required. Classifies lead_type, intent, urgency,
and customer_type from message text using keyword matching.
"""
from __future__ import annotations

import re

from app.lead.models import LeadAnalysis, LeadType, Intent, Urgency, CustomerType


# ── keyword tables ────────────────────────────────────────────────────────────

_LEAD_TYPE_KEYWORDS: list[tuple[LeadType, list[str]]] = [
    ("solar_installation", [
        "solcell", "solpanel", "solenergi", "solar", "solkraft",
        "solcellsinstallation", "solcellsanläggning", "pv",
    ]),
    ("battery_storage", [
        "batteri", "batterilager", "energilager", "laddlager",
        "powerwall", "tesla battery", "husbatteri",
    ]),
    ("ev_charger", [
        "laddbox", "laddstolpe", "elbilsladdning", "wallbox",
        "laddning av elbil", "hemmaladdning", "laddstation",
        "laddpunkt", "ev charger", "elbil laddning",
    ]),
    ("electrical_work", [
        "elarbete", "elinstallation", "elsystem", "elcentral",
        "säkring", "jordfelsbrytare", "gruppcent", "elmontör",
        "elektriker", "elledning",
    ]),
    ("roof_painting", [
        "takmålning", "måla tak", "takfärg", "takbehandling",
        "impregnering", "taklack", "takcoating",
    ]),
    ("roof_cleaning", [
        "taktvätt", "tvätta tak", "alger", "mossa", "lav",
        "biowash", "takhögertryckstvätt", "högtryckstvätt tak",
        "taktvättning",
    ]),
]

# ready_to_buy > comparing > researching (first match wins in that order)
_INTENT_KEYWORDS: list[tuple[Intent, list[str]]] = [
    ("ready_to_buy", [
        "offert", "pris", "installera", "boka", "köpa", "beställa",
        "vill ha", "när kan ni", "kostnad", "prisuppgift", "quote",
        "order",
    ]),
    ("comparing", [
        "jämför", "alternativ", "vilket är bäst", "skillnad",
        "rekommenderar ni", "eller", "vs", "bättre",
    ]),
    ("researching", [
        "funderar", "tänker", "kanske", "vad kostar ungefär",
        "hur fungerar", "mer info", "information", "nyfiken",
        "lär mig",
    ]),
]

_URGENCY_KEYWORDS: dict[Urgency, list[str]] = {
    "high": [
        "akut", "snarast", "asap", "brådskande", "denna vecka",
        "i veckan", "snabbt", "omgående", "nu", "direkt",
    ],
    "medium": [
        "inom en månad", "snart", "nästa månad", "inom kort",
        "ganska snart",
    ],
}

_CUSTOMER_TYPE_KEYWORDS: dict[CustomerType, list[str]] = {
    "brf": ["brf", "bostadsrättsförening", "förening", "styrelse"],
    "company": [
        "ab", "aktiebolag", "företag", "organisation", "org",
        "bolaget", "vd ", "styrelseordförande",
    ],
    "private": [
        "villa", "hus", "mitt hem", "hemma", "privat",
        "enfamiljshus", "radhus",
    ],
}


# ── helper ────────────────────────────────────────────────────────────────────

def _combined_text(input_data: dict) -> str:
    subject = (input_data.get("subject") or "").lower()
    body = (input_data.get("message_text") or "").lower()
    return f"{subject} {body}"


def _any_keyword(text: str, keywords: list[str]) -> bool:
    return any(re.search(r"\b" + re.escape(kw) + r"\b", text) for kw in keywords)


# ── public API ────────────────────────────────────────────────────────────────

def analyze_lead(input_data: dict, entities: dict | None = None) -> LeadAnalysis:
    """Return a LeadAnalysis from raw input_data and optional entity-extraction entities."""
    text = _combined_text(input_data)
    entities = entities or {}

    # lead_type — first keyword match wins; unknown if none
    lead_type: LeadType = "unknown"
    for lt, keywords in _LEAD_TYPE_KEYWORDS:
        if _any_keyword(text, keywords):
            lead_type = lt
            break

    # intent — ready_to_buy takes priority
    intent: Intent = "researching"
    for it, keywords in _INTENT_KEYWORDS:
        if _any_keyword(text, keywords):
            intent = it
            break

    # urgency
    urgency: Urgency = "low"
    for level in ("high", "medium"):
        if _any_keyword(text, _URGENCY_KEYWORDS[level]):  # type: ignore[literal-required]
            urgency = level  # type: ignore[assignment]
            break

    # customer_type — brf > company > private > unknown
    customer_type: CustomerType = "unknown"
    for ct in ("brf", "company", "private"):
        if _any_keyword(text, _CUSTOMER_TYPE_KEYWORDS[ct]):  # type: ignore[literal-required]
            customer_type = ct  # type: ignore[assignment]
            break

    # confidence: higher when lead_type and intent are not default
    confidence = 0.5
    if lead_type != "unknown":
        confidence += 0.25
    if intent != "researching":
        confidence += 0.15
    if urgency != "low":
        confidence += 0.10
    confidence = min(confidence, 1.0)

    return LeadAnalysis(
        lead_type=lead_type,
        intent=intent,
        urgency=urgency,
        customer_type=customer_type,
        confidence=round(confidence, 3),
    )
