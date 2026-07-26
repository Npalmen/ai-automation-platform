"""Operator-only write routes for the end-customer domain."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.admin_auth import require_operator_role
from app.core.admin_session import require_same_origin
from app.domain.customer.api_schemas import (
    CustomerErrorResponse,
    DuplicateDecisionRequest,
    OperatorAddFactRequest,
    OperatorCreateCustomerRequest,
    OperatorCreateIdentityRequest,
    OperatorCreateJobLinkRequest,
    OperatorUpdateCustomerRequest,
    OperatorVerifyFactRequest,
)
from app.domain.customer.enums import CustomerErrorCode
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
from app.services.end_customer_command_service import (
    EndCustomerAuditError,
    EndCustomerCommandError,
    EndCustomerCommandService,
)
from app.repositories.postgres.end_customer_repository import EndCustomerNotFoundError

_OPERATOR_WRITE_ROLES = frozenset({"operations", "admin", "super_admin"})

admin_customer_writes_router = APIRouter(prefix="/admin/tenants/{tenant_id}/end-customers")
admin_duplicate_writes_router = APIRouter(
    prefix="/admin/tenants/{tenant_id}/end-customer-duplicates"
)


def _tenant_not_found(tenant_id: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Tenant '{tenant_id}' not found.")


def _require_operator_tenant(db: Session, tenant_id: str) -> None:
    record = TenantConfigRepository.get(db, tenant_id)
    if record is None:
        raise _tenant_not_found(tenant_id)


def _error_response(code: CustomerErrorCode, message: str, status: int, details: dict | None = None) -> HTTPException:
    body = CustomerErrorResponse(code=code, message=message, details=details or {})
    return HTTPException(status_code=status, detail=body.model_dump())


def _map_command_error(exc: EndCustomerCommandError) -> HTTPException:
    code_map = {
        "CUSTOMER_NOT_FOUND": (CustomerErrorCode.CUSTOMER_NOT_FOUND, 404),
        "DUPLICATE_CANDIDATE_NOT_FOUND": (CustomerErrorCode.DUPLICATE_CANDIDATE_NOT_FOUND, 404),
        "CUSTOMER_VERSION_CONFLICT": (CustomerErrorCode.CUSTOMER_VERSION_CONFLICT, 409),
        "DUPLICATE_DECISION_CONFLICT": (CustomerErrorCode.DUPLICATE_DECISION_CONFLICT, 409),
        "IDEMPOTENCY_CONFLICT": (CustomerErrorCode.IDEMPOTENCY_CONFLICT, 409),
        "INVALID_CUSTOMER_IDENTITY": (CustomerErrorCode.INVALID_CUSTOMER_IDENTITY, 409),
        "IDENTITY_COLLISION_REVIEW_REQUIRED": (
            CustomerErrorCode.IDENTITY_COLLISION_REVIEW_REQUIRED,
            409,
        ),
        "INVALID_SOURCE_PROVENANCE": (CustomerErrorCode.INVALID_SOURCE_PROVENANCE, 422),
        "UNSUPPORTED_CUSTOMER_TRANSITION": (CustomerErrorCode.UNSUPPORTED_CUSTOMER_TRANSITION, 422),
        "AUTOMATIC_MERGE_FORBIDDEN": (CustomerErrorCode.AUTOMATIC_MERGE_FORBIDDEN, 422),
        "INVALID_PAGINATION": (CustomerErrorCode.INVALID_PAGINATION, 422),
        "INTERNAL_ERROR": (CustomerErrorCode.CUSTOMER_NOT_FOUND, 500),
    }
    code, status = code_map.get(exc.code, (CustomerErrorCode.CUSTOMER_NOT_FOUND, 500))
    if exc.code == "INTERNAL_ERROR":
        message = "Operation could not be verified."
    else:
        message = exc.message
    return _error_response(code, message, status, exc.details)


def _parse_idempotency_key(idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")) -> str:
    if idempotency_key is None:
        raise _error_response(
            CustomerErrorCode.INVALID_PAGINATION,
            "Idempotency-Key header is required.",
            422,
        )
    try:
        return EndCustomerCommandService.validate_idempotency_key(idempotency_key)
    except EndCustomerCommandError as exc:
        raise _map_command_error(exc) from exc


def _run_command(handler):
    try:
        return handler()
    except EndCustomerNotFoundError as exc:
        raise _error_response(CustomerErrorCode.CUSTOMER_NOT_FOUND, "Resource not found.", 404) from exc
    except EndCustomerCommandError as exc:
        raise _map_command_error(exc) from exc
    except EndCustomerAuditError as exc:
        raise HTTPException(
            status_code=500,
            detail="Operation could not be verified.",
        ) from exc


@admin_customer_writes_router.post("", status_code=201)
def operator_create_end_customer(
    tenant_id: str,
    body: OperatorCreateCustomerRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    idempotency_key: str = Depends(_parse_idempotency_key),
):
    require_same_origin(request)
    _require_operator_tenant(db, tenant_id)

    def handler():
        return EndCustomerCommandService.create_customer(
            db, tenant_id, operator, body, idempotency_key
        )

    status_code, payload = _run_command(handler)
    return JSONResponse(status_code=status_code, content=payload)


@admin_customer_writes_router.patch("/{customer_id}")
def operator_update_end_customer(
    tenant_id: str,
    customer_id: str,
    body: OperatorUpdateCustomerRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    idempotency_key: str = Depends(_parse_idempotency_key),
):
    require_same_origin(request)
    _require_operator_tenant(db, tenant_id)

    def handler():
        return EndCustomerCommandService.update_customer(
            db, tenant_id, customer_id, operator, body, idempotency_key
        )

    status_code, payload = _run_command(handler)
    return JSONResponse(status_code=status_code, content=payload)


@admin_customer_writes_router.post("/{customer_id}/facts", status_code=201)
def operator_add_fact(
    tenant_id: str,
    customer_id: str,
    body: OperatorAddFactRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    idempotency_key: str = Depends(_parse_idempotency_key),
):
    require_same_origin(request)
    _require_operator_tenant(db, tenant_id)

    def handler():
        return EndCustomerCommandService.add_fact(
            db, tenant_id, customer_id, operator, body, idempotency_key
        )

    status_code, payload = _run_command(handler)
    return JSONResponse(status_code=status_code, content=payload)


@admin_customer_writes_router.post(
    "/{customer_id}/facts/{fact_id}/verify",
    status_code=201,
)
def operator_verify_fact(
    tenant_id: str,
    customer_id: str,
    fact_id: str,
    body: OperatorVerifyFactRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    idempotency_key: str = Depends(_parse_idempotency_key),
):
    require_same_origin(request)
    _require_operator_tenant(db, tenant_id)

    def handler():
        return EndCustomerCommandService.verify_fact(
            db, tenant_id, customer_id, fact_id, operator, body, idempotency_key
        )

    status_code, payload = _run_command(handler)
    return JSONResponse(status_code=status_code, content=payload)


@admin_customer_writes_router.post(
    "/{customer_id}/identities",
    status_code=201,
)
def operator_create_identity(
    tenant_id: str,
    customer_id: str,
    body: OperatorCreateIdentityRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    idempotency_key: str = Depends(_parse_idempotency_key),
):
    require_same_origin(request)
    _require_operator_tenant(db, tenant_id)

    def handler():
        return EndCustomerCommandService.create_identity(
            db, tenant_id, customer_id, operator, body, idempotency_key
        )

    status_code, payload = _run_command(handler)
    return JSONResponse(status_code=status_code, content=payload)


@admin_customer_writes_router.post(
    "/{customer_id}/job-links",
    status_code=201,
)
def operator_create_job_link(
    tenant_id: str,
    customer_id: str,
    body: OperatorCreateJobLinkRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    idempotency_key: str = Depends(_parse_idempotency_key),
):
    require_same_origin(request)
    _require_operator_tenant(db, tenant_id)

    def handler():
        return EndCustomerCommandService.create_job_link(
            db, tenant_id, customer_id, operator, body, idempotency_key
        )

    status_code, payload = _run_command(handler)
    return JSONResponse(status_code=status_code, content=payload)


@admin_duplicate_writes_router.post("/{candidate_id}/decision")
def operator_duplicate_decision(
    tenant_id: str,
    candidate_id: str,
    body: DuplicateDecisionRequest,
    request: Request,
    db: Session = Depends(get_db),
    operator=Depends(require_operator_role(_OPERATOR_WRITE_ROLES)),
    idempotency_key: str = Depends(_parse_idempotency_key),
):
    require_same_origin(request)
    _require_operator_tenant(db, tenant_id)

    def handler():
        return EndCustomerCommandService.duplicate_decision(
            db,
            tenant_id,
            candidate_id,
            operator,
            body.decision,
            body.expected_version,
            body.reason,
            idempotency_key,
        )

    status_code, payload = _run_command(handler)
    return JSONResponse(status_code=status_code, content=payload)
