"""Structured pre-write safety gate for outbound customer reply candidates.

Runs on the exact reply body before authorization and external dispatch.
Conservative: blocks binding language; allows neutral acknowledgements only.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any

REPLY_SAFETY_FAILED = "reply_candidate_safety_failed"

_FORBIDDEN_PATTERNS: tuple[tuple[str, str], ...] = (
    ("concrete_price", r"\b\d{2,}\s*(?:kr|sek|:-)\b"),
    ("concrete_price", r"\b(?:kostar|priset|pris)\s+(?:är|ca\.?|cirka)\s+\d"),
    ("discount", r"\b(?:rabatt|nedsatt|procent\s+rabatt)\b"),
    ("booked_time", r"\b(?:bokad|inbokad|bokat)\s+(?:tid|datum|besök)\b"),
    ("booked_time", r"\b(?:kl\.?\s*)?\d{1,2}[:.]\d{2}\s*(?:på\s+\w+)?\s*(?:måndag|tisdag|onsdag|torsdag|fredag|lördag|söndag)\b"),
    ("delivery_promise", r"\b(?:garanterad|garanterat|garanterar)\s+(?:leverans|leveranstid)\b"),
    ("delivery_promise", r"\b(?:levereras|klart)\s+(?:senast|inom)\s+\d+\s+(?:dag|dagar|veck)\b"),
    ("technical_guarantee", r"\b(?:garanti|garanterar)\s+(?:att|för)\b"),
    ("legal_commitment", r"\b(?:juridiskt|juridisk|rättsligt)\s+(?:bindande|besked)\b"),
    ("economic_commitment", r"\b(?:ekonomiskt|ekonomisk)\s+(?:löfte|besked|åtagande)\b"),
    ("binding_quote", r"\b(?:bindande|fast)\s+offert\b"),
    ("work_approval", r"\b(?:godkänner|accepterar)\s+(?:arbetet|uppdraget|beställningen)\b"),
    ("order_confirmation", r"\b(?:beställningen|ordern)\s+(?:är\s+)?(?:bekräftad|registrerad|mottagen)\b"),
    ("order_confirmation", r"\b(?:arbetet|uppdraget)\s+är\s+beställt\b"),
    ("contractual_commitment", r"\b(?:avtalsenligt|avtalsmässigt)\s+åtagande\b"),
    # English fallbacks
    ("concrete_price", r"\b(?:price|cost)\s+(?:is|of)\s+\d"),
    ("booked_time", r"\b(?:booked|scheduled)\s+(?:for|on)\b"),
    ("binding_quote", r"\bbinding\s+quote\b"),
)

_ALLOWED_NEUTRAL_MARKERS: tuple[str, ...] = (
    r"\btack\s+för",
    r"\bvi\s+har\s+mottagit",
    r"\bvi\s+återkommer",
    r"\bvi\s+hör\s+av\s+oss",
    r"\bskicka\s+gärna",
    r"\bhej\b",
)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _sha256_text(text: str) -> str:
    return hashlib.sha256(_normalize_text(text).encode("utf-8")).hexdigest()


def assess_reply_candidate_safety(body: str | None) -> dict[str, Any]:
    """Return structured safety assessment for a reply candidate body."""
    text = _normalize_text(body or "")
    violations: list[str] = []
    reason_codes: list[str] = []

    if not text:
        return {
            "passed": False,
            "violations": ["empty_reply_candidate"],
            "reason_codes": [REPLY_SAFETY_FAILED, "empty_reply_candidate"],
            "content_hash": _sha256_text(""),
        }

    for code, pattern in _FORBIDDEN_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            violations.append(code)
            if code not in reason_codes:
                reason_codes.append(code)

    passed = not violations
    if not passed:
        reason_codes = [REPLY_SAFETY_FAILED, *reason_codes]

    return {
        "passed": passed,
        "violations": violations,
        "reason_codes": reason_codes,
        "content_hash": _sha256_text(body or ""),
        "has_neutral_marker": any(
            re.search(marker, text, re.IGNORECASE) for marker in _ALLOWED_NEUTRAL_MARKERS
        ),
    }


def verify_sent_reply_matches_approved_candidate(
    *,
    approved_hash: str | None,
    sent_body: str | None,
) -> dict[str, Any]:
    """Post-write check: sent content must match pre-write approved candidate hash."""
    sent_hash = _sha256_text(sent_body or "")
    if not approved_hash:
        return {
            "passed": False,
            "reason_codes": ["missing_approved_reply_hash"],
            "approved_hash": approved_hash,
            "sent_hash": sent_hash,
        }
    passed = approved_hash == sent_hash
    return {
        "passed": passed,
        "reason_codes": [] if passed else ["sent_reply_hash_mismatch"],
        "approved_hash": approved_hash,
        "sent_hash": sent_hash,
    }
