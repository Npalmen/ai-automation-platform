from app.core.config import get_tenant_config
from app.integrations.enums import IntegrationType


def is_integration_enabled_for_tenant(
    tenant_id: str,
    integration_type: IntegrationType,
) -> bool:
    config = get_tenant_config(tenant_id)
    allowed_integrations = config.get("allowed_integrations", [])

    return any(
        allowed == integration_type or allowed == integration_type.value
        for allowed in allowed_integrations
    )