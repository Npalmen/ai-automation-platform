from typing import Dict, Any

from app.domain.workflows.enums import JobType
from app.integrations.enums import IntegrationType
from app.integrations.config_models import IntegrationConnectionConfig


class TenantConfig:
    def __init__(self, tenant_id: str, data: Dict[str, Any]):
        self.tenant_id = tenant_id
        self.data = data

    def get(self, key: str, default=None):
        return self.data.get(key, default)


TENANTS = {
    "TENANT_1001": {
        "name": "Demo AB",
        "auto_actions": False,
        "allowed_integrations": [
            IntegrationType.GOOGLE,
            IntegrationType.VISMA,
        ],
        "integration_connections": {
            IntegrationType.GOOGLE: IntegrationConnectionConfig(
                enabled=True,
                connected=False,
                account_name="demo@demoab.se"
            ),
            IntegrationType.VISMA: IntegrationConnectionConfig(
                enabled=True,
                connected=False,
                account_name="Demo AB"
            ),
        },
        "enabled_job_types": [
            JobType.INTAKE,
            JobType.INVOICE,
            JobType.EMAIL,
            JobType.CONTRACT,
            JobType.UNKNOWN,
        ],
    },
    "TENANT_2002": {
        "name": "Testbolaget Norden AB",
        "auto_actions": True,
        "allowed_integrations": [
            IntegrationType.MICROSOFT,
            IntegrationType.FORTNOX,
        ],
        "integration_connections": {
            IntegrationType.MICROSOFT: IntegrationConnectionConfig(
                enabled=True,
                connected=False,
                account_name="admin@testbolaget.se"
            ),
            IntegrationType.FORTNOX: IntegrationConnectionConfig(
                enabled=True,
                connected=False,
                account_name="Testbolaget Norden AB"
            ),
        },
        "enabled_job_types": [
            JobType.EMAIL,
            JobType.UNKNOWN,
        ],
    }
}


def get_tenant_config(tenant_id: str) -> TenantConfig:
    data = TENANTS.get(tenant_id)

    if not data:
        raise ValueError(f"Tenant {tenant_id} finns inte")

    return TenantConfig(tenant_id, data)