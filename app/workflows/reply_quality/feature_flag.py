"""Feature flag for digital coworker reply path (eval-first rollout)."""

from __future__ import annotations

import os
from typing import Any

LIVE_EVAL_TENANT = "TENANT_LIVE_EVAL"


def is_digital_coworker_reply_enabled(
    *,
    tenant_id: str | None,
    automation_settings: dict[str, Any] | None = None,
) -> bool:
    """Return True when the coworker reply pipeline should replace legacy safe-ack rendering."""
    settings = automation_settings or {}
    if settings.get("digital_coworker_reply_enabled") is True:
        return True
    if settings.get("digital_coworker_reply_enabled") is False:
        return False
    env = os.environ.get("DIGITAL_COWORKER_REPLY_ENABLED", "").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if env in ("1", "true", "yes", "on"):
        return tenant_id == LIVE_EVAL_TENANT
    # Fail-closed: legacy safe-ack remains default until explicitly enabled.
    return False
