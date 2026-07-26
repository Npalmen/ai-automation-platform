"""Deterministic, conservative normalizers for customer identity matching."""

from __future__ import annotations

import re
import unicodedata

from app.domain.customer.schemas import StructuredAddressInput

_ROLE_BASED_LOCAL_PARTS = frozenset(
    {
        "info",
        "support",
        "faktura",
        "invoice",
        "order",
        "kontakt",
        "kundservice",
        "admin",
    }
)

_PHONE_SEPARATORS_RE = re.compile(r"[\s().\-/]+")
_NON_DIGIT_RE = re.compile(r"\D+")


def normalize_email(raw: str | None) -> tuple[str, bool] | None:
    """Return (normalized_email, is_role_based) or None when unsafe to normalize."""
    if raw is None:
        return None
    text = unicodedata.normalize("NFKC", raw).strip()
    if not text or text.count("@") != 1:
        return None
    local, domain = text.split("@", 1)
    local_part = local.strip()
    domain_part = domain.strip()
    if not local_part or not domain_part or "." not in domain_part:
        return None
    normalized_local = local_part.casefold()
    normalized_domain = domain_part.casefold()
    if not normalized_local or not normalized_domain:
        return None
    is_role_based = normalized_local in _ROLE_BASED_LOCAL_PARTS
    return f"{normalized_local}@{normalized_domain}", is_role_based


def normalize_phone(raw: str | None, country_code: str | None = None) -> str | None:
    """Normalize phone to digits with optional leading +; None when ambiguous."""
    if raw is None:
        return None
    text = unicodedata.normalize("NFKC", raw).strip()
    if not text:
        return None

    region = (country_code or "").strip().upper()
    compact = _PHONE_SEPARATORS_RE.sub("", text)
    if compact.startswith("00"):
        compact = "+" + compact[2:]
    elif compact.startswith("+"):
        pass
    elif region == "SE" and compact.startswith("0"):
        compact = "+46" + compact[1:]
    elif region == "SE":
        return None
    elif compact.startswith("0"):
        return None

    if compact.startswith("+"):
        digits = "+" + _NON_DIGIT_RE.sub("", compact[1:])
        digit_body = digits[1:]
    else:
        digit_body = _NON_DIGIT_RE.sub("", compact)
        digits = digit_body

    if not digit_body or not digit_body.isdigit():
        return None
    if len(digit_body) < 7 or len(digit_body) > 15:
        return None
    return digits


def normalize_organization_number(
    raw: str | None,
    country_code: str | None = None,
) -> str | None:
    """Conservative Swedish org-number normalization to ten digits."""
    if raw is None:
        return None
    region = (country_code or "SE").strip().upper()
    if region != "SE":
        digits = _NON_DIGIT_RE.sub("", unicodedata.normalize("NFKC", raw))
        return digits if 6 <= len(digits) <= 14 else None

    digits = _NON_DIGIT_RE.sub("", unicodedata.normalize("NFKC", raw))
    if len(digits) == 12 and digits.startswith("16"):
        digits = digits[2:]
    if len(digits) != 10 or not digits.isdigit():
        return None
    return digits


def normalize_name(raw: str | None) -> str | None:
    """Normalize personal or company name for weak comparison only."""
    if raw is None:
        return None
    text = unicodedata.normalize("NFKC", raw).strip()
    if not text:
        return None
    collapsed = " ".join(text.split())
    if not collapsed:
        return None
    return collapsed.casefold()


def normalize_structured_address(address: StructuredAddressInput | None) -> str | None:
    """Canonical structured address key without geocoding."""
    if address is None:
        return None
    parts: list[str] = []
    for value in (
        address.street,
        address.postal_code,
        address.city,
        address.region,
        address.country_code,
    ):
        if value is None:
            continue
        text = unicodedata.normalize("NFKC", value).strip()
        if text:
            parts.append(text.casefold())
    if not parts:
        return None
    return "|".join(parts)


def is_role_based_email_local_part(local_part: str) -> bool:
    folded = unicodedata.normalize("NFKC", local_part).strip().casefold()
    return folded in _ROLE_BASED_LOCAL_PARTS
