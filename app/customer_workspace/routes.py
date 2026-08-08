"""Customer workspace read-only API routes."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.customer_workspace.adapters.account import get_workspace_context
from app.customer_workspace.adapters.activity import list_workspace_activity
from app.customer_workspace.adapters.approvals import list_workspace_approvals
from app.customer_workspace.adapters.health import get_workspace_health
from app.customer_workspace.adapters.overview import get_workspace_overview
from app.customer_workspace.adapters.work_items import get_workspace_work_item, list_workspace_work_items
from app.customer_workspace.dependencies import get_customer_session_tenant
from app.customer_workspace.schemas import (
    ActivityListResponse,
    ActivityQuery,
    ApprovalListResponse,
    ApprovalsQuery,
    CustomerStatusValue,
    HealthResponse,
    OverviewResponse,
    WorkItemDetailResponse,
    WorkItemListResponse,
    WorkItemsQuery,
    WorkspaceContextResponse,
)

router = APIRouter()


def _work_items_query(
    type: Literal["lead", "support", "needs_help", "all"] = "all",
    status: CustomerStatusValue | None = None,
    q: str | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    sort: Literal["updated_at", "priority_rank", "created_at"] = "priority_rank",
    order: Literal["asc", "desc"] | None = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> WorkItemsQuery:
    if from_ and to and from_ > to:
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("query", "from"),
                    "msg": "from must be before to",
                    "input": from_.isoformat(),
                }
            ]
        )
    return WorkItemsQuery(
        type=type,
        status=status,
        q=q,
        from_=from_,
        to=to,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )


def _approvals_query(
    status: Literal["pending", "all"] = "pending",
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ApprovalsQuery:
    return ApprovalsQuery(status=status, limit=limit, offset=offset)


def _activity_query(
    type: Literal["lead", "support", "invoice", "all"] = "all",
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> ActivityQuery:
    return ActivityQuery(type=type, limit=limit, offset=offset)


@router.get("/context", response_model=WorkspaceContextResponse)
def workspace_context(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_customer_session_tenant),
) -> WorkspaceContextResponse:
    return get_workspace_context(db, tenant_id)


@router.get("/overview", response_model=OverviewResponse)
def workspace_overview(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_customer_session_tenant),
) -> OverviewResponse:
    return get_workspace_overview(db, tenant_id)


@router.get("/work-items", response_model=WorkItemListResponse)
def workspace_work_items(
    query: WorkItemsQuery = Depends(_work_items_query),
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_customer_session_tenant),
) -> WorkItemListResponse:
    return list_workspace_work_items(db, tenant_id, query)


@router.get("/work-items/{work_item_id}", response_model=WorkItemDetailResponse)
def workspace_work_item_detail(
    work_item_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_customer_session_tenant),
) -> WorkItemDetailResponse:
    return get_workspace_work_item(db, tenant_id, work_item_id)


@router.get("/approvals", response_model=ApprovalListResponse)
def workspace_approvals(
    query: ApprovalsQuery = Depends(_approvals_query),
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_customer_session_tenant),
) -> ApprovalListResponse:
    return list_workspace_approvals(
        db,
        tenant_id,
        limit=query.limit,
        offset=query.offset,
        status=query.status,
    )


@router.get("/activity", response_model=ActivityListResponse)
def workspace_activity(
    query: ActivityQuery = Depends(_activity_query),
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_customer_session_tenant),
) -> ActivityListResponse:
    return list_workspace_activity(
        db,
        tenant_id,
        activity_type=query.type,
        limit=query.limit,
        offset=query.offset,
    )


@router.get("/health", response_model=HealthResponse)
def workspace_health(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_customer_session_tenant),
) -> HealthResponse:
    return get_workspace_health(db, tenant_id)
