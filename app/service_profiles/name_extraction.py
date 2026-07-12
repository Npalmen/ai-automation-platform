"""Customer name extraction from email body signatures.

For demo and real Gmail use cases, the Gmail sender name may be the tenant/owner
account (e.g. "Niklas Palm") while the simulated customer name is in the body:
  "Mvh Anders", "Med vänlig hälsning Lena", "Hälsningar Per", "/Anders"

This module prefers the body signature name when:
  - A clear signature pattern is found in the body, AND
  - The body name differs from the sender name's first word

Public API:
    extract_body_signature_name(message_text) -> str | None
    resolve_customer_name(sender_name, message_text)  -> str
"""
from __future__ import annotations

import re


# ── Signature patterns ────────────────────────────────────────────────────────

# Ordered by specificity — more specific patterns first.
# Each pattern must have exactly one capturing group: the person's first name.
_SIGNATURE_PATTERNS: list[re.Pattern[str]] = [
    # "Med vänlig hälsning Lena" / "Med vänliga hälsningar Per"
    re.compile(
        r"med\s+v[äa]nli(?:ga?\s+h[äa]lsningar?|g\s+h[äa]lsning)\s*[,.]?\s*([A-ZÅÄÖ][a-zåäö]{1,20})\b",
        re.IGNORECASE,
    ),
    # "Mvh Lena" / "Mvh. Anders"
    re.compile(
        r"\bmvh\.?\s+([A-ZÅÄÖ][a-zåäö]{1,20})\b",
        re.IGNORECASE,
    ),
    # "Hälsningar Per" / "Hälsningar, Per"
    re.compile(
        r"\bh[äa]lsningar[,.]?\s+([A-ZÅÄÖ][a-zåäö]{1,20})\b",
        re.IGNORECASE,
    ),
    # "/Anders" — slash signature style
    re.compile(
        r"(?:^|\n)/\s*([A-ZÅÄÖ][a-zåäö]{1,20})\b",
        re.IGNORECASE,
    ),
    # "Vänligen, Sara" / "Vänligen Sara"
    re.compile(
        r"\bv[äa]nligen[,.]?\s+([A-ZÅÄÖ][a-zåäö]{1,20})\b",
        re.IGNORECASE,
    ),
    # "Tack, Lena" / "Tack på förhand, Per"
    re.compile(
        r"\btack(?:\s+p[åa]\s+f[öo]rhand)?[,.]?\s+([A-ZÅÄÖ][a-zåäö]{1,20})\b",
        re.IGNORECASE,
    ),
]

# Words that look like names but are NOT person names
_NAME_BLOCKLIST: frozenset[str] = frozenset({
    "test", "demo", "kund", "admin", "support", "info", "kontakt",
    "mail", "email", "noreply", "reply", "no",
    # Swedish common false positives
    "mvh", "hej", "med", "vän", "här", "att", "det", "för",
    "och", "eller", "men", "som", "när", "kan", "ska",
})

# Swedish common first names — helps validate extracted names
_SWEDISH_NAMES: frozenset[str] = frozenset({
    "anna", "anders", "erik", "lena", "per", "sara", "maria", "lars",
    "karin", "johan", "emma", "niklas", "sofia", "magnus", "elin",
    "david", "lisa", "jonas", "kristina", "peter", "eva", "daniel",
    "ingrid", "stefan", "jenny", "mikael", "helena", "fredrik",
    "katarina", "hans", "marie", "thomas", "ida", "henrik", "anna",
    "torbjörn", "björn", "göran", "sven", "gunnar", "rolf", "leif",
    "bo", "christer", "ulf", "bengt", "jan", "lennart",
})


def extract_body_signature_name(message_text: str) -> str | None:
    """Extract a person first name from an email body signature.

    Returns the capitalized first name, or None if no clear signature found.
    Does NOT return phone numbers, company names, or blocklisted words.
    """
    if not message_text:
        return None

    for pattern in _SIGNATURE_PATTERNS:
        match = pattern.search(message_text)
        if not match:
            continue

        name = match.group(1).strip()

        # Safety checks
        if not name or len(name) < 2:
            continue
        if re.search(r"\d", name):
            continue  # Contains digits — not a name
        if name.lower() in _NAME_BLOCKLIST:
            continue

        return name.capitalize()

    return None


def resolve_customer_name(
    sender_name: str,
    message_text: str,
) -> str:
    """Return the best customer name for use in greetings.

    Prefers a clear body signature name over the Gmail sender name when:
    - The body contains a clear signature name, AND
    - The body name differs from the sender name's first word (case-insensitive)

    This handles the common demo scenario where the Gmail sender is the tenant
    account owner (e.g. "Niklas Palm") but the simulated customer signed
    "Mvh Anders" or "Med vänlig hälsning Lena" in the message body.

    Args:
        sender_name: Gmail/email sender's display name (may be tenant owner)
        message_text: Raw email body text

    Returns:
        The resolved customer name (may be same as sender_name if no body sig found)
    """
    body_name = extract_body_signature_name(message_text or "")
    if not body_name:
        return sender_name or ""

    # Compare with sender first name
    sender_first = ""
    if sender_name and sender_name.strip():
        sender_first = sender_name.strip().split()[0].lower()

    if body_name.lower() == sender_first:
        # Same name — body confirms sender, use sender
        return sender_name or body_name

    # Different names — prefer body signature name (more likely to be the actual customer)
    return body_name
