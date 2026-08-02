"""Customer-facing surface contract — block internal metadata in replies."""

from __future__ import annotations

import re
from typing import Any

POLICY_VERSION = "customer_surface_contract_v3"

_INTERNAL_METADATA_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bservice\s*:", re.I),
    re.compile(r"\blocation\s*:", re.I),
    re.compile(r"\bcontact\s+name\b", re.I),
    re.compile(r"\bknown-[a-z_]+\b", re.I),
    re.compile(r"\bknown_[a-z_]+\b", re.I),
    re.compile(r"\brule_trace\b", re.I),
    re.compile(r"\bprofile_version\b", re.I),
    re.compile(r"\bpolicy_version\b", re.I),
    re.compile(r"\bplaybook_id\b", re.I),
    re.compile(r"\bptb-dcq-\d+\b", re.I),
    re.compile(r"\beval\.test\b", re.I),
    re.compile(r"\bexclude:[a-z_]+:", re.I),
    re.compile(r"\bselect:[a-z_]+:", re.I),
    re.compile(r"\{[a-z_]+\}"),
    re.compile(r"\b[a-z]+_[a-z]+_[a-z]+\b"),
)

_PLACEHOLDER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b0 veckor sedan\b", re.I),
    re.compile(r"\bfor 0 weeks\b", re.I),
    re.compile(r"\[REDACTED", re.I),
    re.compile(r"<[A-Z_]+>"),
)

_SV_INDICATORS = re.compile(
    r"\b(hej|tack|vi |er |för |och |behöver|återkom|vänliga|hälsningar|ärende|solcell|laddbox|batteri)\b",
    re.I,
)
_EN_INDICATORS = re.compile(
    r"\b(hi|thank|we |your |for |and |please|kind regards|case|solar|charger|battery|need)\b",
    re.I,
)
_ROBOTIC_SEGMENTS = (
    "vi tittar på förutsättningarna",
    "nästa steg är att samla in underlag",
    "we are reviewing the",
    "next step is to collect",
)

_UNLOCALIZED_FACT_LABEL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bcase reference\b", re.I),
    re.compile(r"\bcustomer identifier\b", re.I),
    re.compile(r"\bstatus dimension\b", re.I),
    re.compile(r"\bissue summary\b", re.I),
    re.compile(r"\bissue description\b", re.I),
    re.compile(r"\bcase reference och customer identifier\b", re.I),
    re.compile(r"\bcase reference and customer identifier\b", re.I),
)

_INTERNAL_ENGLISH_IN_SV = re.compile(
    r"\b(case reference|customer identifier|issue summary|status dimension|kind regards|thank you for your)\b",
    re.I,
)
_INTERNAL_SWEDISH_IN_EN = re.compile(
    r"\b(hej,|vänliga hälsningar|för att vi ska|tack för din|ärendenummer)\b",
    re.I,
)


def detect_internal_metadata_leaks(body: str) -> list[str]:
    issues: list[str] = []
    for pattern in _INTERNAL_METADATA_PATTERNS:
        if pattern.search(body or ""):
            issues.append(f"internal_metadata:{pattern.pattern}")
    return issues


def detect_unresolved_placeholders(body: str) -> list[str]:
    issues: list[str] = []
    for pattern in _PLACEHOLDER_PATTERNS:
        if pattern.search(body or ""):
            issues.append(f"placeholder:{pattern.pattern}")
    return issues


def detect_unlocalized_fact_labels(body: str) -> list[str]:
    issues: list[str] = []
    text = body or ""
    for pattern in _UNLOCALIZED_FACT_LABEL_PATTERNS:
        if pattern.search(text):
            issues.append(f"unlocalized_fact_label:{pattern.pattern}")
    if re.search(r"\b[a-z]{3,}_[a-z]{3,}\b", text):
        issues.append("unlocalized_fact_label:snake_case_field")
    return issues


def detect_mixed_language(body: str, *, expected_language: str) -> list[str]:
    text = body or ""
    sv_hits = len(_SV_INDICATORS.findall(text))
    en_hits = len(_EN_INDICATORS.findall(text))
    if expected_language == "en" and sv_hits >= 2 and en_hits >= 2:
        return ["mixed_language:en_expected_sv_fragments"]
    if expected_language == "sv" and sv_hits >= 2 and en_hits >= 2:
        return ["mixed_language:sv_expected_en_fragments"]
    if expected_language == "en":
        if re.search(r"\b(hej,|vänliga hälsningar|för att vi ska|tack för att ni)\b", text, re.I):
            return ["mixed_language:sv_fragment_in_en_reply"]
        if _INTERNAL_SWEDISH_IN_EN.search(text):
            return ["mixed_language:sv_fragment_in_en_reply"]
    if expected_language == "sv":
        if re.search(r"\b(hi,|kind regards|thank you for your)\b", text, re.I):
            return ["mixed_language:en_fragment_in_sv_reply"]
        if _INTERNAL_ENGLISH_IN_SV.search(text):
            return ["mixed_language:en_fragment_in_sv_reply"]
    return []


def detect_semantic_placeholders(body: str) -> list[str]:
    issues: list[str] = []
    text = body or ""
    if re.search(r"\bCity\b", text):
        issues.append("semantic_placeholder:City")
    if re.search(r"\bin city\b", text, re.I):
        issues.append("semantic_placeholder:in_city")
    if re.search(r"\bknown-[a-z_]+\b", text, re.I):
        issues.append("semantic_placeholder:known_entity")
    if re.search(r"\b(meddelande|message)\s+\d+\s+om\b", text, re.I):
        issues.append("semantic_placeholder:transport_message")
    if re.search(r"\bkompletterande info punkt\b", text, re.I):
        issues.append("semantic_placeholder:continuation_transport")
    if re.search(r"\boffertförfrågan\s+0\b", text, re.I):
        issues.append("semantic_placeholder:invalid_quote_ref_0")
    return issues


def detect_robotic_template_composition(body: str) -> list[str]:
    lowered = (body or "").lower()
    hits = sum(1 for segment in _ROBOTIC_SEGMENTS if segment in lowered)
    issues: list[str] = []
    if hits >= 2:
        issues.append("natural_surface:robotic_segment_stack")
    if re.search(r"\b(?:skicka|send).+\boch om\b", body or "", re.I):
        issues.append("natural_surface:send_clause_with_om_object")
    if re.search(r"\bkan (?:du|ni) skicka .+ och om\b", body or "", re.I):
        issues.append("natural_surface:malformed_send_and_om")
    return issues


def detect_key_value_fragments(body: str) -> list[str]:
    if re.search(r"\b[a-z_]{3,}\s*:\s*[a-z0-9_-]+\b", body or "", re.I):
        return ["natural_surface:key_value_fragment"]
    return []


def validate_customer_surface(
    body: str,
    *,
    expected_language: str,
) -> dict[str, Any]:
    issues: list[str] = []
    issues.extend(detect_internal_metadata_leaks(body))
    issues.extend(detect_unresolved_placeholders(body))
    issues.extend(detect_unlocalized_fact_labels(body))
    issues.extend(detect_semantic_placeholders(body))
    issues.extend(detect_mixed_language(body, expected_language=expected_language))
    issues.extend(detect_robotic_template_composition(body))
    issues.extend(detect_key_value_fragments(body))
    return {
        "passed": not issues,
        "issues": issues,
        "policy_version": POLICY_VERSION,
    }
