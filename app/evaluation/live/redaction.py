"""Recursive redaction for live-eval journals and telemetry."""

from __future__ import annotations

from typing import Any

FORBIDDEN_KEYS = frozenset(
    {
        "authorization",
        "access_token",
        "refresh_token",
        "api_key",
        "secret",
        "password",
        "prompt",
        "raw_prompt",
        "email_body",
        "body",
        "body_text",
        "message_body",
        "message_text",
        "full_text",
    }
)

_MAX_STRING_LEN = 512


def _is_forbidden_key(key: object) -> bool:
    return isinstance(key, str) and key.lower() in FORBIDDEN_KEYS


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: redact_sensitive(item)
            for key, item in value.items()
            if not _is_forbidden_key(key)
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    if isinstance(value, str) and len(value) > _MAX_STRING_LEN:
        return value[:_MAX_STRING_LEN] + "…"
    return value
