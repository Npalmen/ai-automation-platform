"""Canonical recipient identity resolution for live-eval Gmail OAuth."""

from __future__ import annotations

import re
from typing import Any

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_verified_email_address(value: str | None) -> bool:
    """Return True for syntactically valid email addresses; never treat 'me' as email."""
    candidate = (value or "").strip().lower()
    if not candidate or candidate == "me":
        return False
    return bool(_EMAIL_RE.match(candidate))


def resolve_canonical_recipient_email(
    connection_config: dict[str, Any],
    *,
    metadata: dict[str, Any] | None = None,
    allowlist: frozenset[str] | None = None,
) -> tuple[str | None, str | None]:
    """
    Resolve exactly one canonical recipient email for eval intake trust validation.

    Priority:
    1. metadata_json.email when syntactically valid
    2. connection user_id only when syntactically valid (never "me")
    3. fail-closed
    """
    meta = metadata if metadata is not None else {}
    meta_email = str(meta.get("email") or "").strip().lower()
    user_id = str(connection_config.get("user_id") or "").strip().lower()

    meta_valid = is_verified_email_address(meta_email)
    user_valid = is_verified_email_address(user_id)

    if meta_valid and user_valid and meta_email != user_id:
        return None, "recipient_identity_conflict"

    if meta_valid:
        canonical = meta_email
    elif user_valid:
        canonical = user_id
    else:
        return None, "recipient_identity_unverified"

    if allowlist is not None:
        normalized = {item.strip().lower() for item in allowlist if item}
        if canonical not in normalized:
            return None, "recipient_not_allowlisted"

    return canonical, None
