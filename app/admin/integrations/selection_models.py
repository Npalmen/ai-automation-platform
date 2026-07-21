"""Canonical integration selection models (Slice B)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.integrations.keys import (
    CANONICAL_INTEGRATION_KEYS,
    normalize_integration_key,
    registry_key_to_canonical,
)

SelectionStatus = Literal[
    "not_selected",
    "selected_optional",
    "selected_required",
]

RequirementSource = Literal[
    "manual",
    "module_recommendation",
    "module_requirement",
    "legacy_backfill",
]

ConfiguredBy = str  # operator:<id> | system:migration_016


class IntegrationSelectionRecord(BaseModel):
    integration_key: str
    selection_status: SelectionStatus
    migration_review_required: bool = False
    requirement_source: RequirementSource = "manual"
    configured_at: str
    configured_by: str

    @field_validator("integration_key")
    @classmethod
    def canonical_key(cls, value: str) -> str:
        canonical = normalize_integration_key(value)
        if canonical is None:
            raise ValueError(f"Unknown integration key: {value}")
        return canonical

    @field_validator("configured_by")
    @classmethod
    def configured_by_format(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("configured_by is required")
        if text.startswith("operator:") or text.startswith("system:"):
            return text
        raise ValueError("configured_by must start with operator: or system:")

    def to_settings_dict(self) -> dict[str, Any]:
        return {
            "integration_key": self.integration_key,
            "selection_status": self.selection_status,
            "migration_review_required": self.migration_review_required,
            "requirement_source": self.requirement_source,
            "configured_at": self.configured_at,
            "configured_by": self.configured_by,
        }


def parse_selections_map(raw: dict[str, Any] | None) -> dict[str, IntegrationSelectionRecord]:
    if not raw:
        return {}
    out: dict[str, IntegrationSelectionRecord] = {}
    for key, payload in raw.items():
        if not isinstance(payload, dict):
            continue
        canonical = normalize_integration_key(key) or normalize_integration_key(
            str(payload.get("integration_key") or "")
        )
        if canonical is None:
            continue
        merged = {**payload, "integration_key": canonical}
        out[canonical] = IntegrationSelectionRecord.model_validate(merged)
    return out


def selections_from_registry_draft(
    draft_selections: dict[str, Any],
    *,
    configured_by: str,
    configured_at: str | None = None,
) -> dict[str, IntegrationSelectionRecord]:
    """Build canonical selection map from onboarding draft selections."""
    ts = configured_at or datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
    out: dict[str, IntegrationSelectionRecord] = {}
    for raw_key, payload in (draft_selections or {}).items():
        if not isinstance(payload, dict):
            continue
        canonical = registry_key_to_canonical(raw_key) or normalize_integration_key(raw_key)
        if canonical is None:
            continue
        status = str(payload.get("selection_status") or "not_selected")
        if status not in ("not_selected", "selected_optional", "selected_required"):
            continue
        out[canonical] = IntegrationSelectionRecord(
            integration_key=canonical,
            selection_status=status,  # type: ignore[arg-type]
            migration_review_required=bool(payload.get("migration_review_required", False)),
            requirement_source=str(payload.get("requirement_source") or "manual"),  # type: ignore[arg-type]
            configured_at=str(payload.get("configured_at") or ts),
            configured_by=str(payload.get("configured_by") or configured_by),
        )
    return out


def ensure_selections_envelope(settings: dict[str, Any]) -> dict[str, Any]:
    """Ensure settings.integrations.selections exists without mutating selections."""
    merged = dict(settings or {})
    integrations = dict(merged.get("integrations") or {})
    selections = integrations.get("selections")
    if selections is None:
        integrations["selections"] = {}
    if integrations.get("enabled_external_writes") is None:
        integrations["enabled_external_writes"] = []
    merged["integrations"] = integrations
    return merged


def validate_no_duplicate_aliases(selections: dict[str, IntegrationSelectionRecord]) -> None:
    keys = list(selections.keys())
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate canonical integration keys in selections")
