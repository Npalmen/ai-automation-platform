from app.core.config import get_tenant_config
from app.integrations.enums import IntegrationType


def is_integration_enabled_for_tenant(
    tenant_id: str,
    integration_type: IntegrationType
) -> bool:
    tenant_config = get_tenant_config(tenant_id)
    allowed_integrations = tenant_config.get("allowed_integrations", [])
    return integration_type in allowed_integrations