"""Workspace overview adapter."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.customer_workspace.adapters.work_items import project_work_item
from app.customer_workspace.read_sources import (
    compute_roi_metrics,
    compute_summary_metrics,
    list_job_records,
    needs_help_job_ids,
)
from app.customer_workspace.schemas import OverviewResponse, OverviewSummary, PartialError, PriorityWorkItem
from app.customer_workspace.status import customer_status_label, map_internal_status, priority_rank


def get_workspace_overview(db: Session, tenant_id: str) -> OverviewResponse:
    partial_errors: list[PartialError] = []
    summary_metrics = compute_summary_metrics(db, tenant_id)
    roi = compute_roi_metrics(db, tenant_id)

    needs_help_count = 0
    needs_help_ids: set[str] = set()
    try:
        needs_help_ids = needs_help_job_ids(db, tenant_id)
        needs_help_count = len(needs_help_ids)
    except Exception:
        partial_errors.append(
            PartialError(
                section="needs_help",
                code="read_failed",
                message="Behöver-hjälp-data kunde inte hämtas.",
            )
        )

    cases_handled_today = (
        summary_metrics["leads_today"]
        + summary_metrics["inquiries_today"]
        + summary_metrics["invoices_today"]
    )

    summary = OverviewSummary(
        cases_handled_today=cases_handled_today,
        waiting_for_decision=summary_metrics["ready_cases"],
        waiting_for_customer=summary_metrics["waiting_customer"],
        needs_help=needs_help_count,
        failed_today=summary_metrics["failed_today"],
        estimated_hours_saved=float(roi.get("estimated_hours_saved", 0)),
        estimated_value_sek=float(roi.get("estimated_value_sek", 0)),
    )

    records, _ = list_job_records(
        db,
        tenant_id,
        sort_by="priority_rank",
        sort_dir="asc",
        limit=200,
        offset=0,
    )

    priority_items: list[PriorityWorkItem] = []
    for record in records:
        projected = project_work_item(db, tenant_id, record, needs_help_ids=needs_help_ids)
        priority_items.append(
            PriorityWorkItem(
                work_item_id=projected.work_item_id,
                type=projected.type,
                title=projected.title,
                customer_name=projected.customer_name,
                customer_status=projected.customer_status,
                customer_status_label=projected.customer_status_label,
                priority_rank=projected.priority_rank,
                priority_label=projected.priority_label,
                updated_at=projected.updated_at,
            )
        )

    priority_items.sort(
        key=lambda item: (
            item.priority_rank,
            str(item.updated_at or ""),
        )
    )
    priority_items = priority_items[:20]

    return OverviewResponse(
        last_updated_at=datetime.now(timezone.utc).isoformat(),
        summary=summary,
        priority_work_items=priority_items,
        partial_errors=partial_errors,
    )
