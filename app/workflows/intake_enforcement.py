"""Gmail intake cutoff enforcement (Onboarding 2.0, DEC-032)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

SKIP_REASON_BEFORE_CUTOFF = "before_intake_cutoff"
SKIP_REASON_MISSING_CUTOFF = "missing_intake_cutoff"
DEDUPE_KEY_BEFORE_CUTOFF = "intake.before_cutoff"
DEDUPE_KEY_MISSING_CUTOFF = "intake.missing_cutoff"


def parse_gmail_internal_date_ms(internal_date_ms: str | int | None) -> datetime | None:
    """Parse Gmail internalDate (epoch ms) to UTC datetime."""
    if internal_date_ms is None:
        return None
    try:
        ms = int(internal_date_ms)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)


def parse_cutoff_at(cutoff_raw: str | None) -> datetime | None:
    if not cutoff_raw:
        return None
    text = str(cutoff_raw).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def evaluate_intake_gate(
    *,
    tenant_id: str,
    lifecycle_status: str,
    intake_settings: dict[str, Any] | None,
    message_internal_date_ms: str | int | None,
) -> dict[str, Any]:
    """
    Fail-closed intake gate before job creation.

    Returns dict with allowed: bool, reason, dedupe_key (for alerts).
    """
    intake = intake_settings or {}
    cutoff = parse_cutoff_at(intake.get("intake_cutoff_at") or intake.get("activation_cutoff_at"))

    if lifecycle_status == "active" and cutoff is None:
        return {
            "allowed": False,
            "reason": SKIP_REASON_MISSING_CUTOFF,
            "dedupe_key": DEDUPE_KEY_MISSING_CUTOFF,
            "tenant_id": tenant_id,
        }

    if cutoff is None:
        return {"allowed": True, "reason": None, "dedupe_key": None, "tenant_id": tenant_id}

    msg_at = parse_gmail_internal_date_ms(message_internal_date_ms)
    if msg_at is None:
        return {
            "allowed": False,
            "reason": SKIP_REASON_MISSING_CUTOFF,
            "dedupe_key": DEDUPE_KEY_MISSING_CUTOFF,
            "tenant_id": tenant_id,
        }

    if msg_at < cutoff:
        return {
            "allowed": False,
            "reason": SKIP_REASON_BEFORE_CUTOFF,
            "dedupe_key": DEDUPE_KEY_BEFORE_CUTOFF,
            "tenant_id": tenant_id,
            "message_at": msg_at.isoformat(),
            "cutoff_at": cutoff.isoformat(),
        }

    return {"allowed": True, "reason": None, "dedupe_key": None, "tenant_id": tenant_id}
