"""Redaction helpers for pilot observability reports."""

from __future__ import annotations

import hashlib
import re

_EMAIL_RE = re.compile(r"[^@<\s]+@[^@\s>]+")


def hash_ref(value: str | None, *, prefix: str = "") -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    digest = hashlib.sha256(f"{prefix}:{raw}".encode("utf-8")).hexdigest()
    return digest[:16]


def redact_email(value: str | None) -> str:
    if not value:
        return ""
    return _EMAIL_RE.sub("[redacted-email]", value)


def provider_message_ref_hash(tenant_id: str, message_id: str) -> str:
    return hashlib.sha256(f"{tenant_id}:{message_id}".encode("utf-8")).hexdigest()
