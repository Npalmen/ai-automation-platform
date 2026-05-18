"""
Admin API key authentication dependency.

Protects cross-tenant admin endpoints (e.g. GET /admin/tenants/overview).

Rules:
  - Reads X-Admin-API-Key header.
  - Key resolution (in priority order):
      1. ADMIN_API_KEYS (comma-separated list) — if set and non-empty, any
         key in the list is accepted.
      2. ADMIN_API_KEY (single key) — fallback when ADMIN_API_KEYS is empty.
  - Missing header  → 401 Unauthorized.
  - Wrong key       → 401 Unauthorized (same code — no enumeration).
  - Neither env var configured → 401 Unauthorized (fail closed).
  - Tenant X-API-Key keys are NOT accepted on admin endpoints.
  - Secret values never appear in responses, logs, or error details.

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


def _resolve_admin_keys(s) -> list[str]:
    """Return the active set of valid admin keys, trimmed, without logging values.

    Priority: ADMIN_API_KEYS (comma-separated) > ADMIN_API_KEY (single).
    Returns an empty list when nothing is configured.
    Uses getattr + isinstance so the function is safe against SimpleNamespace
    objects, MagicMock stubs, and real Settings instances alike.
    """
    raw_multi = getattr(s, "ADMIN_API_KEYS", None)
    multi = raw_multi.strip() if isinstance(raw_multi, str) else ""
    if multi:
        return [k.strip() for k in multi.split(",") if k.strip()]
    raw_single = getattr(s, "ADMIN_API_KEY", None)
    single = raw_single.strip() if isinstance(raw_single, str) else ""
    return [single] if single else []


def require_admin_api_key(
    x_admin_api_key: str | None = Header(default=None),
) -> None:
    """
    FastAPI dependency. Validates the X-Admin-API-Key header.

    Raises HTTP 401 if the key is missing, wrong, or not configured.
    Never exposes the configured secret value in any response.
    """
    valid_keys = _resolve_admin_keys(get_settings())

    if not valid_keys:
        # Fail closed: no admin key configured → admin endpoints unavailable.
        logger.warning(
            "Admin endpoint accessed but no admin API key is configured. "
            "Returning 401. Set ADMIN_API_KEY or ADMIN_API_KEYS to enable admin access."
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

    # Constant-time comparison for each valid key.
    # All comparisons run against equal-length tokens so timing is uniform.
    provided = x_admin_api_key
    if not any(hmac.compare_digest(k, provided) for k in valid_keys):
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail=_MISSING_OR_WRONG,
            headers={"WWW-Authenticate": "AdminApiKey"},
        )
