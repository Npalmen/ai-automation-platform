# app/core/config.py

from app.domain.workflows.enums import JobType
from app.integrations.enums import IntegrationType


TENANT_CONFIGS = {
    "TENANT_1001": {
        "name": "Default Tenant",
        "auto_actions": {
            JobType.LEAD.value: True,
            JobType.INVOICE.value: False,
            JobType.CUSTOMER_INQUIRY.value: True,
        },
        "enabled_job_types": [
            JobType.LEAD,
            JobType.INVOICE,
            JobType.CUSTOMER_INQUIRY,
        ],
        "allowed_integrations": [
            IntegrationType.CRM,
            IntegrationType.ACCOUNTING,
            IntegrationType.SUPPORT,
            IntegrationType.MONDAY,
            IntegrationType.FORTNOX,
            IntegrationType.VISMA,
            IntegrationType.GOOGLE_MAIL,
            IntegrationType.GOOGLE_CALENDAR,
            IntegrationType.MICROSOFT_MAIL,
            IntegrationType.MICROSOFT_CALENDAR,
        ],
    },
    "TENANT_2001": {
        "name": "Sales Tenant",
        "auto_actions": {
            JobType.LEAD.value: True,
            JobType.CUSTOMER_INQUIRY.value: True,
        },
        "enabled_job_types": [
            JobType.LEAD,
            JobType.CUSTOMER_INQUIRY,
        ],
        "allowed_integrations": [
            IntegrationType.CRM,
            IntegrationType.MONDAY,
            IntegrationType.GOOGLE_MAIL,
            IntegrationType.GOOGLE_CALENDAR,
            IntegrationType.MICROSOFT_MAIL,
            IntegrationType.MICROSOFT_CALENDAR,
        ],
    },
    "TENANT_3001": {
        "name": "Finance Tenant",
        "auto_actions": {
            JobType.INVOICE.value: True,
        },
        "enabled_job_types": [
            JobType.INVOICE,
        ],
        "allowed_integrations": [
            IntegrationType.ACCOUNTING,
            IntegrationType.FORTNOX,
            IntegrationType.VISMA,
            IntegrationType.GOOGLE_MAIL,
            IntegrationType.MICROSOFT_MAIL,
        ],
    },
}


def get_tenant_config(tenant_id: str) -> dict:
    return TENANT_CONFIGS.get(
        tenant_id,
        TENANT_CONFIGS["TENANT_1001"],
    )