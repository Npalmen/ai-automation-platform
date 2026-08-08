"""Fail-closed tenant validation for customer workspace auth.

Unlike app.core.auth._is_tenant_active(), this module never fail-opens on
missing records, inactive tenants, or repository errors.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

logger = logging.getLogger(__name__)

_CANONICAL_ACTIVE_STATUS = "active"


class CustomerTenantAccessError(HTTPException):
    """Tenant denied for customer workspace access."""


def assert_tenant_allowed_for_customer_auth(db: Session, tenant_id: str) -> None:
    """Raise HTTPException if tenant may not be used for customer workspace auth."""
    try:
        record = TenantConfigRepository.get(db, tenant_id)
    except Exception:
        logger.exception("customer_auth_tenant_lookup_failed tenant_id=%s", tenant_id)
        raise CustomerTenantAccessError(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant is not available.",
        ) from None

    if record is None:
        raise CustomerTenantAccessError(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant is not available.",
        )

    tenant_status = (record.status or "").strip().lower()
    if tenant_status != _CANONICAL_ACTIVE_STATUS:
        raise CustomerTenantAccessError(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant is inactive.",
        )
