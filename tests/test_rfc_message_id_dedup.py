"""RFC Message-ID deduplication tests."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.job_repository import JobRepository


def _session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    JobRecord.__table__.create(engine, checkfirst=True)
    return sessionmaker(bind=engine)()


class TestInternetMessageIdDedup:
    def test_finds_job_by_normalized_rfc_id(self):
        db = _session()
        now = datetime.now(timezone.utc)
        rfc = "<abc@mail.test>"
        db.add(
            JobRecord(
                job_id="job-1",
                tenant_id="TENANT_1001",
                job_type="lead",
                status="completed",
                input_data={
                    "source": {
                        "system": "gmail",
                        "message_id": "gmail-1",
                        "internet_message_id": rfc,
                    }
                },
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()

        found = JobRepository.get_by_internet_message_id(db, "TENANT_1001", "abc@mail.test")
        assert found is not None
        assert found.job_id == "job-1"

    def test_different_gmail_id_same_rfc_is_duplicate(self):
        db = _session()
        now = datetime.now(timezone.utc)
        rfc = "<shared@mail.test>"
        db.add(
            JobRecord(
                job_id="job-a",
                tenant_id="TENANT_1001",
                job_type="lead",
                status="completed",
                input_data={
                    "source": {
                        "system": "gmail",
                        "message_id": "gmail-a",
                        "internet_message_id": rfc,
                    }
                },
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        dup = JobRepository.get_by_internet_message_id(db, "TENANT_1001", rfc)
        assert dup is not None
        assert dup.job_id == "job-a"
