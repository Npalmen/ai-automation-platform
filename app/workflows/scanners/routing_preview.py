"""
Routing preview resolver.

Deterministic, read-only.  Inspects tenant_memory.routing_hints for a given
job type and classifies whether routing is ready, missing, or malformed.

Output shape
------------
{
  "job_type": "lead",
  "status": "ready" | "missing_hint" | "invalid_hint",
  "system": "monday" | null,
  "target": { ... } | null,
  "message": "<human-readable Swedish explanation>"
}

No network or DB calls — pure function.
"""

from __future__ import annotations

SUPPORTED_JOB_TYPES: list[str] = [
    "lead",
    "customer_inquiry",
    "invoice",
    "partnership",
    "supplier",
    "support",
    "internal",
]

_REQUIRED_TARGET_KEYS: set[str] = {"board_id", "board_name"}


def _validate_hint(hint: dict) -> str | None:
    """Return an error string if hint is malformed, else None."""
    if not isinstance(hint, dict):
        return "hint is not an object"
    system = hint.get("system")
    if not system:
        return "hint missing 'system'"
    target = hint.get("target")
    if not isinstance(target, dict):
        return "hint missing or invalid 'target'"
    missing = _REQUIRED_TARGET_KEYS - set(target)
    if missing:
        return f"target missing keys: {sorted(missing)}"
    if not target.get("board_id"):
        return "target.board_id is empty"
    return None


def resolve_routing_preview(routing_hints: dict, job_type: str) -> dict:
    """
    Return a routing preview dict for the given job_type.
    routing_hints is the tenant_memory["routing_hints"] dict.
    """
    hint = routing_hints.get(job_type)

    if hint is None:
        return {
            "job_type": job_type,
            "status":   "missing_hint",
            "system":   None,
            "target":   None,
            "message":  f"Ingen routing-hint sparad för {job_type}",
        }

    error = _validate_hint(hint)
    if error:
        return {
            "job_type": job_type,
            "status":   "invalid_hint",
            "system":   hint.get("system") if isinstance(hint, dict) else None,
            "target":   hint.get("target") if isinstance(hint, dict) else None,
            "message":  f"Routing-hint ofullständig: {error}",
        }

    target = hint["target"]
    board_name = target.get("board_name") or target.get("board_id")
    system = hint["system"]

    return {
        "job_type": job_type,
        "status":   "ready",
        "system":   system,
        "target":   target,
        "message":  f"{job_type.replace('_', ' ').capitalize()} skulle routas till {system} board {board_name}",
    }


def resolve_routing_readiness(routing_hints: dict) -> dict:
    """
    Return a readiness summary across all supported job types.
    routing_hints is the tenant_memory["routing_hints"] dict.
    """
    ready: list[str] = []
    missing: list[str] = []
    invalid: list[str] = []

    for job_type in SUPPORTED_JOB_TYPES:
        preview = resolve_routing_preview(routing_hints, job_type)
        status = preview["status"]
        if status == "ready":
            ready.append(job_type)
        elif status == "missing_hint":
            missing.append(job_type)
        else:
            invalid.append(job_type)

    total = len(SUPPORTED_JOB_TYPES)
    ready_count = len(ready)
    percent = round(ready_count / total * 100) if total else 0

    return {
        "ready":   ready,
        "missing": missing,
        "invalid": invalid,
        "score": {
            "ready_count": ready_count,
            "total":       total,
            "percent":     percent,
        },
    }
