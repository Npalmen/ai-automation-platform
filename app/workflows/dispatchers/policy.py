"""
Dispatch policy resolver.

Reads the tenant's existing auto_actions config (stored in tenant_configs.auto_actions)
and returns a normalized dispatch mode for a given job type.

The auto_actions dict stores values set via the Setup / Control Panel UI:
  'manual' | False | None → "manual"
  'semi'                  → "approval_required"
  'auto'  | True          → "full_auto"

This is the single source of truth — no parallel config is created.

Output
------
{
  "policy_mode":        "manual" | "approval_required" | "full_auto",
  "requires_approval":  bool,
  "can_dispatch_now":   bool   # True when manual or full_auto; False when approval_required
}
"""

from __future__ import annotations

from typing import Any

# Normalized modes
MANUAL            = "manual"
APPROVAL_REQUIRED = "approval_required"
FULL_AUTO         = "full_auto"

_VALID_MODES = {MANUAL, APPROVAL_REQUIRED, FULL_AUTO}


def _normalize(raw) -> str:
    """Map a raw auto_actions value to a normalized dispatch mode."""
    if raw is True or raw == "auto":
        return FULL_AUTO
    if raw == "semi":
        return APPROVAL_REQUIRED
    # False, None, "manual", missing, or anything else → safest default
    return MANUAL


def resolve_dispatch_policy(tenant_config: dict, job_type: str) -> dict:
    """
    Return dispatch policy for (tenant_config, job_type).

    tenant_config is the dict returned by TenantConfigRepository.get_config()
    or any dict with an 'auto_actions' key.

    Pure function — no DB or network calls.
    """
    auto_actions: dict = tenant_config.get("auto_actions") or {}
    raw = auto_actions.get(job_type)
    mode = _normalize(raw)

    requires_approval = mode == APPROVAL_REQUIRED
    can_dispatch_now  = mode != APPROVAL_REQUIRED

    return {
        "policy_mode":       mode,
        "requires_approval": requires_approval,
        "can_dispatch_now":  can_dispatch_now,
    }
