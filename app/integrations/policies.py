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
    raw = config.get("allowed_integrations", [])

    # Normalize to strings — config may contain enum objects or string values.
    allowed = [i.value if hasattr(i, "value") else i for i in raw]

    return integration_type.value in allowed