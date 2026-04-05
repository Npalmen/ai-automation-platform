from app.core.config import get_tenant_config
from app.domain.workflows.enums import JobType


def is_job_type_enabled_for_tenant(tenant_id: str, job_type: JobType) -> bool:
    tenant_config = get_tenant_config(tenant_id)
    enabled_job_types = tenant_config.get("enabled_job_types", [])
    return job_type in enabled_job_types