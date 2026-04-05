from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.domain.workflows.models import Job
from app.domain.workflows.schemas import JobCreateRequest, JobResponse
from app.repositories.postgres.job_repository import create_job, update_job
from app.workflows.pipeline_runner import run_pipeline

router = APIRouter()


@router.post("/jobs", response_model=JobResponse)
def create_job_endpoint(request: JobCreateRequest, db: Session = Depends(get_db)):
    job = Job(
        tenant_id=request.tenant_id,
        job_type=request.job_type,
        input_data=request.input_data,
    )

    # Spara initialt jobb
    db_job = create_job(db, job)

    # Kör pipeline
    processed_job = run_pipeline(job, db)

    # Uppdatera DB med resultat
    updated_job = update_job(db, processed_job)

    return JobResponse(
        job_id=updated_job.job_id,
        tenant_id=updated_job.tenant_id,
        job_type=updated_job.job_type.value,
        status=updated_job.status.value,
        input_data=updated_job.input_data,
        result=updated_job.result,
        processor_history=updated_job.processor_history,
        created_at=updated_job.created_at.isoformat(),
        updated_at=updated_job.updated_at.isoformat(),
    )