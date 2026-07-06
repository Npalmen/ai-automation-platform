"""Rule-based support ticket analyzer.

Deterministic — no LLM required. Classifies ticket_type, category, urgency,
customer_sentiment, and requires_human from message text using keyword matching.

When a TenantSupportContext is provided the analyzer:
- Checks tenant SLA critical_keywords for urgency override.
- Uses matched service from tenant services list.
- Maps to tenant support_categories when available.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.support.models import (
    SupportAnalysis,
    TicketType,
    SupportCategory,
    SupportUrgency,
    CustomerSentiment,
)

if TYPE_CHECKING:
    from app.support.tenant_context import TenantSupportContext


# ── Keyword tables ────────────────────────────────────────────────────────────

_EMERGENCY_KEYWORDS = [
    "akut", "brand", "eld", "strömmen har gått", "strömbortfall",
    "elstöt", "stöt", "farligt", "fara", "läcker", "vattenskada",
    "kortslutning", "rök", "gnistor", "risk för liv", "brandrisk",
    "nödsituation", "omedelbart", "sos",
    "luktar bränt", "bränt lukt", "gnistrar", "gnistrade", "gnistor",
]

_TICKET_TYPE_KEYWORDS: list[tuple[TicketType, list[str]]] = [
    ("emergency", _EMERGENCY_KEYWORDS),
    ("warranty", [
        "garanti", "reklamation", "garantiärende", "fel efter installation",
        "defekt", "gick sönder", "slutat fungera", "inte fungerat sedan installation",
        "installerade hos oss", "ni installerade", "sedan ni installerade",
        "sedan installationen",
    ]),
    ("invoice_question", [
        "faktura", "fakturan", "belopp", "debitering", "påminnelse",
        "betalning", "överdebiterats", "fakturerat", "avgift", "kostnad fel",
    ]),
    ("complaint", [
        "klagomål", "missnöjd", "besviken", "dålig service", "dåligt arbete",
        "inte nöjd", "kräver kompensation", "oacceptabelt", "skandal",
        "anmäler", "JO-anmälan", "Konsumentverket", "reklamation",
        "häva avtalet", "hävning", "avtalstvist", "bestrider avtalet",
        "bestrider kostnaden", "advokat",
    ]),
    ("scheduling", [
        "boka om", "boka tid", "omboka", "avboka", "när kommer ni",
        "ny tid", "tidsbyte", "inte dykt upp", "uteblev", "missat besöket",
        "schemalägga", "planera besök",
    ]),
    ("question", [
        "undrar", "fråga", "hur fungerar", "vad kostar", "kan ni",
        "är det möjligt", "behöver information", "mer info", "hur lång tid",
        "vad innebär", "hjälp att förstå",
    ]),
    ("issue", [
        "problem", "fungerar inte", "trasig", "fel på", "driftstörning",
        "sluta fungera", "går inte", "krånglar", "driftstopp",
        "inte igång", "larm", "varning", "felkod", "blinkar",
        "producerar inget", "helt nere",
        "jordfelsbrytaren löser", "säkringen löser", "säkring slår",
        "växelriktaren", "invertern", "inga solceller",
    ]),
]

_CATEGORY_KEYWORDS: list[tuple[SupportCategory, list[str]]] = [
    ("safety", _EMERGENCY_KEYWORDS + ["säkerhet", "elsäkerhet", "strömrisk"]),
    ("installation", [
        "installation", "montage", "montering", "driftsättning",
        "installerat", "monterat", "anslutning", "inkoppling",
    ]),
    ("warranty", [
        "garanti", "reklamation", "defekt", "garantifel",
    ]),
    ("invoice", [
        "faktura", "belopp", "debitering", "betalning", "fakturering",
        "inkasso", "betalningskrav", "kravbrev", "kronofogden",
    ]),
    ("scheduling", [
        "boka", "tid", "besök", "kalender", "schema",
    ]),
    ("product", [
        "produkt", "enhet", "panel", "batteri", "laddbox", "inverter",
        "komponent", "fabrikat", "modell", "specifikation",
    ]),
    ("service", [
        "service", "underhåll", "rengöring", "kontroll", "besiktning",
        "årsservice", "inspektion",
    ]),
]

_URGENCY_KEYWORDS: dict[SupportUrgency, list[str]] = {
    "critical": _EMERGENCY_KEYWORDS + [
        "livsfarligt", "evakuering", "rädda", "läckage", "explosion",
        "arbetsmiljö", "säkerhetsrisk",
        "luktar bränt", "bränt lukt", "gnistrar", "gnistor",
        "elstöt", "kortslutning",
    ],
    "high": [
        "brådskande", "asap", "snabbt", "snarast", "omgående",
        "idag", "denna vecka", "inom 24 timmar", "akut hjälp",
        "inga solceller", "producerar inget", "helt nere",
    ],
    "medium": [
        "snart", "inom kort", "inom en vecka", "ganska viktigt",
        "lite problem", "sporadiskt", "ibland",
    ],
}

_SENTIMENT_KEYWORDS: dict[CustomerSentiment, list[str]] = {
    "angry": [
        "arg", "rasande", "skandal", "oacceptabelt", "kräver",
        "anmäler", "skäms", "livsfarligt fel ni gjort", "stämmer",
        "advokat", "polisanmälan", "häva avtalet", "bestrider",
    ],
    "frustrated": [
        "missnöjd", "besviken", "frustrerad", "trött på", "inte okej",
        "tredje gången", "andra gången", "fortfarande inte löst",
        "fortfarande problem", "ingenting händer", "ni svarar inte",
    ],
    "concerned": [
        "orolig", "bekymrad", "osäker", "oro", "undrar om det är farligt",
        "vad händer om", "risk", "säker",
    ],
}

_REQUIRES_HUMAN_SIGNALS = [
    "emergency", "complaint", "warranty",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _combined_text(input_data: dict) -> str:
    subject = (input_data.get("subject") or "").lower()
    body = (input_data.get("message_text") or "").lower()
    return f"{subject} {body}"


def _any_keyword(text: str, keywords: list[str]) -> bool:
    return any(re.search(r"\b" + re.escape(kw.lower()) + r"\b", text) for kw in keywords)


def _detect_urgency(text: str, tenant_ctx: "TenantSupportContext | None") -> SupportUrgency:
    # Tenant SLA critical override first
    if tenant_ctx and tenant_ctx.context_available and tenant_ctx.is_critical_by_sla(text):
        return "critical"
    for level in ("critical", "high", "medium"):
        if _any_keyword(text, _URGENCY_KEYWORDS[level]):  # type: ignore[literal-required]
            return level  # type: ignore[return-value]
    return "low"


def _detect_sentiment(text: str) -> CustomerSentiment:
    for sentiment in ("angry", "frustrated", "concerned"):
        if _any_keyword(text, _SENTIMENT_KEYWORDS[sentiment]):  # type: ignore[literal-required]
            return sentiment  # type: ignore[return-value]
    return "neutral"


def _match_service(text: str, tenant_ctx: "TenantSupportContext | None") -> str | None:
    if not tenant_ctx or not tenant_ctx.context_available:
        return None
    for svc in tenant_ctx.services:
        kws = (svc.get("keywords") or []) + [svc.get("name", ""), svc.get("lead_type", "")]
        for kw in kws:
            if kw and re.search(r"\b" + re.escape(kw.lower()) + r"\b", text):
                return svc.get("name") or svc.get("lead_type")
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def analyze_support(
    input_data: dict,
    entities: dict | None = None,
    tenant_ctx: "TenantSupportContext | None" = None,
) -> SupportAnalysis:
    """Return a SupportAnalysis from raw input_data and optional entity extraction.

    Deterministic — no LLM required.
    Tenant-aware: uses SLA rules and service matching when context is provided.
    """
    text = _combined_text(input_data)
    entities = entities or {}

    # ticket_type — first match wins (priority order matters)
    ticket_type: TicketType = "other"
    for tt, keywords in _TICKET_TYPE_KEYWORDS:
        if _any_keyword(text, keywords):
            ticket_type = tt
            break

    # category
    category: SupportCategory = "other"
    # If tenant context, check if category is in tenant support_categories first
    if tenant_ctx and tenant_ctx.context_available and tenant_ctx.support_categories:
        for cat in tenant_ctx.support_categories:
            if re.search(r"\b" + re.escape(cat.lower()) + r"\b", text):
                category = cat if cat in SupportCategory.__args__ else "other"  # type: ignore[attr-defined]
                break

    if category == "other":
        for cat, keywords in _CATEGORY_KEYWORDS:
            if _any_keyword(text, keywords):
                category = cat
                break

    # urgency
    urgency = _detect_urgency(text, tenant_ctx)

    # sentiment
    sentiment = _detect_sentiment(text)

    # requires_human — also escalate frustrated customers; recurring-contact
    # patterns ("tredje gången") indicate a case that has slipped through.
    requires_human = (
        ticket_type in _REQUIRES_HUMAN_SIGNALS
        or urgency in ("critical", "high")
        or sentiment in ("angry", "frustrated")
    )

    # matched_service from tenant context
    matched_service = _match_service(text, tenant_ctx)

    # confidence
    confidence = 0.5
    if ticket_type != "other":
        confidence += 0.2
    if category != "other":
        confidence += 0.1
    if urgency != "low":
        confidence += 0.1
    if tenant_ctx and tenant_ctx.context_available:
        confidence += 0.05
    confidence = min(confidence, 1.0)

    ctx_used = bool(tenant_ctx and tenant_ctx.context_available)
    ctx_sources = list(tenant_ctx.sources_used) if ctx_used else []

    return SupportAnalysis(
        ticket_type=ticket_type,
        category=category,
        urgency=urgency,
        customer_sentiment=sentiment,
        requires_human=requires_human,
        confidence=round(confidence, 3),
        matched_service=matched_service,
        tenant_context_used=ctx_used,
        context_sources=ctx_sources,
    )
