from app.core.config import get_tenant_config
from app.integrations.enums import IntegrationType
from app.core.config import get_tenant_config


def is_integration_enabled_for_tenant(tenant_id: str, integration: IntegrationType) -> bool:
    config = get_tenant_config(tenant_id)

    enabled = config.get("enabled_integrations", [])
    return integration.value in enabled