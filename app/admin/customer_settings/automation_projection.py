"""Deterministic automation runtime projection for active customer settings."""

from __future__ import annotations

from typing import Any

from app.admin.onboarding.registries import (
    resolve_modules_to_tenant_config,
    resolve_preset,
    preset_snapshot,
)

AUTOMATION_CANONICAL_KEYS = frozenset(
    {
        "preset_key",
        "preset_version",
        "approval_first",
        "demo_mode",
    }
)

FORBIDDEN_AUTOMATION_RUNTIME_KEYS = frozenset(
    {
        "effective_policy_snapshot",
        "auto_actions",
        "scheduler",
        "enabled_external_writes",
    }
)


class AutomationProjectionError(ValueError):
    """Raised when automation projection cannot be computed safely."""


def _fail_closed_auto_actions(capability_keys: list[str] | None) -> dict[str, str]:
    if not capability_keys:
        return {}
    job_types, _ = resolve_modules_to_tenant_config(capability_keys, [])
    return {job_type: "manual" for job_type in job_types}


def _enforce_approval_first(auto_actions: dict[str, str]) -> dict[str, str]:
    return {
        key: ("semi" if value == "auto" else value)
        for key, value in auto_actions.items()
    }


def compute_automation_runtime_projection(
    settings: dict[str, Any],
    *,
    capability_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Derive runtime automation projections from canonical settings.automation only."""
    automation = dict(settings.get("automation") or {})
    caps = list(capability_keys or [])

    preset_key = automation.get("preset_key")
    preset_version = int(automation.get("preset_version") or 1)
    if not preset_key and automation.get("approval_first"):
        preset_key = "approval_first"

    if not preset_key:
        return {
            "auto_actions": _fail_closed_auto_actions(caps),
            "automation_flags": {},
        }

    preset = resolve_preset(str(preset_key), preset_version)
    if preset is None:
        raise AutomationProjectionError(
            f"Unknown automation preset: {preset_key} v{preset_version}"
        )

    snapshot = preset_snapshot(preset)
    auto_actions = dict(snapshot.get("auto_actions") or {})
    if automation.get("approval_first"):
        auto_actions = _enforce_approval_first(auto_actions)

    if caps:
        job_types, _ = resolve_modules_to_tenant_config(caps, [])
        allowed = set(job_types)
        auto_actions = {key: value for key, value in auto_actions.items() if key in allowed}

    return {
        "auto_actions": auto_actions,
        "automation_flags": dict(snapshot.get("automation_flags") or {}),
    }
