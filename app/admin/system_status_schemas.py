"""Pydantic schemas for GET /admin/system/status (Kapitel 8)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

StatusLevel = Literal[
    "healthy",
    "warning",
    "failed",
    "critical",
    "paused",
    "unknown",
    "not_configured",
]

FreshnessLevel = Literal["reported", "stale", "not_reported"]

VerificationStatus = Literal["success", "failed", "not_performed", "unknown"]


class DomainStatus(BaseModel):
    status: StatusLevel
    label: str
    summary: str


class ComponentStatus(BaseModel):
    status: StatusLevel
    label: str
    summary: str
    checked_at: datetime
    source: str
    freshness: FreshnessLevel | None = None
    limitation: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ApiRuntimeStatus(ComponentStatus):
    pass


class DatabaseRuntimeStatus(ComponentStatus):
    pass


class SchedulerRuntimeStatus(ComponentStatus):
    pass


class JobsRuntimeStatus(ComponentStatus):
    pass


class IntegrationRuntimeStatus(ComponentStatus):
    issues: int = 0
    affected_tenants: int = 0


class RuntimeBlock(BaseModel):
    api: ApiRuntimeStatus
    database: DatabaseRuntimeStatus
    scheduler: SchedulerRuntimeStatus
    jobs: JobsRuntimeStatus
    integrations: dict[str, IntegrationRuntimeStatus]


class BackupResilienceStatus(ComponentStatus):
    operation_status: Literal["success", "failed", "unknown"] | None = None
    archive_integrity_verified: bool | None = None


class RestoreResilienceStatus(ComponentStatus):
    operation_status: Literal["success", "failed", "unknown"] | None = None
    schema_verification: VerificationStatus | None = None
    application_smoke_verification: VerificationStatus | None = None


class RetentionResilienceStatus(ComponentStatus):
    retention_days: int | None = None


class ResilienceBlock(BaseModel):
    last_backup: BackupResilienceStatus
    last_restore_test: RestoreResilienceStatus
    retention: RetentionResilienceStatus


class BuildDeployStatus(ComponentStatus):
    commit_sha: str | None = None
    build_time: datetime | None = None
    release_id: str | None = None


class LastDeployStatus(ComponentStatus):
    deployed_at: datetime | None = None


class RoutingConfigStatus(ComponentStatus):
    pass


class ReleaseGateStatus(ComponentStatus):
    pass


class DeploymentBlock(BaseModel):
    current_build: BuildDeployStatus
    last_deploy: LastDeployStatus
    routing_config: RoutingConfigStatus
    release_gate: ReleaseGateStatus


class RunbookRef(BaseModel):
    id: str
    label: str


class SystemStatusResponse(BaseModel):
    generated_at: datetime
    runtime_status: DomainStatus
    resilience_status: DomainStatus
    deploy_readiness_status: DomainStatus
    overall_status: DomainStatus
    runtime: RuntimeBlock
    resilience: ResilienceBlock
    deployment: DeploymentBlock
    limitations: list[str] = Field(default_factory=list)
    runbooks: list[RunbookRef] = Field(default_factory=list)
