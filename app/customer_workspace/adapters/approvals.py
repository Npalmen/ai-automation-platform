"""Workspace approvals adapter."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.customer_workspace.read_sources import derive_case_fields, get_job_record
from app.customer_workspace.schemas import ApprovalListItem, ApprovalListResponse
from app.customer_workspace.status import (
    customer_status_label,
    map_internal_status,
    map_job_type_to_work_item_type,
)
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.approval_repository import ApprovalRequestRepository


def list_workspace_approvals(
    db: Session,
    tenant_id: str,
    *,
    limit: int,
    offset: int,
    status: str = "pending",
) -> ApprovalListResponse:
    if status == "pending":
        records = ApprovalRequestRepository.list_pending_for_tenant(db, tenant_id, limit=limit, offset=offset)
        total = ApprovalRequestRepository.count_pending_for_tenant(db, tenant_id)
    else:
        records = (
            db.query(ApprovalRequestRecord)
            .filter(ApprovalRequestRecord.tenant_id == tenant_id)
            .order_by(ApprovalRequestRecord.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        total = (
            db.query(ApprovalRequestRecord)
            .filter(ApprovalRequestRecord.tenant_id == tenant_id)
            .count()
        )

    items: list[ApprovalListItem] = []
    for record in records:
        job = get_job_record(db, tenant_id, record.job_id)
        derived = derive_case_fields(job) if job else {}
        title = record.title or derived.get("subject") or "Godkännande"
        work_item_type = map_job_type_to_work_item_type(record.job_type or (job.job_type if job else None))
        if work_item_type != "lead":
            work_item_type = "support"
        pending = record.state == "pending"
        customer_status = map_internal_status(
            job.status if job else None,
            has_pending_approval=pending,
            recommended_status=derived.get("recommended_status") if job else None,
        )
        items.append(
            ApprovalListItem(
                approval_id=record.approval_id,
                work_item_id=record.job_id,
                work_item_type=work_item_type,  # type: ignore[arg-type]
                work_item_title=derived.get("subject") or title,
                title=title,
                summary=record.summary,
                customer_status=customer_status,
                customer_status_label=customer_status_label(customer_status),
                requested_at=record.requested_at.isoformat() if record.requested_at else None,
            )
        )

    return ApprovalListResponse(items=items, total=total, limit=limit, offset=offset)
