"""Customer workspace browser authentication routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.customer_session import (
    authenticate_customer_credentials,
    clear_customer_session_cookie,
    create_customer_login_session,
    enforce_customer_login_rate_limit,
    get_customer_session_context,
    require_same_origin,
    revoke_customer_session_from_request,
    set_customer_session_cookie,
)
from app.core.customer_session_models import (
    CustomerLoginRequest,
    CustomerLoginResponse,
    CustomerLogoutResponse,
    CustomerMeResponse,
    CustomerSessionContext,
)
from app.customer_auth.account_context import get_customer_company_name

router = APIRouter(tags=["customer-auth"])


@router.post("/auth/customer/login", response_model=CustomerLoginResponse)
def customer_login(
    payload: CustomerLoginRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    require_same_origin(request)
    enforce_customer_login_rate_limit(request, payload.email)
    user = authenticate_customer_credentials(db, email=payload.email, password=payload.password)
    raw_token, max_age = create_customer_login_session(db, user)
    body = CustomerLoginResponse(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        tenant_id=user.tenant_id,
    )
    response = JSONResponse(content=body.model_dump())
    set_customer_session_cookie(response, raw_token, max_age=max_age)
    return response


@router.post("/auth/customer/logout", response_model=CustomerLogoutResponse)
def customer_logout(
    request: Request,
    db: Session = Depends(get_db),
):
    require_same_origin(request)
    revoke_customer_session_from_request(db, request)
    response = JSONResponse(content=CustomerLogoutResponse().model_dump())
    clear_customer_session_cookie(response)
    return response


@router.get("/auth/customer/me", response_model=CustomerMeResponse)
def customer_me(
    ctx: CustomerSessionContext = Depends(get_customer_session_context),
    db: Session = Depends(get_db),
):
    return CustomerMeResponse(
        user_id=ctx["user_id"],
        email=ctx["email"],
        display_name=ctx["display_name"],
        tenant_id=ctx["tenant_id"],
        company_name=get_customer_company_name(db, ctx["tenant_id"]),
    )
