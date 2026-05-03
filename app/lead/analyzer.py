"""Rule-based lead analyzer.

Deterministic — no LLM required. Classifies lead_type, intent, urgency,
and customer_type from message text using keyword matching.

When a TenantLeadContext is provided the analyzer:
- Restricts lead_type to services the tenant actually offers.
- Uses per-service tenant keywords in addition to default keywords.
- Reports tenant_context_used and matched_service.
"""
from __future__ import annotations

import re

from app.lead.models import LeadAnalysis, LeadType, Intent, Urgency, CustomerType


# ── default keyword tables ────────────────────────────────────────────────────

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


# ── helpers ───────────────────────────────────────────────────────────────────

def _combined_text(input_data: dict) -> str:
    subject = (input_data.get("subject") or "").lower()
    body = (input_data.get("message_text") or "").lower()
    return f"{subject} {body}"


def _any_keyword(text: str, keywords: list[str]) -> bool:
    return any(re.search(r"\b" + re.escape(kw) + r"\b", text) for kw in keywords)


def _build_effective_lead_type_table(
    tenant_ctx: "TenantLeadContext | None",
) -> list[tuple[str, list[str]]]:
    """Merge default keywords with tenant service keywords.

    If tenant has a services list, only include types the tenant offers.
    For each offered type, prepend any tenant-specific keywords.
    """
    if tenant_ctx is None or not tenant_ctx.context_available:
        return list(_LEAD_TYPE_KEYWORDS)  # type: ignore[return-value]

    offered = tenant_ctx.service_lead_types()
    if not offered:
        return list(_LEAD_TYPE_KEYWORDS)  # type: ignore[return-value]

    result = []
    for lt, default_kws in _LEAD_TYPE_KEYWORDS:
        if lt not in offered:
            continue
        extra = tenant_ctx.service_keywords_for(lt)
        result.append((lt, extra + default_kws))
    return result


# ── public API ────────────────────────────────────────────────────────────────

def analyze_lead(
    input_data: dict,
    entities: dict | None = None,
    tenant_ctx: "TenantLeadContext | None" = None,
) -> "LeadAnalysis":
    """Return a LeadAnalysis from raw input_data and optional entity-extraction entities.

    When tenant_ctx is provided the analysis is tenant-aware:
    - lead_type is restricted to services the tenant offers
    - per-service tenant keywords are added to the matching table
    - result includes tenant_context_used and matched_service
    """
    from app.lead.tenant_context import TenantLeadContext  # local to avoid circular
    text = _combined_text(input_data)
    entities = entities or {}

    effective_table = _build_effective_lead_type_table(tenant_ctx)

    # lead_type — first keyword match in effective table wins
    lead_type: str = "unknown"
    matched_service: str | None = None
    for lt, keywords in effective_table:
        if _any_keyword(text, keywords):
            lead_type = lt
            # Try to resolve human-readable service name from tenant config
            if tenant_ctx and tenant_ctx.context_available:
                for svc in tenant_ctx.services:
                    if svc.get("lead_type") == lt:
                        matched_service = svc.get("name") or lt
                        break
                if matched_service is None:
                    matched_service = lt
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

    # confidence
    confidence = 0.5
    if lead_type != "unknown":
        confidence += 0.25
    if intent != "researching":
        confidence += 0.15
    if urgency != "low":
        confidence += 0.10
    confidence = min(confidence, 1.0)

    # tenant context metadata
    ctx_used = bool(tenant_ctx and tenant_ctx.context_available)
    ctx_sources = tenant_ctx.sources_used if ctx_used else []

    return LeadAnalysis(
        lead_type=lead_type,  # type: ignore[arg-type]
        intent=intent,
        urgency=urgency,
        customer_type=customer_type,
        confidence=round(confidence, 3),
        tenant_context_used=ctx_used,
        context_sources=list(ctx_sources),
        matched_service=matched_service,
    )
