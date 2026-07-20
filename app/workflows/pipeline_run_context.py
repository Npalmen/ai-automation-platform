"""Explicit pipeline run context for decision trace (no thread-local)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.workflows.decision_record import PipelineRunSource

if TYPE_CHECKING:
    from app.domain.workflows.models import Job


@dataclass(frozen=True)
class PipelineRunContext:
    pipeline_run_id: str
    parent_pipeline_run_id: str | None
    source: PipelineRunSource
    tenant_id: str
    job_id: str
    tenant_config_version: int | None
    code_version: str
    started_at: datetime


@dataclass
class DecisionTraceSession:
    """Mutable per-run trace state passed explicitly through the pipeline."""

    pipeline_run: PipelineRunContext
    db: Session | None = None
    _stage_sequence: int = field(default=0, repr=False)

    def next_stage(self) -> int:
        self._stage_sequence += 1
        return self._stage_sequence


def _read_code_version() -> str:
    from app.core.settings import get_settings

    settings = get_settings()
    return getattr(settings, "APP_CODE_VERSION", None) or settings.ENV


def _read_tenant_config_version(db: Session | None, tenant_id: str) -> int | None:
    if db is None:
        return None
    try:
        from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

        record = TenantConfigRepository.get(db, tenant_id)
        if record is None:
            return None
        return int(record.config_version)
    except Exception:
        return None


def create_pipeline_run_context(
    job: Job,
    *,
    source: PipelineRunSource,
    db: Session | None = None,
    parent_pipeline_run_id: str | None = None,
) -> PipelineRunContext:
    return PipelineRunContext(
        pipeline_run_id=str(uuid.uuid4()),
        parent_pipeline_run_id=parent_pipeline_run_id,
        source=source,
        tenant_id=job.tenant_id,
        job_id=job.job_id,
        tenant_config_version=_read_tenant_config_version(db, job.tenant_id),
        code_version=_read_code_version(),
        started_at=datetime.now(timezone.utc),
    )


def create_trace_session(
    job: Job,
    *,
    source: PipelineRunSource,
    db: Session | None = None,
    parent_pipeline_run_id: str | None = None,
) -> DecisionTraceSession:
    return DecisionTraceSession(
        pipeline_run=create_pipeline_run_context(
            job,
            source=source,
            db=db,
            parent_pipeline_run_id=parent_pipeline_run_id,
        ),
        db=db,
    )
