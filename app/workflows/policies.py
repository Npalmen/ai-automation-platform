from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import get_tenant_config
from app.domain.workflows.enums import JobType

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _normalize_job_type(value: JobType | str) -> str:
    if isinstance(value, JobType):
        return value.value
    return str(value)


def is_job_type_enabled_for_tenant(
    job_type: JobType | str,
    tenant_id: str,
    db: "Session | None" = None,
) -> bool:
    tenant_config = get_tenant_config(tenant_id, db=db)
    enabled_job_types = tenant_config.get("enabled_job_types", [])

    requested = _normalize_job_type(job_type)
    enabled = {_normalize_job_type(item) for item in enabled_job_types}

    return requested in enabled