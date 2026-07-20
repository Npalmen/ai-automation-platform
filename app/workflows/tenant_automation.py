"""Central normalization for tenant automation / auto_actions values."""

from __future__ import annotations

from typing import Any

# Normalized automation modes (authoritative)
MANUAL = "manual"
APPROVAL_REQUIRED = "approval_required"
FULL_AUTO = "full_auto"

_VALID_MODES = {MANUAL, APPROVAL_REQUIRED, FULL_AUTO}


def normalize_automation_mode(raw: Any) -> str:
    """Map a raw auto_actions[job_type] value to a normalized mode."""
    if raw is True or raw == "auto" or raw == "full_auto":
        return FULL_AUTO
    if raw == "semi":
        return APPROVAL_REQUIRED
    return MANUAL


def resolve_automation_mode(auto_actions: dict[str, Any] | None, job_type: str) -> str:
    auto_actions = auto_actions or {}
    return normalize_automation_mode(auto_actions.get(job_type))


def allows_direct_external_execution(mode: str) -> bool:
    return mode == FULL_AUTO


def requires_action_approval(mode: str) -> bool:
    return mode != FULL_AUTO


def read_tenant_auto_actions(job, db) -> dict[str, Any]:
    """Load tenant auto_actions when DB is available; otherwise empty (fail-closed)."""
    if db is None:
        return {}
    try:
        from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

        record = TenantConfigRepository.get(db, job.tenant_id)
        return dict(record.auto_actions or {}) if record else {}
    except Exception:
        return {}

