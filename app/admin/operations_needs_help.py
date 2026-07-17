"""
Needs-help queue service for the operator panel.

Read-only. No writes, no external API calls, no secrets in response.

Detail lookup: when tenant_id is provided, scopes to a single tenant via
_build_tenant_triage. Without tenant_id, falls back to a full global scan —
an explicit scaling limitation documented here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.admin.operations_triage import (
    _build_tenant_triage,
    _map_priority_item,
    _resolve_runbook,
    _sort_priority_rows,
    collect_all_triage_rows,
)
from app.admin.operator_actions import (
    load_approval_resource_state,
    needs_help_candidate_actions,
    resolve_available_actions,
)
from app.admin.incidents import (
    build_recommended_incident_action,
    find_linked_incidents,
)
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

_PANEL_SEVERITY = {
    "critical": "critical",
    "high": "failed",
    "medium": "warning",
    "info": "information",
}


def _panel_severity(internal: str) -> str:
    return _PANEL_SEVERITY.get(internal, "information")


def _map_needs_help_item(row: dict[str, Any]) -> dict[str, Any]:
    base = _map_priority_item(row)
    internal_severity = row.get("severity") or "info"
    return {
        **base,
        "severity": _panel_severity(internal_severity),
        "safe_retry_available": row.get("retryable") or "unknown",
        "external_action_may_have_occurred": row.get("external_impact") or "unknown",
        "source_type": row.get("source_type") or "",
        "related_alert_id": row.get("related_alert_id"),
        "alert_severity": row.get("alert_severity"),
        "alert_status": row.get("alert_status"),
        "alert_occurrence_count": row.get("alert_occurrence_count"),
        "_runbook_ref": row.get("runbook_ref") or "",
        "_approval_id": row.get("approval_id") or "",
        "_tenant_id": row.get("tenant_id") or "",
    }


def _attach_available_actions(
    db: Session,
    item: dict[str, Any],
    operator_role: str,
) -> list[dict[str, Any]]:
    candidates = needs_help_candidate_actions(item)
    if not candidates:
        return []
    resource_state: dict[str, Any] = {}
    approval_id = item.get("_approval_id")
    tenant_id = item.get("_tenant_id") or item.get("tenant_id")
    if approval_id and tenant_id:
        resource_state = load_approval_resource_state(db, tenant_id, approval_id)
    actions = resolve_available_actions(candidates, operator_role, resource_state)
    return [action.model_dump() for action in actions]


def _matches_search(item: dict[str, Any], needle: str) -> bool:
    fields = (
        item.get("customer_name", ""),
        item.get("tenant_id", ""),
        item.get("title", ""),
        item.get("category", ""),
        item.get("id", ""),
    )
    return any(needle in str(value).lower() for value in fields)


def _apply_filters(
    items: list[dict[str, Any]],
    *,
    search: str | None,
    severity: str | None,
    category: str | None,
    tenant_id: str | None,
    source_type: str | None,
    safe_retry: str | None,
    external_impact: str | None,
    minimum_age_hours: int | None,
) -> list[dict[str, Any]]:
    result = items
    if search:
        needle = search.strip().lower()
        if needle:
            result = [i for i in result if _matches_search(i, needle)]
    if severity:
        result = [i for i in result if i.get("severity") == severity]
    if category:
        result = [i for i in result if i.get("category") == category]
    if tenant_id:
        result = [i for i in result if i.get("tenant_id") == tenant_id]
    if source_type:
        result = [i for i in result if i.get("source_type") == source_type]
    if safe_retry:
        result = [i for i in result if i.get("safe_retry_available") == safe_retry]
    if external_impact:
        result = [
            i for i in result
            if i.get("external_action_may_have_occurred") == external_impact
        ]
    if minimum_age_hours is not None:
        result = [
            i for i in result
            if (i.get("age_hours") or 0) >= minimum_age_hours
        ]
    return result


def _build_summary(items: list[dict[str, Any]]) -> dict[str, int]:
    tenants = {i.get("tenant_id") for i in items if i.get("tenant_id")}
    return {
        "critical": sum(1 for i in items if i.get("severity") == "critical"),
        "failed": sum(1 for i in items if i.get("severity") == "failed"),
        "warning": sum(1 for i in items if i.get("severity") == "warning"),
        "information": sum(1 for i in items if i.get("severity") == "information"),
        "affected_tenants": len(tenants),
        "safe_retry_yes": sum(
            1 for i in items if i.get("safe_retry_available") == "yes"
        ),
        "external_action_yes_or_unknown": sum(
            1 for i in items
            if i.get("external_action_may_have_occurred") in ("yes", "unknown")
        ),
    }


def _sort_items(
    items: list[dict[str, Any]],
    *,
    sort: str,
    order: str,
) -> list[dict[str, Any]]:
    reverse = order.lower() == "desc"
    if sort == "age":
        return sorted(
            items,
            key=lambda i: i.get("age_hours") if i.get("age_hours") is not None else -1,
            reverse=reverse,
        )
    if sort == "tenant":
        return sorted(
            items,
            key=lambda i: (i.get("customer_name") or "").lower(),
            reverse=reverse,
        )
    if sort == "severity":
        severity_order = {"critical": 0, "failed": 1, "warning": 2, "information": 3}
        return sorted(
            items,
            key=lambda i: severity_order.get(i.get("severity", ""), 99),
            reverse=reverse,
        )
    return items


def _collect_mapped_items(
    db: Session,
    *,
    app_settings: Any,
    tenant_id: str | None = None,
) -> list[dict[str, Any]]:
    if tenant_id:
        record = TenantConfigRepository.get(db, tenant_id)
        if record is None:
            return []
        rows = _build_tenant_triage(
            db,
            tenant_id=tenant_id,
            tenant_name=record.name or tenant_id,
            app_settings=app_settings,
            record=record,
        )
        from app.admin.operations_triage import dedupe_and_normalize_signals
        rows = dedupe_and_normalize_signals(rows)
    else:
        rows = collect_all_triage_rows(db, app_settings=app_settings)

    sorted_rows = _sort_priority_rows(rows)
    return [_map_needs_help_item(r) for r in sorted_rows]


def list_needs_help_queue(
    db: Session,
    *,
    app_settings: Any,
    operator_role: str = "read_only",
    search: str | None = None,
    severity: str | None = None,
    category: str | None = None,
    tenant_id: str | None = None,
    source_type: str | None = None,
    safe_retry: str | None = None,
    external_impact: str | None = None,
    minimum_age_hours: int | None = None,
    sort: str = "priority",
    order: str = "asc",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    mapped = _collect_mapped_items(db, app_settings=app_settings)
    filtered = _apply_filters(
        mapped,
        search=search,
        severity=severity,
        category=category,
        tenant_id=tenant_id,
        source_type=source_type,
        safe_retry=safe_retry,
        external_impact=external_impact,
        minimum_age_hours=minimum_age_hours,
    )
    summary = _build_summary(filtered)
    sorted_filtered = _sort_items(filtered, sort=sort, order=order)
    total = len(sorted_filtered)
    page = sorted_filtered[offset : offset + limit]
    clean_page = []
    for item in page:
        actions = _attach_available_actions(db, item, operator_role)
        clean = {k: v for k, v in item.items() if not k.startswith("_")}
        clean["available_actions"] = actions
        clean_page.append(clean)

    return {
        "generated_at": datetime.now(timezone.utc),
        "total": total,
        "summary": summary,
        "items": clean_page,
        "limit": limit,
        "offset": offset,
    }


def get_needs_help_item(
    db: Session,
    item_id: str,
    *,
    app_settings: Any,
    operator_role: str = "read_only",
    tenant_id: str | None = None,
) -> dict[str, Any] | None:
    if tenant_id:
        items = _collect_mapped_items(
            db, app_settings=app_settings, tenant_id=tenant_id
        )
    else:
        items = _collect_mapped_items(db, app_settings=app_settings)

    for item in items:
        if item.get("id") == item_id:
            runbook_ref = item.get("_runbook_ref", "")
            runbook = _resolve_runbook(runbook_ref)
            actions = _attach_available_actions(db, item, operator_role)
            clean = {k: v for k, v in item.items() if not k.startswith("_")}
            recommended = build_recommended_incident_action(clean)
            linked = find_linked_incidents(db, item_id)
            return {
                **clean,
                "runbook": runbook,
                "available_actions": actions,
                "recommended_incident_action": (
                    recommended.model_dump() if recommended else None
                ),
                "linked_incidents": linked.model_dump(),
            }
    return None
