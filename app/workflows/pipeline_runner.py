from sqlalchemy.orm import Session

from app.domain.workflows.models import Job
from app.workflows.orchestrator import WorkflowOrchestrator


def run_pipeline(job: Job, db: Session) -> Job:
    return WorkflowOrchestrator(db).run(job)