"""Versioned HMAC fingerprints for action diagnostics (not operation identity)."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

FINGERPRINT_KEY_VERSION = 1


def _canonical_action_fields(action: dict[str, Any]) -> dict[str, Any]:
    action_type = str(action.get("type") or "")
    target = (
        action.get("to")
        or action.get("item_name")
        or action.get("channel")
        or ""
    )
    subject = str(action.get("subject") or "")
    subject_digest = hashlib.sha256(subject.encode("utf-8")).hexdigest()[:16] if subject else None
    return {
        "action_type": action_type,
        "target": str(target).strip().lower(),
        "tenant_id": str(action.get("tenant_id") or ""),
        "subject_digest": subject_digest,
    }


def compute_action_fingerprint(action: dict[str, Any]) -> tuple[str | None, int | None]:
    """Return (fingerprint, key_version) or (None, None) when HMAC key is unset."""
    from app.core.settings import get_settings

    secret = (get_settings().DECISION_RECORD_HMAC_KEY or "").strip()
    if not secret:
        return None, None

    payload = json.dumps(_canonical_action_fields(action), sort_keys=True, separators=(",", ":"))
    digest = hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return digest, FINGERPRINT_KEY_VERSION
