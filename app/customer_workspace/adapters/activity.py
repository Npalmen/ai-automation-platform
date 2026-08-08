"""Workspace activity adapter."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.customer_workspace.read_sources import list_activity_records
from app.customer_workspace.schemas import ActivityListItem, ActivityListResponse
from app.customer_workspace.status import customer_status_label, map_internal_status


def _activity_label(item: dict) -> str:
    status = item.get("status")
    action = item.get("latest_action")
    if status == "awaiting_approval":
        return "Väntar på godkännande"
    if status == "failed":
        return "Behöver åtgärd"
    if action == "send_email":
        return "Kundmeddelande skickat"
    if action == "create_monday_item":
        return "Skapat i Monday"
    if status == "completed":
        return "Ärende klart"
    if status == "processing":
        return "Bearbetas"
    return "Aktivitet registrerad"


def _normalize_activity_type(raw_type: str | None) -> str:
    key = (raw_type or "").strip().lower()
    if key == "lead":
        return "lead"
    if key == "invoice":
        return "invoice"
    return "support"


def _matches_activity_filter(normalized_type: str, filter_type: str) -> bool:
    if filter_type == "all":
        return True
    return normalized_type == filter_type


def list_workspace_activity(
    db: Session,
    tenant_id: str,
    *,
    activity_type: str,
    limit: int,
    offset: int,
) -> ActivityListResponse:
    raw_items, total = list_activity_records(db, tenant_id, limit=limit, offset=offset)
    items: list[ActivityListItem] = []
    for item in raw_items:
        normalized_type = _normalize_activity_type(item.get("type"))
        if not _matches_activity_filter(normalized_type, activity_type):
            continue
        customer_status = map_internal_status(
            item.get("status"),
            has_pending_approval=bool(item.get("has_pending_approval")),
            recommended_status=item.get("recommended_status"),
        )
        items.append(
            ActivityListItem(
                at=item.get("created_at"),
                type=normalized_type,
                customer_status=customer_status,
                customer_status_label=customer_status_label(customer_status),
                priority=item.get("priority"),
                label=_activity_label(item),
            )
        )
    return ActivityListResponse(items=items, total=total, limit=limit, offset=offset)
