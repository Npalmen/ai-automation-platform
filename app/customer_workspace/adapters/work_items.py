"""Workspace work item adapters."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.customer_workspace.read_sources import (
    build_customer_timeline,
    derive_case_fields,
    get_job_record,
    has_pending_approval,
    list_job_records,
    needs_help_job_ids,
)
from app.customer_workspace.schemas import (
    PartialError,
    TimelineEvent,
    WorkItemDetailResponse,
    WorkItemListItem,
    WorkItemListResponse,
    WorkItemsQuery,
    WorkItemTypeValue,
)
from app.customer_workspace.status import (
    customer_status_label,
    map_internal_status,
    map_job_type_to_work_item_type,
    map_work_item_type_to_job_types,
    priority_label,
    priority_rank,
)
from app.repositories.postgres.job_models import JobRecord


def _work_item_type_for_record(
    record: JobRecord,
    *,
    needs_help_ids: set[str],
) -> WorkItemTypeValue:
    if record.job_id in needs_help_ids:
        return "needs_help"
    mapped = map_job_type_to_work_item_type(record.job_type)
    return "lead" if mapped == "lead" else "support"


def project_work_item(
    db: Session,
    tenant_id: str,
    record: JobRecord,
    *,
    needs_help_ids: set[str] | None = None,
) -> WorkItemListItem:
    help_ids = needs_help_ids or set()
    derived = derive_case_fields(record)
    pending = has_pending_approval(db, tenant_id, record.job_id)
    customer_status = map_internal_status(
        record.status,
        has_pending_approval=pending,
        recommended_status=derived.get("recommended_status"),
    )
    if record.job_id in help_ids:
        customer_status = "needs_help"
    item_type = _work_item_type_for_record(record, needs_help_ids=help_ids)
    priority = derived.get("priority")
    title = derived.get("subject") or "Ärende"
    return WorkItemListItem(
        work_item_id=record.job_id,
        type=item_type,
        title=title,
        customer_name=derived.get("customer_name"),
        customer_email=derived.get("customer_email"),
        customer_status=customer_status,
        customer_status_label=customer_status_label(customer_status),
        priority_rank=priority_rank(priority),
        priority_label=priority_label(priority),
        summary=title,
        created_at=derived.get("created_at"),
        updated_at=derived.get("processed_at"),
    )


def _derive_waiting_for(derived: dict, customer_status: str) -> str | None:
    recommended = (derived.get("recommended_status") or "").strip().lower()
    if customer_status == "waiting_for_customer" or recommended == "needs_customer_info":
        return "Svar från kund"
    if customer_status == "waiting_for_decision":
        return "Godkännande"
    if customer_status == "needs_help":
        return "Åtgärd från teamet"
    return None


def list_workspace_work_items(
    db: Session,
    tenant_id: str,
    query: WorkItemsQuery,
) -> WorkItemListResponse:
    partial_errors: list[PartialError] = []
    needs_help_ids: set[str] = set()
    try:
        needs_help_ids = needs_help_job_ids(db, tenant_id)
    except Exception:
        partial_errors.append(
            PartialError(
                section="needs_help",
                code="read_failed",
                message="Behöver-hjälp-data kunde inte hämtas.",
            )
        )

    job_types = None if query.type == "needs_help" else map_work_item_type_to_job_types(query.type)

    if query.type == "needs_help":
        records = [
            record
            for job_id in needs_help_ids
            if (record := get_job_record(db, tenant_id, job_id)) is not None
        ]
    else:
        records, _ = list_job_records(
            db,
            tenant_id,
            job_types=job_types,
            q=query.q,
            created_from=query.from_,
            created_to=query.to,
            sort_by=query.sort,
            sort_dir=query.resolved_order(),
            limit=10_000,
            offset=0,
        )

    projected: list[WorkItemListItem] = []
    for record in records:
        item = project_work_item(db, tenant_id, record, needs_help_ids=needs_help_ids)
        if query.type == "lead" and item.type != "lead":
            continue
        if query.type == "support" and item.type != "support":
            continue
        if query.type == "needs_help" and item.type != "needs_help":
            continue
        if query.status and item.customer_status != query.status:
            continue
        projected.append(item)

    reverse = query.resolved_order() == "desc"
    if query.sort == "created_at":
        projected.sort(key=lambda item: str(item.created_at or ""), reverse=reverse)
    elif query.sort == "updated_at":
        projected.sort(key=lambda item: str(item.updated_at or ""), reverse=reverse)
    else:
        projected.sort(
            key=lambda item: (item.priority_rank, str(item.updated_at or "")),
            reverse=reverse,
        )

    total = len(projected)
    page = projected[query.offset : query.offset + query.limit]
    return WorkItemListResponse(
        items=page,
        total=total,
        limit=query.limit,
        offset=query.offset,
        partial_errors=partial_errors,
    )


def get_workspace_work_item(
    db: Session,
    tenant_id: str,
    work_item_id: str,
) -> WorkItemDetailResponse:
    record = get_job_record(db, tenant_id, work_item_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Not found")

    needs_help_ids = needs_help_job_ids(db, tenant_id)
    item = project_work_item(db, tenant_id, record, needs_help_ids=needs_help_ids)
    derived = derive_case_fields(record)
    timeline_raw = build_customer_timeline(db, tenant_id, record)
    timeline = [TimelineEvent(**event) for event in timeline_raw]

    human_takeover = item.customer_status == "needs_help" or (record.status or "").lower() in {
        "manual_review",
        "needs_help",
    }

    return WorkItemDetailResponse(
        work_item_id=item.work_item_id,
        type=item.type,
        title=item.title,
        customer_name=item.customer_name,
        customer_email=item.customer_email,
        customer_status=item.customer_status,
        customer_status_label=item.customer_status_label,
        priority_rank=item.priority_rank,
        summary=item.summary,
        created_at=item.created_at,
        updated_at=item.updated_at,
        timeline=timeline,
        waiting_for=_derive_waiting_for(derived, item.customer_status),
        human_takeover_required=human_takeover,
    )
