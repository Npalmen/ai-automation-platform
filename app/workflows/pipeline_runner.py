from sqlalchemy.orm import Session

from app.domain.workflows.models import Job
from app.workflows.orchestrator import WorkflowOrchestrator
from app.workflows.pipeline_run_context import PipelineRunSource


def run_pipeline(
    job: Job,
    db: Session,
    *,
    run_source: PipelineRunSource = PipelineRunSource.INTAKE,
    parent_pipeline_run_id: str | None = None,
) -> Job:
    return WorkflowOrchestrator(db).run(
        job,
        source=run_source,
        parent_pipeline_run_id=parent_pipeline_run_id,
    )