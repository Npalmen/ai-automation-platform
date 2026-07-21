"""Secret-free audit helpers for customer settings changes."""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.repositories.postgres.audit_models import AuditEventRecord

_REDACT_FRAGMENTS = frozenset(
    {
        "token",
        "secret",
        "password",
        "credential",
        "api_key",
        "authorization",
        "refresh",
        "access_token",
        "refresh_token",
        "client_secret",
    }
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def redact_settings_value(key: str, value: Any) -> Any:
    key_lower = key.lower()
    if any(fragment in key_lower for fragment in _REDACT_FRAGMENTS):
        return "[REDACTED]"
    if isinstance(value, dict):
        return redact_settings_summary(value)
    if isinstance(value, list):
        return [redact_settings_value(key, item) for item in value]
    if isinstance(value, str):
        if value.startswith(("ya29.", "kw_", "1//")):
            return "[REDACTED]"
    return value


def redact_settings_summary(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}
    return {key: redact_settings_value(key, value) for key, value in payload.items()}


def filter_internal_audit_paths(paths: list[str]) -> list[str]:
    return [path for path in paths if not path.startswith("_readiness")]


def diff_field_paths(before: dict[str, Any], after: dict[str, Any], *, prefix: str = "") -> list[str]:
    paths: list[str] = []
    keys = sorted(set(before.keys()) | set(after.keys()))
    for key in keys:
        path = f"{prefix}.{key}" if prefix else key
        b_val = before.get(key)
        a_val = after.get(key)
        if isinstance(b_val, dict) and isinstance(a_val, dict):
            paths.extend(diff_field_paths(b_val, a_val, prefix=path))
        elif b_val != a_val:
            paths.append(path)
    return paths


def build_settings_audit_event(
    *,
    tenant_id: str,
    domain: str,
    operator_id: str,
    operator_role: str,
    previous_config_version: int,
    new_config_version: int,
    changed_paths: list[str],
    readiness_domains_invalidated: list[str],
    runtime_projections_changed: list[str],
    change_reason: str | None,
    previous_summary: dict[str, Any],
    new_summary: dict[str, Any],
) -> AuditEventRecord:
    return AuditEventRecord(
        event_id=str(uuid4()),
        tenant_id=tenant_id,
        category="tenant_settings",
        action=f"tenant.settings.{domain}_updated",
        status="succeeded",
        details={
            "operator_id": operator_id,
            "operator_role": operator_role,
            "domain": domain,
            "previous_config_version": previous_config_version,
            "new_config_version": new_config_version,
            "changed_paths": changed_paths,
            "readiness_domains_invalidated": readiness_domains_invalidated,
            "runtime_projections_changed": runtime_projections_changed,
            "change_reason": change_reason,
            "previous_summary": redact_settings_summary(previous_summary),
            "new_summary": redact_settings_summary(new_summary),
        },
        created_at=_utcnow(),
    )


def domain_snapshot(settings: dict[str, Any], domain: str) -> dict[str, Any]:
    settings = copy.deepcopy(settings or {})
    if domain == "identity":
        return {"company": settings.get("company") or {}}
    if domain == "modules":
        return {"capabilities": settings.get("capabilities") or {}}
    if domain == "services":
        return {"memory": settings.get("memory") or {}}
    if domain == "routing":
        return {"routing": settings.get("routing") or {}}
    if domain == "integrations":
        return {"integrations": settings.get("integrations") or {}}
    if domain == "automation":
        return {"automation": settings.get("automation") or {}}
    if domain == "intake":
        return {"intake": settings.get("intake") or {}}
    return {}
