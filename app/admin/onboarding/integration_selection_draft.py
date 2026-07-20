"""Draft-level integration selection helpers for onboarding Slice B."""

from __future__ import annotations

from app.admin.onboarding.integration_draft_schemas import (
    GmailIntegrationConfig,
    GoogleSheetsIntegrationConfig,
    IntegrationSelectionDraft,
    IntegrationsDraftPayload,
    MondayIntegrationConfig,
    VismaIntegrationConfig,
)
from app.integrations.keys import (
    ALTERNATIVES_GROUPS,
    INTEGRATION_REGISTRY,
    registry_key_to_canonical,
)

SelectionStatus = str


def registry_meta_for_key(registry_key: str) -> dict[str, str | bool | None]:
    canonical = registry_key_to_canonical(registry_key)
    meta = INTEGRATION_REGISTRY.get(canonical or "", {})
    alt_group = str(meta.get("alternatives_group") or "")
    group_label = ALTERNATIVES_GROUPS.get(alt_group, {}).get("label_sv")
    return {
        "canonical_integration_key": canonical,
        "category": str(meta.get("category") or ""),
        "alternatives_group": alt_group or None,
        "alternatives_group_label_sv": str(group_label) if group_label else None,
        "support_status": str(meta.get("support_status") or ""),
        "selectable": bool(meta.get("selectable", False)),
    }


def onboarding_display_registry_keys() -> list[str]:
    seen: set[str] = set()
    category_order = {
        "email": 0,
        "finance": 1,
        "work_management": 2,
        "spreadsheet_export": 3,
        "calendar": 4,
    }

    def sort_key(registry_key: str) -> tuple[int, str]:
        canonical = registry_key_to_canonical(registry_key) or registry_key
        category = str(INTEGRATION_REGISTRY.get(canonical, {}).get("category") or "")
        return (category_order.get(category, 99), registry_key)

    for canonical, meta in INTEGRATION_REGISTRY.items():
        registry_key = str(meta.get("registry_key", canonical))
        seen.add(registry_key)
    return sorted(seen, key=sort_key)


def effective_selection_status(
    draft: IntegrationsDraftPayload,
    registry_key: str,
    *,
    required_by_module: bool,
) -> tuple[SelectionStatus, bool]:
    canonical = registry_key_to_canonical(registry_key)
    if canonical and draft.selections:
        sel = draft.selections.get(canonical)
        if sel is not None:
            return sel.selection_status, sel.migration_review_required

    if required_by_module:
        return "selected_required", False

    requested = registry_key in (draft.requested_integrations or [])
    if registry_key == "gmail":
        requested = requested or draft.gmail.requested
    elif registry_key == "visma":
        requested = requested or draft.visma.requested
    elif registry_key == "google_sheets":
        requested = requested or draft.google_sheets.requested
    elif registry_key == "monday":
        requested = requested or draft.monday.requested

    if requested:
        if required_by_module or registry_key in (draft.requested_integrations or []):
            return "selected_required", False
        return "selected_optional", False
    return "not_selected", False


def _clear_legacy_flags(registry_key: str, draft: IntegrationsDraftPayload) -> IntegrationsDraftPayload:
    requested = [k for k in draft.requested_integrations if k != registry_key]
    updates: dict[str, object] = {"requested_integrations": requested}
    if registry_key == "gmail":
        updates["gmail"] = GmailIntegrationConfig(requested=False, label_scope_slug="")
    elif registry_key == "visma":
        updates["visma"] = VismaIntegrationConfig(requested=False)
    elif registry_key == "google_sheets":
        updates["google_sheets"] = GoogleSheetsIntegrationConfig(
            requested=False, spreadsheet_id="", export_tabs=[]
        )
    elif registry_key == "monday":
        updates["monday"] = MondayIntegrationConfig(requested=False)
    return draft.model_copy(update=updates)


def apply_selections_to_legacy_draft(draft: IntegrationsDraftPayload) -> IntegrationsDraftPayload:
    if not draft.selections:
        return draft

    requested: list[str] = []
    gmail = draft.gmail.model_copy()
    visma = draft.visma.model_copy()
    sheets = draft.google_sheets.model_copy()
    monday = draft.monday.model_copy()

    for canonical, sel in draft.selections.items():
        meta = INTEGRATION_REGISTRY.get(canonical, {})
        registry_key = str(meta.get("registry_key", canonical))
        if sel.selection_status == "not_selected":
            continue
        if registry_key not in requested:
            requested.append(registry_key)
        if canonical == "google_mail":
            gmail = gmail.model_copy(update={"requested": True})
        elif canonical == "visma":
            visma = visma.model_copy(update={"requested": True})
        elif canonical == "google_sheets":
            sheets = sheets.model_copy(update={"requested": True})
        elif canonical == "monday":
            monday = monday.model_copy(update={"requested": True})

    merged = draft.model_copy(
        update={
            "requested_integrations": requested,
            "gmail": gmail,
            "visma": visma,
            "google_sheets": sheets,
            "monday": monday,
        }
    )

    for canonical, sel in draft.selections.items():
        if sel.selection_status != "not_selected":
            continue
        meta = INTEGRATION_REGISTRY.get(canonical, {})
        registry_key = str(meta.get("registry_key", canonical))
        merged = _clear_legacy_flags(registry_key, merged)

    return merged


def merge_selection_patch(
    current: IntegrationsDraftPayload,
    patch: dict[str, IntegrationSelectionDraft],
) -> IntegrationsDraftPayload:
    selections = dict(current.selections)
    for raw_key, sel in patch.items():
        canonical = registry_key_to_canonical(raw_key)
        if canonical is None:
            continue
        selections[canonical] = sel
    merged = current.model_copy(update={"selections": selections})
    return apply_selections_to_legacy_draft(merged)
