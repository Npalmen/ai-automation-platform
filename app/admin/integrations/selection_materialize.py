"""Materialize explicit integration selections into tenant settings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.admin.integrations.selection_models import (
    IntegrationSelectionRecord,
    ensure_selections_envelope,
    selections_from_registry_draft,
)
from app.admin.onboarding.registries import INTEGRATIONS, PRODUCT_CAPABILITIES
from app.integrations.keys import (
    CANONICAL_INTEGRATION_KEYS,
    registry_key_to_canonical,
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _module_required_keys(capability_keys: list[str]) -> set[str]:
    required: set[str] = set()
    for cap_key in capability_keys:
        cap = PRODUCT_CAPABILITIES.get(cap_key)
        if not cap:
            continue
        for registry_key in cap.required_integrations:
            canonical = registry_key_to_canonical(registry_key)
            if canonical:
                required.add(canonical)
    return required


def materialize_selections_config(
    tenant_settings: dict[str, Any],
    *,
    modules_payload: dict[str, Any],
    integrations_payload: dict[str, Any] | None,
    operator_id: str,
) -> dict[str, Any]:
    """Write settings.integrations.selections from onboarding drafts."""
    settings = ensure_selections_envelope(dict(tenant_settings or {}))
    integrations_block = dict(settings.get("integrations") or {})
    existing = integrations_block.get("selections") or {}
    if existing:
        settings["integrations"] = integrations_block
        return settings

    capability_keys = list(modules_payload.get("capabilities") or [])
    module_required = _module_required_keys(capability_keys)
    draft = integrations_payload or {}
    draft_selections = draft.get("selections") if isinstance(draft.get("selections"), dict) else {}

    if draft_selections:
        selections = selections_from_registry_draft(
            draft_selections,
            configured_by=f"operator:{operator_id}",
        )
    else:
        requested = set(draft.get("requested_integrations") or [])
        configured_at = _utcnow_iso()
        configured_by = f"operator:{operator_id}"
        selections: dict[str, IntegrationSelectionRecord] = {}
        for registry_key in requested:
            canonical = registry_key_to_canonical(registry_key)
            if canonical is None:
                continue
            status = "selected_required" if canonical in module_required else "selected_optional"
            selections[canonical] = IntegrationSelectionRecord(
                integration_key=canonical,
                selection_status=status,  # type: ignore[arg-type]
                migration_review_required=False,
                requirement_source="module_requirement" if canonical in module_required else "manual",
                configured_at=configured_at,
                configured_by=configured_by,
            )
        for canonical in module_required:
            if canonical in selections:
                continue
            selections[canonical] = IntegrationSelectionRecord(
                integration_key=canonical,
                selection_status="selected_required",
                migration_review_required=False,
                requirement_source="module_requirement",
                configured_at=configured_at,
                configured_by=configured_by,
            )

    for key in CANONICAL_INTEGRATION_KEYS:
        if key not in selections:
            continue
        meta = INTEGRATIONS.get(selections[key].integration_key) or INTEGRATIONS.get(
            next((k for k, v in INTEGRATIONS.items() if v.allowed_integration_key == key), "")
        )
        if meta and not meta.supported_in_current_slice:
            selections[key] = selections[key].model_copy(
                update={"migration_review_required": True}
            )

    integrations_block["selections"] = {
        key: rec.to_settings_dict() for key, rec in sorted(selections.items())
    }
    if integrations_block.get("enabled_external_writes") is None:
        integrations_block["enabled_external_writes"] = []
    settings["integrations"] = integrations_block
    return settings
