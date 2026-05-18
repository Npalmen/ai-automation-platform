"""
Admin authentication dependencies.

Supports two auth modes (checked in order):
  1. Session cookie — set by POST /auth/admin/login (browser UX).
  2. X-Admin-API-Key header — for API / script / migration access.

Key resolution for header mode (priority order):
  1. ADMIN_API_KEYS (comma-separated list) — if set and non-empty, any key accepted.
  2. ADMIN_API_KEY (single key) — fallback.

Missing or wrong credentials → 401 Unauthorized.
Neither env var configured AND no session → 401 (fail closed).
Tenant X-API-Key keys are NOT accepted on admin endpoints.
Secret values never appear in responses, logs, or error details.

Usage:
    @app.get("/admin/something")
    def endpoint(_: None = Depends(require_admin_api_key)):
        ...
"""
from __future__ import annotations

import hmac
import logging

from fastapi import Header, HTTPException, Request
from fastapi import status as http_status

from app.core.settings import get_settings

logger = logging.getLogger(__name__)

_MISSING_OR_WRONG = "Missing or invalid admin credentials. Provide X-Admin-API-Key header or log in via /auth/admin/login."


def _resolve_admin_keys(s) -> list[str]:
    """Return the active set of valid admin keys, trimmed, without logging values."""
    raw_multi = getattr(s, "ADMIN_API_KEYS", None)
    multi = raw_multi.strip() if isinstance(raw_multi, str) else ""
    if multi:
        return [k.strip() for k in multi.split(",") if k.strip()]
    raw_single = getattr(s, "ADMIN_API_KEY", None)
    single = raw_single.strip() if isinstance(raw_single, str) else ""
    return [single] if single else []


def require_admin_api_key(
    request: Request,
    x_admin_api_key: str | None = Header(default=None),
) -> None:
    """
    FastAPI dependency. Accepts admin session cookie OR X-Admin-API-Key header.

    Priority:
      1. Valid session cookie (set by POST /auth/admin/login)
      2. Valid X-Admin-API-Key header

    Raises HTTP 401 if neither credential is valid.
    Never exposes configured secret values in any response.
    """
    # --- Session cookie path ---
    if request is not None:
        try:
            from app.core.admin_session import get_admin_from_session  # local import avoids circular
            admin_user = get_admin_from_session(request)
            if admin_user:
                return  # session cookie is valid
        except Exception:
            pass  # admin_session not available / misconfigured — fall through to key check

    # --- API key path ---
    valid_keys = _resolve_admin_keys(get_settings())

    if not valid_keys:
        logger.warning(
            "Admin endpoint accessed but no admin API key is configured and no valid session. "
            "Set ADMIN_API_KEY / ADMIN_API_KEYS, or configure session auth."
        )
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Admin access is not configured on this server.",
            headers={"WWW-Authenticate": "AdminApiKey"},
        )

    if not x_admin_api_key:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail=_MISSING_OR_WRONG,
            headers={"WWW-Authenticate": "AdminApiKey"},
        )

    provided = x_admin_api_key
    if not any(hmac.compare_digest(k, provided) for k in valid_keys):
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail=_MISSING_OR_WRONG,
            headers={"WWW-Authenticate": "AdminApiKey"},
        )
