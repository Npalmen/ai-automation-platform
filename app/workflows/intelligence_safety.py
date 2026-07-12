"""Shared deterministic safety checks for core intelligence.

These helpers are intentionally small and conservative. They do not decide the
business action; they only surface do-not-touch signals so processors can fail
closed when content is legally, financially, safety, or privacy sensitive.
"""
from __future__ import annotations

import re
from typing import Any


_RISK_KEYWORDS: dict[str, tuple[str, ...]] = {
    "legal_threat": (
        "advokat",
        "juridiskt",
        "juridisk",
        "rättsligt",
        "stämning",
        "polisanmälan",
        "anmälan",
        "konsumentverket",
        "arn",
    ),
    "complaint": (
        "reklamation",
        "reklamerar",
        "klagomål",
        "missnöjd",
        "inte nöjd",
        "ej nöjd",
        "oacceptabelt",
        "dåligt arbete",
        "kompensation",
        "ingen har ringt",
        "ingen ringde",
        "inte hört av er",
    ),
    "contract_dispute": (
        "häva avtalet",
        "hävning",
        "avtalstvist",
        "bestrider avtalet",
        "bestrider kostnaden",
        "avtalsfråga",
        "avtalsbrott",
    ),
    "debt_collection": (
        "inkasso",
        "inkassokrav",
        "inkassobolag",
        "betalningskrav",
        "kravbrev",
        "påminnelseavgift",
        "kronofogden",
        "förfallen skuld",
        "betalningsanmärkning",
    ),
    "financial_change": (
        "ändra faktura",
        "kreditera",
        "makulera faktura",
        "återbetalning",
        "rabatt i efterhand",
        "ekonomisk ändring",
    ),
    "safety_risk": (
        "brandrisk",
        "risk för brand",
        "luktar bränt",
        "gnistor",
        "elstöt",
        "strömförande",
        "livsfarligt",
        "arbetsmiljö",
        "säkerhetsrisk",
    ),
    "sensitive_personal_data": (
        "personnummer",
        "sjukskriven",
        "diagnos",
        "läkarintyg",
        "skyddad identitet",
        "känsliga personuppgifter",
    ),
    "data_deletion": (
        "radera alla mina personuppgifter",
        "radera alla mina uppgifter",
        "radera mina personuppgifter",
        "ta bort mina personuppgifter",
        "gdpr-radering",
        "rätten att bli bortglömd",
    ),
    "mass_send": (
        "massutskick",
        "skicka till alla kunder",
        "alla mottagare",
        "hela kundlistan",
    ),
}


def combined_text(input_data: dict[str, Any]) -> str:
    subject = str(input_data.get("subject") or "")
    body = str(input_data.get("message_text") or "")
    return f"{subject} {body}".lower()


def _contains_phrase(text: str, phrase: str) -> bool:
    return bool(re.search(r"\b" + re.escape(phrase.lower()) + r"\b", text))


def assess_content_risk(input_data: dict[str, Any]) -> dict[str, Any]:
    """Return conservative do-not-touch signals for message content."""
    text = combined_text(input_data)
    categories: list[str] = []

    for category, keywords in _RISK_KEYWORDS.items():
        if any(_contains_phrase(text, kw) for kw in keywords):
            categories.append(category)

    return {
        "risk_detected": bool(categories),
        "categories": categories,
        "reasons": [f"risk:{category}" for category in categories],
        "needs_human": bool(categories),
        "approval_required": bool(categories),
        "route_to": "manual_review" if categories else None,
        "next_best_action": "manual_review" if categories else None,
    }
