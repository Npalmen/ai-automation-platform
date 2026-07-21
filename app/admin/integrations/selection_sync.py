"""Sync runtime integration gates from explicit selections (fail-closed)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.admin.integrations.selection_models import (
    IntegrationSelectionRecord,
    parse_selections_map,
)
from app.admin.integrations.selection_resolver import (
    _has_tenant_credential,
    _has_verified_config,
)
from app.integrations.keys import (
    INTEGRATION_REGISTRY,
    normalize_integration_key_list,
)

MIGRATION_BACKFILL_ACTOR = "system:migration_016"


@dataclass(frozen=True)
class RuntimeIntegrationGates:
    allowed_integrations: list[str]
    enabled_external_writes: list[str]
    changes: dict[str, Any]


def _selections_from_settings(settings: dict[str, Any]) -> dict[str, IntegrationSelectionRecord]:
    block = (settings.get("integrations") or {}).get("selections") or {}
    return parse_selections_map(block if isinstance(block, dict) else {})


def _support_allows_runtime(key: str) -> bool:
    meta = INTEGRATION_REGISTRY.get(key) or {}
    return meta.get("support_status") not in ("coming_later", "legacy_only")


def _is_verified_connected(
    db: Session,
    tenant_id: str,
    settings: dict[str, Any],
    key: str,
) -> bool:
    return _has_verified_config(settings, key) and _has_tenant_credential(db, tenant_id, key)


def compute_runtime_gates_from_selections(
    db: Session,
    *,
    tenant_id: str,
    settings: dict[str, Any],
    selections: dict[str, IntegrationSelectionRecord] | None = None,
) -> RuntimeIntegrationGates:
    """Derive allowed_integrations and enabled_external_writes from selections."""
    selections = selections or _selections_from_settings(settings)
    allowed: list[str] = []
    writes: list[str] = []

    for key, record in sorted(selections.items()):
        if record.selection_status == "not_selected":
            continue
        if record.migration_review_required:
            continue
        if not _support_allows_runtime(key):
            continue

        if record.selection_status == "selected_required":
            allowed.append(key)
            if _is_verified_connected(db, tenant_id, settings, key):
                writes.append(key)
        elif record.selection_status == "selected_optional":
            if _is_verified_connected(db, tenant_id, settings, key):
                allowed.append(key)
                writes.append(key)

    return RuntimeIntegrationGates(
        allowed_integrations=sorted(set(allowed)),
        enabled_external_writes=sorted(set(writes)),
        changes={},
    )


def sync_allowed_integrations_from_selections(
    db: Session,
    record: Any,
    *,
    dry_run: bool = False,
    fail_closed: bool = True,
    allow_expand_on_activation: bool = False,
) -> RuntimeIntegrationGates:
    """
    Apply runtime gates on tenant record from explicit selections.

    fail_closed: never enable external writes that were not previously enabled,
    unless allow_expand_on_activation=True (onboarding activation path).
    """
    settings = getattr(record, "settings", None) or {}
    tenant_id = getattr(record, "tenant_id", "")
    previous_allowed = set(normalize_integration_key_list(getattr(record, "allowed_integrations", None)))
    integrations = settings.get("integrations") or {}
    previous_writes = set(
        normalize_integration_key_list(integrations.get("enabled_external_writes"))
    )

    computed = compute_runtime_gates_from_selections(db, tenant_id=tenant_id, settings=settings)
    new_allowed = set(computed.allowed_integrations)
    new_writes = set(computed.enabled_external_writes)

    if fail_closed and not allow_expand_on_activation:
        safe_allowed = set(previous_allowed)
        for key in new_allowed:
            if key in previous_allowed:
                safe_allowed.add(key)
        new_allowed = safe_allowed
        new_writes = previous_writes & new_writes

    if fail_closed and allow_expand_on_activation:
        expanded_writes: set[str] = set(previous_writes)
        for key in new_writes:
            if key in previous_writes or key in new_allowed:
                expanded_writes.add(key)
        new_writes = expanded_writes & new_allowed

    final_allowed = sorted(new_allowed)
    final_writes = sorted(new_writes)

    changes = {
        "allowed_before": sorted(previous_allowed),
        "allowed_after": final_allowed,
        "writes_before": sorted(previous_writes),
        "writes_after": final_writes,
    }

    if not dry_run:
        record.allowed_integrations = final_allowed
        merged_settings = dict(settings)
        integrations_block = dict(merged_settings.get("integrations") or {})
        integrations_block["enabled_external_writes"] = final_writes
        merged_settings["integrations"] = integrations_block
        record.settings = merged_settings

    return RuntimeIntegrationGates(
        allowed_integrations=final_allowed,
        enabled_external_writes=final_writes,
        changes=changes,
    )


def is_external_write_enabled_for_tenant(
    tenant_id: str,
    integration_key: str,
    *,
    settings: dict[str, Any],
) -> bool:
    canonical = integration_key
    writes = normalize_integration_key_list(
        (settings.get("integrations") or {}).get("enabled_external_writes")
    )
    return canonical in writes
