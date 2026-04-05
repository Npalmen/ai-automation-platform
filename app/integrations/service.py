from app.core.config import get_tenant_config
from app.integrations.config_models import IntegrationConnectionConfig
from app.integrations.enums import IntegrationType


def get_integration_connection_config(
    tenant_id: str,
    integration_type: IntegrationType
) -> IntegrationConnectionConfig:
    tenant_config = get_tenant_config(tenant_id)
    integration_connections = tenant_config.get("integration_connections", {})

    connection_config = integration_connections.get(integration_type)

    if connection_config is None:
        return IntegrationConnectionConfig(
            enabled=False,
            connected=False,
            account_name=None
        )

    return connection_config