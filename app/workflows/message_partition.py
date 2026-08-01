"""Partition inbound email text into current message and quoted history."""

from __future__ import annotations

import re

CONTRACT_VERSION = "message_partition_v1"

_QUOTE_MARKERS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^>{1,}\s?", re.MULTILINE),
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^-{2,}\s*Ursprungligt meddelande\s*-{2,}", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^On .+ wrote:\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Den .+ skrev:\s*$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Från:\s*.+$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^From:\s*.+$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Skickat:\s*.+$", re.IGNORECASE | re.MULTILINE),
    re.compile(r"^Sent:\s*.+$", re.IGNORECASE | re.MULTILINE),
)

_FORWARD_MARKERS: tuple[str, ...] = (
    "fwd:",
    "fw:",
    "vidarebefordrat",
    "forwarded message",
)


def is_forwarded_subject(subject: str) -> bool:
    lowered = (subject or "").strip().lower()
    return any(lowered.startswith(marker) for marker in _FORWARD_MARKERS)


def partition_message_text(body: str) -> tuple[str, str]:
    """Return (current_message, quoted_history) from raw email body."""
    text = (body or "").replace("\r\n", "\n")
    if not text.strip():
        return "", ""

    split_at: int | None = None
    for pattern in _QUOTE_MARKERS:
        match = pattern.search(text)
        if match and (split_at is None or match.start() < split_at):
            split_at = match.start()

    if split_at is None:
        return text.strip(), ""

    current = text[:split_at].strip()
    quoted = text[split_at:].strip()
    return current, quoted


def normalize_rfc_message_id(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.startswith("<") and raw.endswith(">"):
        return raw.lower()
    return f"<{raw.strip('<>')}>" if raw else ""
