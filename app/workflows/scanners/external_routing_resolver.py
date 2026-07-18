"""
Resolve effective external dispatch routing hints.

Canonical source: settings.integrations.external_routing_targets
Legacy fallback: memory.routing_hints (dict hints only — string internal routes ignored)

Runtime consumers must use resolve_effective_dispatch_hints() rather than reading
memory.routing_hints directly for external dispatch.
"""

from __future__ import annotations

from typing import Any

from app.workflows.scanners.routing_preview import (
    SUPPORTED_JOB_TYPES,
    resolve_routing_preview,
    resolve_routing_readiness,
)

CANONICAL_SOURCE = "canonical"
LEGACY_SOURCE = "legacy_routing_hints"
MISSING_SOURCE = "missing"

_MANUAL_REVIEW_HINT = {
    "system": "manual_review",
    "target": {
        "board_id": "manual",
        "board_name": "Manuell granskning",
        "group_id": None,
        "group_name": None,
    },
}


def _is_external_dict_hint(value: Any) -> bool:
    return isinstance(value, dict) and "system" in value and "target" in value


def canonical_target_to_hint(job_type: str, target: dict[str, Any]) -> dict[str, Any] | None:
    """Map canonical external_routing_targets entry to legacy dispatch hint shape."""
    if not isinstance(target, dict):
        return None
    target_type = str(target.get("target_type") or "").strip()
    if target_type == "monday_board" and job_type == "lead":
        board_id = str(target.get("board_id") or "").strip()
        board_name = str(target.get("board_name") or "").strip()
        if not board_id or not board_name:
            return None
        return {
            "system": "monday",
            "target": {
                "board_id": board_id,
                "board_name": board_name,
                "group_id": target.get("group_id"),
                "group_name": target.get("group_name"),
            },
        }
    return None


def resolve_effective_dispatch_hint(
    *,
    job_type: str,
    tenant_settings: dict[str, Any] | None,
    memory: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str]:
    """
    Return (hint, source) for one job_type.

    source: canonical | legacy_routing_hints | missing
  Invalid canonical entries do not fall back to legacy (fail-closed to manual_review).
    """
    settings = tenant_settings or {}
    mem = memory or {}
    integrations = settings.get("integrations") or {}
    canonical_targets = integrations.get("external_routing_targets") or {}

    if job_type in canonical_targets:
        canonical_entry = canonical_targets[job_type]
        hint = canonical_target_to_hint(job_type, canonical_entry)
        if hint is None:
            return dict(_MANUAL_REVIEW_HINT), CANONICAL_SOURCE
        return hint, CANONICAL_SOURCE

    legacy_hints = mem.get("routing_hints") or {}
    legacy = legacy_hints.get(job_type)
    if legacy is None:
        return None, MISSING_SOURCE
    if isinstance(legacy, dict) and not _is_external_dict_hint(legacy):
        return legacy, LEGACY_SOURCE
    if not _is_external_dict_hint(legacy):
        return None, MISSING_SOURCE
    return legacy, LEGACY_SOURCE


def resolve_effective_dispatch_hints(
    tenant_settings: dict[str, Any] | None,
    memory: dict[str, Any] | None,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """
    Build routing_hints dict for resolve_routing_preview / dispatch engine.

    Returns (hints, sources_per_job_type).
    """
    hints: dict[str, dict[str, Any]] = {}
    sources: dict[str, str] = {}
    for job_type in SUPPORTED_JOB_TYPES:
        hint, source = resolve_effective_dispatch_hint(
            job_type=job_type,
            tenant_settings=tenant_settings,
            memory=memory,
        )
        if hint is not None:
            hints[job_type] = hint
            sources[job_type] = source
    return hints, sources


def resolve_effective_routing_readiness(
    tenant_settings: dict[str, Any] | None,
    memory: dict[str, Any] | None,
) -> dict[str, Any]:
    hints, sources = resolve_effective_dispatch_hints(tenant_settings, memory)
    summary = resolve_routing_readiness(hints)
    summary["sources"] = sources
    return summary


def resolve_effective_routing_preview(
    *,
    job_type: str,
    tenant_settings: dict[str, Any] | None,
    memory: dict[str, Any] | None,
) -> dict[str, Any]:
    """Preview with canonical-first resolution and source metadata."""
    hint, source = resolve_effective_dispatch_hint(
        job_type=job_type,
        tenant_settings=tenant_settings,
        memory=memory,
    )
    if hint is None:
        preview = resolve_routing_preview({}, job_type)
    else:
        preview = resolve_routing_preview({job_type: hint}, job_type)
    preview["routing_source"] = source
    if hint and hint.get("system") == "manual_review":
        preview["status"] = "invalid_hint"
        preview["message"] = (
            "Ogiltig eller okänd canonical routing — manuell granskning krävs."
        )
    return preview
