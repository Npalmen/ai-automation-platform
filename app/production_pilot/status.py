"""Production pilot status markers."""

from __future__ import annotations

from typing import Any

from app.production_pilot.constants import PRODUCTION_PILOT_P1_OBSERVE_QUALIFIED

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


PRODUCTION_PILOT_P1_OPERATIONAL_READY = "PRODUCTION_PILOT_P1_OPERATIONAL_READY"


def evaluate_operational_ready_status(
    *,
    readiness: dict[str, Any],
    runtime_readiness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registered: list[str] = []
    blocked: list[str] = []
    if readiness.get("overall_status") != "ready_for_p1_activation":
        blocked.append("readiness_blockers")
    elif not runtime_readiness or runtime_readiness.get("overall_status") != "ready_for_operational_attach":
        blocked.append("runtime_readiness_pending")
    else:
        registered.append(PRODUCTION_PILOT_P1_OPERATIONAL_READY)
    return {
        "registered": registered,
        "blocked": blocked,
        "p2_status": "NO-GO",
    }


def evaluate_p1_status(
    *,
    readiness: dict[str, Any],
    preflight: dict[str, Any] | None = None,
    evaluation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registered: list[str] = []
    blocked: list[str] = []
    if readiness.get("overall_status") != "ready_for_p1_activation":
        blocked.append("readiness_blockers")
    elif not preflight or preflight.get("status") != "PASS":
        blocked.append("p1_preflight_pending")
    elif not evaluation or evaluation.get("status") != "PASS":
        blocked.append("p1_evaluation_pending")
    else:
        registered.append(PRODUCTION_PILOT_P1_OBSERVE_QUALIFIED)
        registered.append(PRODUCTION_PILOT_ACTIVE)
    return {
        "registered": registered,
        "blocked": blocked,
        "not_registered": [PRODUCTION_GA],
    }
