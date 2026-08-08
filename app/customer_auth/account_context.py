"""Read-only customer account context for /auth/customer/me — no app.main coupling."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.postgres.tenant_config_repository import TenantConfigRepository


def get_customer_company_name(db: Session, tenant_id: str) -> str:
    """Resolve display company name from tenant DB record only."""
    record = TenantConfigRepository.get(db, tenant_id)
    if record is None:
        return tenant_id
    settings = record.settings or {}
    account = settings.get("account") or {}
    branding = settings.get("branding") or {}
    return (
        (account.get("company_name") or "").strip()
        or (branding.get("company_display_name") or "").strip()
        or (record.name or "").strip()
        or tenant_id
    )
