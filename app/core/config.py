from __future__ import annotations

from typing import TYPE_CHECKING

from app.domain.workflows.enums import JobType
from app.integrations.enums import IntegrationType

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


TENANT_CONFIGS = {
    "TENANT_1001": {
        "name": "Default Tenant",
        "auto_actions": {
            JobType.LEAD.value: True,
            JobType.INVOICE.value: False,
            JobType.CUSTOMER_INQUIRY.value: True,
        },
        "enabled_job_types": [
            "lead",
            "invoice",
            "customer_inquiry",
        ],
        "allowed_integrations": [
            IntegrationType.CRM.value,
            IntegrationType.ACCOUNTING.value,
            IntegrationType.SUPPORT.value,
            IntegrationType.MONDAY.value,
            IntegrationType.FORTNOX.value,
            IntegrationType.VISMA.value,
            IntegrationType.GOOGLE_MAIL.value,
            IntegrationType.GOOGLE_CALENDAR.value,
            IntegrationType.MICROSOFT_MAIL.value,
            IntegrationType.MICROSOFT_CALENDAR.value,
        ],
    },
    "TENANT_2001": {
        "name": "Sales Tenant",
        "auto_actions": {
            JobType.LEAD.value: True,
            JobType.CUSTOMER_INQUIRY.value: True,
        },
        "enabled_job_types": [
            "lead",
            "customer_inquiry",
        ],
        "allowed_integrations": [
            IntegrationType.CRM.value,
            IntegrationType.MONDAY.value,
            IntegrationType.GOOGLE_MAIL.value,
            IntegrationType.GOOGLE_CALENDAR.value,
            IntegrationType.MICROSOFT_MAIL.value,
            IntegrationType.MICROSOFT_CALENDAR.value,
        ],
    },
    "TENANT_2002": {
        "name": "Sales Tenant 2",
        "auto_actions": {
            JobType.LEAD.value: True,
            JobType.CUSTOMER_INQUIRY.value: True,
        },
        "enabled_job_types": [
            "lead",
            "customer_inquiry",
        ],
        "allowed_integrations": [
            IntegrationType.CRM.value,
            IntegrationType.MONDAY.value,
            IntegrationType.GOOGLE_MAIL.value,
            IntegrationType.GOOGLE_CALENDAR.value,
            IntegrationType.MICROSOFT_MAIL.value,
            IntegrationType.MICROSOFT_CALENDAR.value,
        ],
    },
    "TENANT_3001": {
        "name": "Finance Tenant",
        "auto_actions": {
            JobType.INVOICE.value: True,
        },
        "enabled_job_types": [
            "invoice",
        ],
        "allowed_integrations": [
            IntegrationType.ACCOUNTING.value,
            IntegrationType.FORTNOX.value,
            IntegrationType.VISMA.value,
            IntegrationType.GOOGLE_MAIL.value,
            IntegrationType.MICROSOFT_MAIL.value,
        ],
    },
}


def _tenant_config_from_static(tenant_id: str) -> dict:
    return TENANT_CONFIGS.get(tenant_id, TENANT_CONFIGS["TENANT_1001"])


def get_tenant_config(tenant_id: str, db: "Session | None" = None) -> dict:
    """Return tenant config dict.

    Primary source: tenant_configs DB table (when db is provided and a row exists).
    Fallback: TENANT_CONFIGS static dict (backward compatibility).
    """
    if db is not None:
        try:
            from app.repositories.postgres.tenant_config_repository import TenantConfigRepository
            record = TenantConfigRepository.get(db, tenant_id)
            if record is not None:
                return TenantConfigRepository.to_dict(record)
        except Exception:
            # DB unavailable or table missing — fall through to static config.
            pass
    return _tenant_config_from_static(tenant_id)