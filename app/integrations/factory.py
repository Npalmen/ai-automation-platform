from app.integrations.enums import IntegrationType
from app.integrations.base import IntegrationAdapter
from app.integrations.config_models import IntegrationConnectionConfig
from app.integrations.google.adapter import GoogleIntegrationAdapter
from app.integrations.visma.adapter import VismaIntegrationAdapter


def get_integration_adapter(
    integration_type: IntegrationType,
    connection_config: IntegrationConnectionConfig | None = None
) -> IntegrationAdapter:
    if integration_type == IntegrationType.GOOGLE:
        return GoogleIntegrationAdapter(connection_config=connection_config)

    if integration_type == IntegrationType.VISMA:
        return VismaIntegrationAdapter(connection_config=connection_config)

    raise ValueError(f"No adapter registered for integration '{integration_type.value}'.")