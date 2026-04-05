from sqlalchemy.orm import Session

from app.domain.workflows.models import Job
from app.repositories.postgres.job_models import JobRecord


class JobRepository:

    @staticmethod
    def create_job(db: Session, job: Job) -> JobRecord:
        record = JobRecord(
            job_id=job.job_id,
            tenant_id=job.tenant_id,
            job_type=job.job_type.value,
            status=job.status.value,
            input_data=job.input_data,
            result=job.result,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def update_job(db: Session, job: Job) -> JobRecord:
        record = db.query(JobRecord).filter_by(job_id=job.job_id).first()

        if record is None:
            raise ValueError(f"Job {job.job_id} not found in database")

        record.status = job.status.value
        record.result = job.result
        record.updated_at = job.updated_at

        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def list_jobs_for_tenant(
        db: Session,
        tenant_id: str,
        limit: int = 20,
        offset: int = 0,
        job_type: str | None = None,
        status: str | None = None,
    ) -> list[JobRecord]:

        query = db.query(JobRecord).filter_by(tenant_id=tenant_id)

        if job_type is not None:
            query = query.filter(JobRecord.job_type == job_type)

        if status is not None:
            query = query.filter(JobRecord.status == status)

        return (
            query
            .order_by(JobRecord.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    @staticmethod
    def count_jobs_for_tenant(
        db: Session,
        tenant_id: str,
        job_type: str | None = None,
        status: str | None = None,
    ) -> int:

        query = db.query(JobRecord).filter_by(tenant_id=tenant_id)

        if job_type is not None:
            query = query.filter(JobRecord.job_type == job_type)

        if status is not None:
            query = query.filter(JobRecord.status == status)

        return query.count()

    @staticmethod
    def get_job_by_id(db: Session, tenant_id: str, job_id: str) -> JobRecord | None:
        return (
            db.query(JobRecord)
            .filter_by(tenant_id=tenant_id, job_id=job_id)
            .first()
        )