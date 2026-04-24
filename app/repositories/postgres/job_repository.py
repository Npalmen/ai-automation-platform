from sqlalchemy.orm import Session

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.repositories.postgres.job_models import JobRecord


class JobRepository:
    @staticmethod
    def _to_domain(record: JobRecord) -> Job:
        stored_result = record.result or {}
        processor_history = stored_result.get("processor_history", [])

        result = stored_result.copy() if isinstance(stored_result, dict) else stored_result
        if isinstance(result, dict) and "processor_history" in result:
            result = result.copy()
            result.pop("processor_history", None)

        return Job(
            job_id=record.job_id,
            tenant_id=record.tenant_id,
            job_type=JobType(record.job_type),
            status=record.status,
            input_data=record.input_data or {},
            result=result,
            processor_history=processor_history,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def create_job(db: Session, job: Job) -> Job:
        record = JobRecord(
            job_id=job.job_id,
            tenant_id=job.tenant_id,
            job_type=job.job_type.value,
            status=job.status,
            input_data=job.input_data,
            result={
                **(job.result or {}),
                "processor_history": job.processor_history,
            },
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        return JobRepository._to_domain(record)

    @staticmethod
    def update_job(db: Session, job: Job) -> Job:
        db_job = JobRepository.get_job_by_id_record(db, job.tenant_id, job.job_id)

        if not db_job:
            raise ValueError("Job not found")

        db_job.job_type = job.job_type.value if hasattr(job.job_type, "value") else str(job.job_type)
        db_job.status = job.status
        db_job.input_data = job.input_data
        db_job.result = {
            **(job.result or {}),
            "processor_history": job.processor_history,
        }
        db_job.updated_at = job.updated_at

        db.commit()
        db.refresh(db_job)

        return JobRepository._to_domain(db_job)

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
    def get_job_by_id_record(db: Session, tenant_id: str, job_id: str) -> JobRecord | None:
        return (
            db.query(JobRecord)
            .filter_by(tenant_id=tenant_id, job_id=job_id)
            .first()
        )

    @staticmethod
    def get_job_by_id(db: Session, tenant_id: str, job_id: str) -> Job | None:
        record = JobRepository.get_job_by_id_record(db, tenant_id, job_id)
        if record is None:
            return None
        return JobRepository._to_domain(record)

    @staticmethod
    def get_by_gmail_message_id(db: Session, tenant_id: str, message_id: str) -> Job | None:
        record = (
            db.query(JobRecord)
            .filter(
                JobRecord.tenant_id == tenant_id,
                JobRecord.input_data["source"]["system"].as_string() == "gmail",
                JobRecord.input_data["source"]["message_id"].as_string() == message_id,
            )
            .order_by(JobRecord.created_at.desc())
            .first()
        )
        if record is None:
            return None
        return JobRepository._to_domain(record)

    @staticmethod
    def get_by_source_thread_id(
        db: Session,
        tenant_id: str,
        source_system: str,
        thread_id: str,
    ) -> "Job | None":
        record = (
            db.query(JobRecord)
            .filter(
                JobRecord.tenant_id == tenant_id,
                JobRecord.input_data["source"]["system"].as_string() == source_system,
                JobRecord.input_data["source"]["thread_id"].as_string() == thread_id,
            )
            .order_by(JobRecord.created_at.desc())
            .first()
        )
        if record is None:
            return None
        return JobRepository._to_domain(record)

    # Aliases used by main.py
    @staticmethod
    def list_jobs(
        db: Session,
        tenant_id: str,
        limit: int = 20,
        offset: int = 0,
        job_type: str | None = None,
        status: str | None = None,
    ) -> list[Job]:
        records = JobRepository.list_jobs_for_tenant(
            db, tenant_id, limit=limit, offset=offset, job_type=job_type, status=status
        )
        return [JobRepository._to_domain(r) for r in records]

    @staticmethod
    def count_jobs(
        db: Session,
        tenant_id: str,
        job_type: str | None = None,
        status: str | None = None,
    ) -> int:
        return JobRepository.count_jobs_for_tenant(
            db, tenant_id, job_type=job_type, status=status
        )