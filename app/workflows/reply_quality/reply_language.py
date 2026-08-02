"""Authoritative reply language decision for customer-facing rendering."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

POLICY_VERSION = "reply_language_decision_v2"

_EN_MARKERS = (
    "thank",
    "hello",
    "hi ",
    "dear",
    "please",
    "quote",
    "need",
    "help",
    "we ",
    "our ",
    "house",
    "home",
    "battery",
    "charger",
    "solar",
    "follow",
    "status",
    "regards",
)
_SV_MARKERS = (
    "tack",
    "hej",
    "vänligen",
    "behöver",
    "vill",
    "undrar",
    "offert",
    "solcell",
    "batteri",
    "laddbox",
    "ärende",
    "status",
    "vår",
    "vårt",
    "villan",
    "fastighet",
    "installation",
    "reklamation",
    "problem",
    "återkom",
)
_PRODUCT_TERMS = frozenset(
    {
        "uppsala",
        "stockholm",
        "kwh",
        "brf",
        "ev",
        "niklas",
        "gmail",
    }
)


@dataclass(frozen=True)
class ReplyLanguageDecision:
    language: str
    confidence: float
    evidence: tuple[str, ...]
    fallback_reason: str | None
    policy_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "confidence": self.confidence,
            "evidence": list(self.evidence),
            "fallback_reason": self.fallback_reason,
            "policy_version": self.policy_version,
        }


def _score_markers(text: str, markers: tuple[str, ...]) -> int:
    lowered = text.lower()
    return sum(1 for marker in markers if marker in lowered)


def _strip_quoted_history(text: str) -> str:
    """Keep only the latest non-quoted customer-authored lines."""
    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            kept.append(line)
            continue
        if stripped.startswith(">"):
            continue
        if re.match(r"^on .+ wrote:$", stripped, re.I):
            break
        if stripped.startswith("-----Original Message-----"):
            break
        kept.append(line)
    return "\n".join(kept).strip()


def _customer_authored_text(input_data: dict[str, Any]) -> str:
    parts = [
        str(input_data.get("message_text") or ""),
        str(input_data.get("subject") or ""),
    ]
    combined = " ".join(part for part in parts if part).strip()
    return _strip_quoted_history(combined)


def authoritative_reply_language(
    *,
    input_data: dict[str, Any],
    profile_default_language: str = "sv",
    plan_language: str | None = None,
) -> ReplyLanguageDecision:
    """Single language authority used by plan, renderer, validators and oracles."""
    decision = decide_reply_language(
        input_data=input_data,
        profile_default_language=profile_default_language,
    )
    if plan_language and plan_language.lower().startswith(decision.language[:2]):
        return decision
    return decision


def decide_reply_language(
    *,
    input_data: dict[str, Any],
    profile_default_language: str = "sv",
) -> ReplyLanguageDecision:
    text = _customer_authored_text(input_data)
    evidence: list[str] = []
    fallback: str | None = None

    if not text.strip():
        lang = "en" if profile_default_language.lower().startswith("en") else "sv"
        return ReplyLanguageDecision(
            language=lang,
            confidence=0.4,
            evidence=("empty_customer_text", f"profile_default:{profile_default_language}"),
            fallback_reason="profile_default",
            policy_version=POLICY_VERSION,
        )

    en_score = _score_markers(text, _EN_MARKERS)
    sv_score = _score_markers(text, _SV_MARKERS)
    evidence.append(f"en_markers:{en_score}")
    evidence.append(f"sv_markers:{sv_score}")

    if re.search(r"\b(the|and|for|with|about|your)\b", text, re.I):
        en_score += 2
        evidence.append("en_function_words")
    if re.search(r"\b(och|att|för|med|vår|vårt|ärende)\b", text, re.I):
        sv_score += 2
        evidence.append("sv_function_words")

    if en_score > sv_score and en_score >= 2:
        confidence = min(0.95, 0.55 + 0.1 * (en_score - sv_score))
        return ReplyLanguageDecision(
            language="en",
            confidence=confidence,
            evidence=tuple(evidence),
            fallback_reason=None,
            policy_version=POLICY_VERSION,
        )
    if sv_score > en_score and sv_score >= 2:
        confidence = min(0.95, 0.55 + 0.1 * (sv_score - en_score))
        return ReplyLanguageDecision(
            language="sv",
            confidence=confidence,
            evidence=tuple(evidence),
            fallback_reason=None,
            policy_version=POLICY_VERSION,
        )

    lang = "en" if profile_default_language.lower().startswith("en") else "sv"
    fallback = "profile_default_tie_or_low_confidence"
    return ReplyLanguageDecision(
        language=lang,
        confidence=0.5,
        evidence=tuple(evidence + [f"profile_default:{profile_default_language}"]),
        fallback_reason=fallback,
        policy_version=POLICY_VERSION,
    )


def localized_greeting(*, language: str, signature_name: str | None = None) -> str:
    if language == "en":
        return "Hi,"
    return "Hej,"


def localized_closing(*, language: str) -> str:
    return "Kind regards" if language == "en" else "Vänliga hälsningar"
