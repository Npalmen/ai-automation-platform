from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import get_tenant_config
from app.integrations.enums import IntegrationType

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def is_integration_enabled_for_tenant(
    tenant_id: str,
    integration_type: IntegrationType,
    db: "Session | None" = None,
) -> bool:
    config = get_tenant_config(tenant_id, db=db)
    allowed_integrations = config.get("allowed_integrations", [])

    return any(
        allowed == integration_type or allowed == integration_type.value
        for allowed in allowed_integrations
    )