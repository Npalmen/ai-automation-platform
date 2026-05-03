"""Lead Scoring Engine.

Deterministic rule-based scoring (0–100). Returns score, category, and reasons.
"""
from __future__ import annotations

import re

from app.lead.models import LeadAnalysis, LeadScore, MissingInfoResult, ScoreCategory


_BUYING_KEYWORDS = [
    "offert", "pris", "installera", "boka", "köpa", "beställa",
    "när kan ni komma", "prisuppgift", "intresserad av att gå vidare",
]

_WEAK_KEYWORDS = [
    "funderar bara", "kanske", "tittar runt", "jämföra priser",
    "ingen brådska", "inga planer",
]


def _any_keyword(text: str, keywords: list[str]) -> bool:
    return any(re.search(r"\b" + re.escape(kw) + r"\b", text) for kw in keywords)


def _category(score: int) -> ScoreCategory:
    if score >= 70:
        return "hot"
    if score >= 40:
        return "warm"
    return "cold"


def score_lead(
    analysis: LeadAnalysis,
    missing_info: MissingInfoResult,
    entities: dict,
    input_data: dict,
) -> LeadScore:
    subject = (input_data.get("subject") or "").lower()
    body = (input_data.get("message_text") or "").lower()
    text = f"{subject} {body}"

    points = 0
    reasons: list[str] = []

    # Intent
    if analysis.intent == "ready_to_buy":
        points += 25
        reasons.append("intent:ready_to_buy (+25)")
    elif analysis.intent == "comparing":
        points += 15
        reasons.append("intent:comparing (+15)")

    # Urgency
    if analysis.urgency == "high":
        points += 20
        reasons.append("urgency:high (+20)")
    elif analysis.urgency == "medium":
        points += 8
        reasons.append("urgency:medium (+8)")

    # Completeness
    if missing_info.completeness_score >= 0.8:
        points += 20
        reasons.append("completeness:>=0.8 (+20)")
    elif missing_info.completeness_score >= 0.5:
        points += 8
        reasons.append("completeness:>=0.5 (+8)")

    # Contact info present
    contact_score = 0
    if entities.get("email"):
        contact_score += 4
    if entities.get("phone"):
        contact_score += 3
    if entities.get("address") or entities.get("city"):
        contact_score += 3
    if contact_score > 0:
        points += contact_score
        reasons.append(f"contact_info (+{contact_score})")

    # Strong buying keywords
    if _any_keyword(text, _BUYING_KEYWORDS):
        points += 10
        reasons.append("buying_keywords (+10)")

    # Weak/research language — penalty
    if _any_keyword(text, _WEAK_KEYWORDS):
        points -= 10
        reasons.append("weak_language (-10)")

    # Known lead_type adds credibility
    if analysis.lead_type != "unknown":
        points += 5
        reasons.append(f"lead_type:{analysis.lead_type} (+5)")

    score = max(0, min(100, points))
    return LeadScore(score=score, category=_category(score), reasons=reasons)
