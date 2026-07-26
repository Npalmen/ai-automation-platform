"""Read-only HTTP routes for the end-customer domain."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.admin_session_models import VALID_OPERATOR_ROLES
from app.core.admin_auth import require_operator_role
from app.core.auth import get_verified_tenant
from app.domain.customer.api_schemas import (
    CustomerErrorResponse,
    DuplicateCandidateListViewResponse,
    EndCustomerCardDetailResponse,
    EndCustomerListViewResponse,
    EndCustomerSearchResponse,
    LinkedJobsViewResponse,
    LinkedThreadsViewResponse,
    TimelineViewResponse,
)
from app.domain.customer.enums import CustomerErrorCode
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
from app.services.end_customer_read_service import (
    EndCustomerReadService,
    EndCustomerReadValidationError,
)

_OPERATOR_READ_ROLES = VALID_OPERATOR_ROLES

tenant_router = APIRouter()
tenant_duplicates_router = APIRouter()
admin_router = APIRouter(prefix="/admin/tenants/{tenant_id}/end-customers")
admin_duplicates_router = APIRouter(prefix="/admin/tenants/{tenant_id}/end-customer-duplicates")


def _customer_not_found() -> HTTPException:
    body = CustomerErrorResponse(
        code=CustomerErrorCode.CUSTOMER_NOT_FOUND,
        message="Customer not found.",
    )
    return HTTPException(status_code=404, detail=body.model_dump())


def _validation_error(exc: EndCustomerReadValidationError) -> HTTPException:
    code_map = {
        "INVALID_SEARCH_QUERY": CustomerErrorCode.INVALID_SEARCH_QUERY,
        "INVALID_SORT": CustomerErrorCode.INVALID_SORT,
        "INVALID_PAGINATION": CustomerErrorCode.INVALID_PAGINATION,
    }
    body = CustomerErrorResponse(
        code=code_map.get(exc.code, CustomerErrorCode.INVALID_SEARCH_QUERY),
        message=exc.message,
        details=exc.details,
    )
    return HTTPException(status_code=422, detail=body.model_dump())


def _tenant_not_found(tenant_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found.")


def _require_operator_tenant(db: Session, tenant_id: str) -> None:
    record = TenantConfigRepository.get(db, tenant_id)
    if record is None:
        raise _tenant_not_found(tenant_id)


@tenant_router.get("", response_model=EndCustomerListViewResponse)
def tenant_list_end_customers(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
    status: str | None = Query(default=None),
    customer_type: str | None = Query(default=None),
    sort: str = Query(default="created_at"),
    order: str = Query(default="desc"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> EndCustomerListViewResponse:
    try:
        return EndCustomerReadService.list_customers(
            db,
            tenant_id,
            status=status,
            customer_type=customer_type,
            sort=sort,
            order=order,
            limit=limit,
            offset=offset,
        )
    except EndCustomerReadValidationError as exc:
        raise _validation_error(exc) from exc


@tenant_router.get("/search", response_model=EndCustomerSearchResponse)
def tenant_search_end_customers(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
    q: str = Query(min_length=1),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> EndCustomerSearchResponse:
    try:
        return EndCustomerReadService.search(
            db, tenant_id, q, limit=limit, offset=offset
        )
    except EndCustomerReadValidationError as exc:
        raise _validation_error(exc) from exc


@tenant_router.get("/{customer_id}/timeline", response_model=TimelineViewResponse)
def tenant_customer_timeline(
    customer_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TimelineViewResponse:
    result = EndCustomerReadService.list_timeline(
        db, tenant_id, customer_id, limit=limit, offset=offset
    )
    if result is None:
        raise _customer_not_found()
    return result


@tenant_router.get("/{customer_id}/jobs", response_model=LinkedJobsViewResponse)
def tenant_customer_jobs(
    customer_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> LinkedJobsViewResponse:
    result = EndCustomerReadService.list_jobs(
        db, tenant_id, customer_id, limit=limit, offset=offset
    )
    if result is None:
        raise _customer_not_found()
    return result


@tenant_router.get("/{customer_id}/threads", response_model=LinkedThreadsViewResponse)
def tenant_customer_threads(
    customer_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> LinkedThreadsViewResponse:
    result = EndCustomerReadService.list_threads(
        db, tenant_id, customer_id, limit=limit, offset=offset
    )
    if result is None:
        raise _customer_not_found()
    return result


@tenant_router.get("/{customer_id}", response_model=EndCustomerCardDetailResponse)
def tenant_customer_detail(
    customer_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
) -> EndCustomerCardDetailResponse:
    result = EndCustomerReadService.get_customer_card(db, tenant_id, customer_id)
    if result is None:
        raise _customer_not_found()
    return result


@tenant_duplicates_router.get("", response_model=DuplicateCandidateListViewResponse)
def tenant_list_duplicates(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_verified_tenant),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DuplicateCandidateListViewResponse:
    return EndCustomerReadService.list_duplicates(
        db, tenant_id, limit=limit, offset=offset
    )


@admin_router.get("", response_model=EndCustomerListViewResponse)
def admin_list_end_customers(
    tenant_id: str,
    db: Session = Depends(get_db),
    _operator=Depends(require_operator_role(_OPERATOR_READ_ROLES)),
    status: str | None = Query(default=None),
    customer_type: str | None = Query(default=None),
    sort: str = Query(default="created_at"),
    order: str = Query(default="desc"),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> EndCustomerListViewResponse:
    _require_operator_tenant(db, tenant_id)
    try:
        return EndCustomerReadService.list_customers(
            db,
            tenant_id,
            status=status,
            customer_type=customer_type,
            sort=sort,
            order=order,
            limit=limit,
            offset=offset,
        )
    except EndCustomerReadValidationError as exc:
        raise _validation_error(exc) from exc


@admin_router.get("/search", response_model=EndCustomerSearchResponse)
def admin_search_end_customers(
    tenant_id: str,
    db: Session = Depends(get_db),
    _operator=Depends(require_operator_role(_OPERATOR_READ_ROLES)),
    q: str = Query(min_length=1),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> EndCustomerSearchResponse:
    _require_operator_tenant(db, tenant_id)
    try:
        return EndCustomerReadService.search(
            db, tenant_id, q, limit=limit, offset=offset
        )
    except EndCustomerReadValidationError as exc:
        raise _validation_error(exc) from exc


@admin_router.get("/{customer_id}/timeline", response_model=TimelineViewResponse)
def admin_customer_timeline(
    tenant_id: str,
    customer_id: str,
    db: Session = Depends(get_db),
    _operator=Depends(require_operator_role(_OPERATOR_READ_ROLES)),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> TimelineViewResponse:
    _require_operator_tenant(db, tenant_id)
    result = EndCustomerReadService.list_timeline(
        db, tenant_id, customer_id, limit=limit, offset=offset
    )
    if result is None:
        raise _customer_not_found()
    return result


@admin_router.get("/{customer_id}/jobs", response_model=LinkedJobsViewResponse)
def admin_customer_jobs(
    tenant_id: str,
    customer_id: str,
    db: Session = Depends(get_db),
    _operator=Depends(require_operator_role(_OPERATOR_READ_ROLES)),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> LinkedJobsViewResponse:
    _require_operator_tenant(db, tenant_id)
    result = EndCustomerReadService.list_jobs(
        db, tenant_id, customer_id, limit=limit, offset=offset
    )
    if result is None:
        raise _customer_not_found()
    return result


@admin_router.get("/{customer_id}/threads", response_model=LinkedThreadsViewResponse)
def admin_customer_threads(
    tenant_id: str,
    customer_id: str,
    db: Session = Depends(get_db),
    _operator=Depends(require_operator_role(_OPERATOR_READ_ROLES)),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> LinkedThreadsViewResponse:
    _require_operator_tenant(db, tenant_id)
    result = EndCustomerReadService.list_threads(
        db, tenant_id, customer_id, limit=limit, offset=offset
    )
    if result is None:
        raise _customer_not_found()
    return result


@admin_router.get("/{customer_id}", response_model=EndCustomerCardDetailResponse)
def admin_customer_detail(
    tenant_id: str,
    customer_id: str,
    db: Session = Depends(get_db),
    _operator=Depends(require_operator_role(_OPERATOR_READ_ROLES)),
) -> EndCustomerCardDetailResponse:
    _require_operator_tenant(db, tenant_id)
    result = EndCustomerReadService.get_customer_card(db, tenant_id, customer_id)
    if result is None:
        raise _customer_not_found()
    return result


@admin_duplicates_router.get("", response_model=DuplicateCandidateListViewResponse)
def admin_list_duplicates(
    tenant_id: str,
    db: Session = Depends(get_db),
    _operator=Depends(require_operator_role(_OPERATOR_READ_ROLES)),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> DuplicateCandidateListViewResponse:
    _require_operator_tenant(db, tenant_id)
    return EndCustomerReadService.list_duplicates(
        db, tenant_id, limit=limit, offset=offset
    )
