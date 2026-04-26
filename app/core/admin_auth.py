"""
Admin API key authentication dependency.

Protects cross-tenant admin endpoints (e.g. GET /admin/tenants/overview).

Rules:
  - Reads X-Admin-API-Key header.
  - Compares to ADMIN_API_KEY env var using constant-time comparison.
  - Missing header  → 401 Unauthorized.
  - Wrong key       → 401 Unauthorized (same code — no enumeration).
  - ADMIN_API_KEY not configured → 401 Unauthorized (fail closed).
  - Tenant X-API-Key keys are NOT accepted on admin endpoints.
  - Secret value never appears in responses, logs, or error details.

Usage:
    @app.get("/admin/something")
    def endpoint(_: None = Depends(require_admin_api_key)):
        ...
"""
from __future__ import annotations

import hmac
import logging

from fastapi import Header, HTTPException
from fastapi import status as http_status

from app.core.settings import get_settings

logger = logging.getLogger(__name__)

_MISSING_OR_WRONG = "Missing or invalid admin API key. Provide the X-Admin-API-Key header."


def require_admin_api_key(
    x_admin_api_key: str | None = Header(default=None),
) -> None:
    """
    FastAPI dependency. Validates the X-Admin-API-Key header.

    Raises HTTP 401 if the key is missing, wrong, or not configured.
    Never exposes the configured secret value in any response.
    """
    configured = get_settings().ADMIN_API_KEY.strip()

    if not configured:
        # Fail closed: no admin key configured → admin endpoints unavailable.
        logger.warning(
            "Admin endpoint accessed but ADMIN_API_KEY is not configured. "
            "Returning 401. Set ADMIN_API_KEY to enable admin access."
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

    # Constant-time comparison prevents timing attacks.
    if not hmac.compare_digest(configured, x_admin_api_key):
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail=_MISSING_OR_WRONG,
            headers={"WWW-Authenticate": "AdminApiKey"},
        )
