"""Server-side customer workspace session authentication."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.admin_session import (
    hash_password,
    require_same_origin,
    verify_password,
)
from app.core.customer_session_models import CustomerSessionContext
from app.core.rate_limit import check_rate_limit
from app.core.settings import get_settings
from app.customer_auth.tenant_access import assert_tenant_allowed_for_customer_auth
from app.repositories.postgres.customer_workspace_session_repository import (
    DEFAULT_SESSION_MAX_AGE_SECONDS,
    CustomerWorkspaceSessionRepository,
    hash_session_token,
)
from app.repositories.postgres.customer_workspace_user_models import CustomerWorkspaceUserRecord
from app.repositories.postgres.customer_workspace_user_repository import (
    USER_STATUS_ACTIVE,
    CustomerWorkspaceUserRepository,
    normalize_email,
)

logger = logging.getLogger(__name__)

CUSTOMER_SESSION_COOKIE = "customer_session"
LOGIN_RATE_LIMIT_MAX = 5
LOGIN_RATE_LIMIT_WINDOW_SECONDS = 60
INVALID_CREDENTIALS_DETAIL = "Ogiltig e-postadress eller lösenord."
_TIMING_SAFE_DUMMY_HASH: str | None = None


def _cookie_secure() -> bool:
    env = getattr(get_settings(), "ENV", "dev").strip().lower()
    return env not in ("dev", "development", "local", "test")


def _session_max_age_seconds() -> int:
    configured = getattr(get_settings(), "CUSTOMER_SESSION_MAX_AGE_SECONDS", None)
    if configured is None:
        return DEFAULT_SESSION_MAX_AGE_SECONDS
    try:
        value = int(configured)
    except (TypeError, ValueError):
        return DEFAULT_SESSION_MAX_AGE_SECONDS
    return max(60, value)


def _login_identifier_bucket(email: str) -> str:
    normalized = normalize_email(email)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return f"customer_login:id:{digest}"


def enforce_customer_login_rate_limit(request: Request, email: str) -> None:
    """Dual-bucket in-memory rate limit: IP + hashed email identifier."""
    client_ip = request.client.host if request.client else "unknown"
    buckets = (
        f"customer_login:ip:{client_ip}",
        _login_identifier_bucket(email),
    )
    retry_after = 0
    for bucket in buckets:
        allowed, bucket_retry = check_rate_limit(
            bucket,
            max_calls=LOGIN_RATE_LIMIT_MAX,
            window_seconds=LOGIN_RATE_LIMIT_WINDOW_SECONDS,
        )
        if not allowed:
            retry_after = max(retry_after, bucket_retry)
    if retry_after > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="För många inloggningsförsök. Försök igen senare.",
            headers={"Retry-After": str(retry_after)},
        )


def set_customer_session_cookie(response: Response, raw_token: str, *, max_age: int) -> None:
    response.set_cookie(
        key=CUSTOMER_SESSION_COOKIE,
        value=raw_token,
        httponly=True,
        samesite="strict",
        max_age=max_age,
        secure=_cookie_secure(),
        path="/",
    )


def clear_customer_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=CUSTOMER_SESSION_COOKIE,
        httponly=True,
        samesite="strict",
        path="/",
        secure=_cookie_secure(),
    )


def _build_session_context(
    user: CustomerWorkspaceUserRecord,
) -> CustomerSessionContext:
    if user.role != "customer_viewer":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden.")
    return {
        "user_id": user.id,
        "tenant_id": user.tenant_id,
        "email": user.email,
        "display_name": user.display_name,
        "role": "customer_viewer",
    }


def resolve_customer_session(
    db: Session,
    request: Request,
) -> CustomerSessionContext:
    raw_token = request.cookies.get(CUSTOMER_SESSION_COOKIE, "")
    if not raw_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")

    session = CustomerWorkspaceSessionRepository.get_active_by_token_hash(
        db, hash_session_token(raw_token)
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")

    user = CustomerWorkspaceUserRepository.get_by_id(db, session.user_id)
    if user is None or user.status != USER_STATUS_ACTIVE:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")

    if session.tenant_id != user.tenant_id:
        logger.warning(
            "customer_session_tenant_mismatch user_id=%s session_tenant=%s user_tenant=%s",
            user.id,
            session.tenant_id,
            user.tenant_id,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated.")

    assert_tenant_allowed_for_customer_auth(db, user.tenant_id)
    return _build_session_context(user)


def get_customer_session_context(
    request: Request,
    db: Session = Depends(get_db),
) -> CustomerSessionContext:
    return resolve_customer_session(db, request)


def get_customer_session_tenant(
    ctx: CustomerSessionContext = Depends(get_customer_session_context),
) -> str:
    return ctx["tenant_id"]


def authenticate_customer_credentials(
    db: Session,
    *,
    email: str,
    password: str,
) -> CustomerWorkspaceUserRecord:
    global _TIMING_SAFE_DUMMY_HASH
    if _TIMING_SAFE_DUMMY_HASH is None:
        _TIMING_SAFE_DUMMY_HASH = hash_password("timing-safe-dummy-customer-auth")

    user = CustomerWorkspaceUserRepository.get_active_by_email(db, email)
    if user is None:
        verify_password(password, _TIMING_SAFE_DUMMY_HASH)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS_DETAIL)

    if not verify_password(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=INVALID_CREDENTIALS_DETAIL)

    assert_tenant_allowed_for_customer_auth(db, user.tenant_id)
    return user


def create_customer_login_session(
    db: Session,
    user: CustomerWorkspaceUserRecord,
) -> tuple[str, int]:
    max_age = _session_max_age_seconds()
    raw_token, _record = CustomerWorkspaceSessionRepository.create_session(
        db,
        user_id=user.id,
        tenant_id=user.tenant_id,
        max_age_seconds=max_age,
    )
    return raw_token, max_age


def revoke_customer_session_from_request(db: Session, request: Request) -> None:
    raw_token = request.cookies.get(CUSTOMER_SESSION_COOKIE, "")
    if not raw_token:
        return
    session = CustomerWorkspaceSessionRepository.get_active_by_token_hash(
        db, hash_session_token(raw_token)
    )
    if session is not None:
        CustomerWorkspaceSessionRepository.revoke_session(db, session)


__all__ = [
    "CUSTOMER_SESSION_COOKIE",
    "INVALID_CREDENTIALS_DETAIL",
    "authenticate_customer_credentials",
    "clear_customer_session_cookie",
    "create_customer_login_session",
    "enforce_customer_login_rate_limit",
    "get_customer_session_context",
    "get_customer_session_tenant",
    "hash_password",
    "require_same_origin",
    "resolve_customer_session",
    "revoke_customer_session_from_request",
    "set_customer_session_cookie",
]
