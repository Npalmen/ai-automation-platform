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


def is_external_write_enabled_for_integration(
    tenant_id: str,
    integration_type: IntegrationType,
    db: "Session | None" = None,
) -> bool:
    """Fail-closed gate for external writes — requires enabled_external_writes."""
    from app.integrations.keys import normalize_integration_key
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

    if db is None:
        return is_integration_enabled_for_tenant(tenant_id, integration_type, db=db)

    settings = TenantConfigRepository.get_settings(db, tenant_id)
    integrations = settings.get("integrations") or {}
    selections = integrations.get("selections") or {}
    writes = integrations.get("enabled_external_writes")

    if not selections and writes is None:
        return is_integration_enabled_for_tenant(tenant_id, integration_type, db=db)

    normalized_writes = {
        normalize_integration_key(str(item))
        for item in (writes or [])
    }
    canonical = normalize_integration_key(integration_type.value)
    if canonical not in normalized_writes:
        return False
    return is_integration_enabled_for_tenant(tenant_id, integration_type, db=db)
