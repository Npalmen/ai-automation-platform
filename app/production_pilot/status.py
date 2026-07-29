"""Production pilot status markers."""

from __future__ import annotations

from typing import Any

PRODUCTION_PILOT_RELEASE_READY = "PRODUCTION_PILOT_RELEASE_READY"
PRODUCTION_PILOT_ACTIVE = "PRODUCTION_PILOT_ACTIVE"
PRODUCTION_GA = "PRODUCTION_GA"


def evaluate_release_status(
    *,
    readiness: dict[str, Any],
    preflight: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registered: list[str] = []
    blocked: list[str] = []
    if readiness.get("overall_status") == "ready_for_p0_preflight":
        if preflight and preflight.get("status") == "PASS":
            registered.append(PRODUCTION_PILOT_RELEASE_READY)
        else:
            blocked.append("p0_preflight_pending")
    else:
        blocked.append("readiness_blockers")
    if PRODUCTION_PILOT_ACTIVE in registered or PRODUCTION_GA in registered:
        blocked.append("activation_not_allowed_in_p0")
    return {
        "registered": registered,
        "blocked": blocked,
        "not_registered": [PRODUCTION_PILOT_ACTIVE, PRODUCTION_GA],
    }
