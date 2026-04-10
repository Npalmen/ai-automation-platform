"""
API key authentication dependency.

Per-tenant API keys are configured via the TENANT_API_KEYS environment variable
as a JSON string mapping tenant_id to api_key:

    TENANT_API_KEYS='{"TENANT_1001": "key-abc123", "TENANT_2001": "key-def456"}'

If TENANT_API_KEYS is empty or not set, auth is disabled and the X-Tenant-ID
header is used directly (development mode only). A warning is logged at startup.

Protected endpoints use:
    tenant_id: str = Depends(get_verified_tenant)
"""
from __future__ import annotations

import json
import logging

from fastapi import Header, HTTPException
from fastapi import status as http_status

from app.core.settings import get_settings
from app.core.tenancy import set_current_tenant

logger = logging.getLogger(__name__)

# Parsed once at module load from settings.
_API_KEY_MAP: dict[str, str] | None = None


def _load_api_key_map() -> dict[str, str]:
    global _API_KEY_MAP
    if _API_KEY_MAP is not None:
        return _API_KEY_MAP

    raw = get_settings().TENANT_API_KEYS.strip()
    if not raw:
        logger.warning(
            "TENANT_API_KEYS is not configured. "
            "API key validation is DISABLED. "
            "Do not run without auth in production."
        )
        _API_KEY_MAP = {}
        return _API_KEY_MAP

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"TENANT_API_KEYS is not valid JSON: {exc}"
        ) from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("TENANT_API_KEYS must be a JSON object mapping tenant_id to api_key.")

    _API_KEY_MAP = {str(k): str(v) for k, v in parsed.items()}
    logger.info("API key auth enabled for %d tenant(s).", len(_API_KEY_MAP))
    return _API_KEY_MAP


def get_verified_tenant(
    x_api_key: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
) -> str:
    """
    FastAPI dependency. Returns the verified tenant_id for the request.

    When TENANT_API_KEYS is configured:
      - X-API-Key header is required.
      - The key is looked up to resolve the tenant.
      - X-Tenant-ID header is ignored (tenant is derived from the key).

    When TENANT_API_KEYS is empty (dev mode):
      - X-Tenant-ID header is used directly (no validation).
      - Defaults to TENANT_1001 if omitted.
    """
    key_map = _load_api_key_map()

    if not key_map:
        # Auth disabled — dev mode fallback.
        tenant_id = x_tenant_id or "TENANT_1001"
        set_current_tenant(tenant_id)
        return tenant_id

    # Auth enabled — require and validate X-API-Key.
    if not x_api_key:
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide the X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Reverse lookup: find which tenant owns this key.
    tenant_id = next(
        (tid for tid, key in key_map.items() if key == x_api_key),
        None,
    )

    if tenant_id is None:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail="Invalid API key.",
        )

    set_current_tenant(tenant_id)
    return tenant_id
