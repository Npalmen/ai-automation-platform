"""
API key authentication dependency.

Auth priority:
  1. DB-backed tenant API keys (tenant_api_keys table) — checked first.
  2. Env-based TENANT_API_KEYS JSON map — backward-compatible fallback.
  3. Dev-mode passthrough — only when TENANT_API_KEYS is empty/unset and
     no DB key was provided.

Existing TENANT_2001 / TENANT_1001 env keys continue to work unchanged.
New tenants provisioned via POST /admin/tenants get DB-backed keys.

Protected endpoints use:
    tenant_id: str = Depends(get_verified_tenant)
"""
from __future__ import annotations

import hmac
import json
import logging

from fastapi import Depends, Header, HTTPException, Request
from fastapi import status as http_status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.settings import get_settings
from app.core.tenancy import set_current_tenant

logger = logging.getLogger(__name__)

# Env-based key map — parsed once, cached.
_API_KEY_MAP: dict[str, str] | None = None


def _load_env_key_map() -> dict[str, str]:
    global _API_KEY_MAP
    if _API_KEY_MAP is not None:
        return _API_KEY_MAP

    raw = get_settings().TENANT_API_KEYS.strip()
    if not raw:
        logger.warning(
            "TENANT_API_KEYS is not configured. "
            "DB-backed keys are the only auth source. "
            "Dev-mode passthrough active when no key is provided."
        )
        _API_KEY_MAP = {}
        return _API_KEY_MAP

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"TENANT_API_KEYS is not valid JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise RuntimeError("TENANT_API_KEYS must be a JSON object mapping tenant_id to api_key.")

    _API_KEY_MAP = {str(k): str(v) for k, v in parsed.items()}
    logger.info("Env API key fallback loaded for %d tenant(s).", len(_API_KEY_MAP))
    return _API_KEY_MAP


def _lookup_env_key(raw_key: str) -> str | None:
    """Reverse-lookup env map: raw_key → tenant_id, or None."""
    key_map = _load_env_key_map()
    return next((tid for tid, k in key_map.items() if k == raw_key), None)


def _is_production_env() -> bool:
    return str(getattr(get_settings(), "ENV", "") or "").strip().lower() in {"prod", "production"}


def _lookup_db_key(db: Session, raw_key: str) -> str | None:
    """Check DB for an active hashed key. Returns tenant_id or None.

    Degrades gracefully if the table doesn't exist yet (first boot).
    """
    try:
        from app.repositories.postgres.tenant_api_key_repository import TenantApiKeyRepository
        return TenantApiKeyRepository.lookup_tenant(db, raw_key)
    except Exception:
        return None


def _is_tenant_active(db: Session, tenant_id: str) -> bool:
    """Return False if the tenant exists in DB and is explicitly marked inactive."""
    try:
        from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
        record = TenantConfigRepository.get(db, tenant_id)
        if record is None:
            return True  # env-only tenant, not in DB — allow through
        return (record.status or "active") == "active"
    except Exception:
        return True  # degrade gracefully


def get_verified_tenant(
    request: Request = None,  # type: ignore[assignment]  # FastAPI injects; None in direct test calls
    x_api_key: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None),
    x_admin_api_key: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> str:
    """
    FastAPI dependency. Returns the verified tenant_id for the request.

    Resolution order (highest to lowest priority):
      0. Admin session cookie + X-Tenant-ID  — browser UI with session login
      1. X-Admin-API-Key + X-Tenant-ID       — API/script admin impersonation
      2. X-API-Key                           — tenant's own API key
      3. Dev-mode passthrough                — only when no keys are configured

    After resolution, checks tenant status == 'active'.
    """
    # Priority 0: Admin session cookie + explicit X-Tenant-ID header.
    # Allows the browser operator UI to call tenant-scoped endpoints after
    # POST /auth/admin/login without requiring a per-tenant API key in the UI.
    if request is not None:
        try:
            from app.core.admin_session import get_admin_from_session
            admin_user = get_admin_from_session(request)
            if admin_user:
                if not x_tenant_id:
                    raise HTTPException(
                        status_code=http_status.HTTP_400_BAD_REQUEST,
                        detail=(
                            "X-Tenant-ID is required when using admin session "
                            "on tenant endpoints."
                        ),
                    )
                if not _is_tenant_active(db, x_tenant_id):
                    raise HTTPException(
                        status_code=http_status.HTTP_403_FORBIDDEN,
                        detail="Tenant is inactive.",
                    )
                set_current_tenant(x_tenant_id)
                return x_tenant_id
        except HTTPException:
            raise
        except Exception:
            pass  # session module not configured or error — fall through

    # Priority 1: X-Admin-API-Key header + X-Tenant-ID.
    if isinstance(x_admin_api_key, str) and x_admin_api_key:
        from app.core.admin_auth import _resolve_admin_keys

        valid_keys = _resolve_admin_keys(get_settings())
        if not valid_keys:
            raise HTTPException(
                status_code=http_status.HTTP_401_UNAUTHORIZED,
                detail="Admin access is not configured on this server.",
                headers={"WWW-Authenticate": "AdminApiKey"},
            )
        if not any(hmac.compare_digest(k, x_admin_api_key) for k in valid_keys):
            raise HTTPException(
                status_code=http_status.HTTP_401_UNAUTHORIZED,
                detail="Missing or invalid admin API key. Provide the X-Admin-API-Key header.",
                headers={"WWW-Authenticate": "AdminApiKey"},
            )
        if not x_tenant_id:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="X-Tenant-ID is required when using X-Admin-API-Key on tenant endpoints.",
            )
        if not _is_tenant_active(db, x_tenant_id):
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Tenant is inactive.",
            )
        set_current_tenant(x_tenant_id)
        return x_tenant_id

    env_map = _load_env_key_map()

    if x_api_key:
        # 1. DB lookup (new provisioned keys)
        tenant_id = _lookup_db_key(db, x_api_key)

        # 2. Env fallback (existing keys)
        if tenant_id is None:
            tenant_id = _lookup_env_key(x_api_key)

        if tenant_id is None:
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Invalid API key.",
            )

        if not _is_tenant_active(db, tenant_id):
            raise HTTPException(
                status_code=http_status.HTTP_403_FORBIDDEN,
                detail="Tenant is inactive.",
            )

        set_current_tenant(tenant_id)
        return tenant_id

    # No key provided.
    if env_map:
        # Env auth is configured — key is required.
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide the X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if _is_production_env():
        raise HTTPException(
            status_code=http_status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Production requires X-API-Key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    # Dev-mode: no env keys, no DB key provided.
    tenant_id = x_tenant_id or "TENANT_1001"
    set_current_tenant(tenant_id)
    return tenant_id
