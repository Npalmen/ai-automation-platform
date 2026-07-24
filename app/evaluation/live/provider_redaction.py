"""Sanitize provider-facing error text before journals, artifacts, or logs."""

from __future__ import annotations

import re

_MAX_DIAGNOSTIC_LEN = 240
_BEARER_RE = re.compile(r"Bearer\s+\S+", re.IGNORECASE)
_API_KEY_RE = re.compile(r"(api[_-]?key|authorization)\s*[:=]\s*\S+", re.IGNORECASE)
_SK_PREFIX_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def sanitize_provider_error_message(message: str | BaseException | None) -> str:
    text = str(message or "").strip()
    if not text:
        return ""
    text = _BEARER_RE.sub("<redacted-auth>", text)
    text = _API_KEY_RE.sub(r"\1=<redacted>", text)
    text = _SK_PREFIX_RE.sub("<redacted-api-key>", text)
    text = _EMAIL_RE.sub("<redacted-email>", text)
    if "LLM raw response is not valid JSON:" in text:
        return "LLM raw response is not valid JSON"
    if "LLM returned invalid JSON content:" in text:
        return "LLM returned invalid JSON content"
    if "LLM HTTPError" in text:
        match = re.search(r"LLM HTTPError (\d{3})", text)
        if match:
            return f"LLM HTTPError {match.group(1)}"
        return "LLM HTTPError"
    if len(text) > _MAX_DIAGNOSTIC_LEN:
        return text[:_MAX_DIAGNOSTIC_LEN] + "…"
    return text
