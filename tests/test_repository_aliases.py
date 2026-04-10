"""
Tests for the repository alias methods added to make main.py read endpoints work.

Verifies:
  JobRepository.list_jobs       — alias for list_jobs_for_tenant, returns domain Jobs
  JobRepository.count_jobs      — alias for count_jobs_for_tenant
  AuditRepository.list_events   — alias for list_events_for_tenant
  AuditRepository.count_events  — alias for count_events_for_tenant
  IntegrationRepository.list_events  — static alias wrapping instance method
  IntegrationRepository.count_events — static alias wrapping instance method

All tests use MagicMock to avoid any real DB connection.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, call
import pytest

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job


# ---------------------------------------------------------------------------
# Helpers: build fake ORM records without SQLAlchemy
# ---------------------------------------------------------------------------

def _fake_job_record(
    *,
    job_id: str = "job-1",
    tenant_id: str = "TENANT_1001",
    job_type: str = "lead",
    status: str = "completed",
) -> MagicMock:
    now = datetime.now(timezone.utc)
    rec = MagicMock()
    rec.job_id = job_id
    rec.tenant_id = tenant_id
    rec.job_type = job_type
    rec.status = status
    rec.input_data = {"subject": "Test"}
    rec.result = {"processor_history": []}
    rec.created_at = now
    rec.updated_at = now
    return rec


def _fake_audit_record(event_id: str = "evt-1", tenant_id: str = "TENANT_1001") -> MagicMock:
    now = datetime.now(timezone.utc)
    rec = MagicMock()
    rec.event_id = event_id
    rec.tenant_id = tenant_id
    rec.category = "workflow"
    rec.action = "job_created"
    rec.status = "success"
    rec.details = {}
    rec.created_at = now
    return rec


# ---------------------------------------------------------------------------
# JobRepository aliases
# ---------------------------------------------------------------------------

class TestJobRepositoryAliases:
    def test_list_jobs_delegates_to_list_jobs_for_tenant(self):
        from app.repositories.postgres.job_repository import JobRepository

        fake_records = [_fake_job_record(job_id="a"), _fake_job_record(job_id="b")]
        db = MagicMock()

        with patch.object(
            JobRepository, "list_jobs_for_tenant", return_value=fake_records
        ) as mock_list:
            result = JobRepository.list_jobs(db, tenant_id="TENANT_1001", limit=10, offset=0)

        mock_list.assert_called_once_with(
            db, "TENANT_1001", limit=10, offset=0, job_type=None, status=None
        )
        assert len(result) == 2
        # Returns domain Job objects, not raw records
        assert all(isinstance(j, Job) for j in result)
        assert result[0].job_id == "a"
        assert result[1].job_id == "b"

    def test_list_jobs_passes_filters(self):
        from app.repositories.postgres.job_repository import JobRepository

        db = MagicMock()
        with patch.object(JobRepository, "list_jobs_for_tenant", return_value=[]) as mock_list:
            JobRepository.list_jobs(
                db, tenant_id="T1", limit=5, offset=2, job_type="lead", status="completed"
            )

        mock_list.assert_called_once_with(
            db, "T1", limit=5, offset=2, job_type="lead", status="completed"
        )

    def test_count_jobs_delegates_to_count_jobs_for_tenant(self):
        from app.repositories.postgres.job_repository import JobRepository

        db = MagicMock()
        with patch.object(
            JobRepository, "count_jobs_for_tenant", return_value=42
        ) as mock_count:
            result = JobRepository.count_jobs(db, tenant_id="TENANT_1001")

        mock_count.assert_called_once_with(db, "TENANT_1001", job_type=None, status=None)
        assert result == 42

    def test_count_jobs_passes_filters(self):
        from app.repositories.postgres.job_repository import JobRepository

        db = MagicMock()
        with patch.object(
            JobRepository, "count_jobs_for_tenant", return_value=7
        ) as mock_count:
            result = JobRepository.count_jobs(db, tenant_id="T1", job_type="invoice", status="failed")

        mock_count.assert_called_once_with(db, "T1", job_type="invoice", status="failed")
        assert result == 7


# ---------------------------------------------------------------------------
# AuditRepository aliases
# ---------------------------------------------------------------------------

class TestAuditRepositoryAliases:
    def test_list_events_delegates_to_list_events_for_tenant(self):
        from app.repositories.postgres.audit_repository import AuditRepository

        fake_records = [_fake_audit_record("e1"), _fake_audit_record("e2")]
        db = MagicMock()

        with patch.object(
            AuditRepository, "list_events_for_tenant", return_value=fake_records
        ) as mock_list:
            result = AuditRepository.list_events(db, tenant_id="TENANT_1001", limit=50, offset=0)

        mock_list.assert_called_once_with(db, "TENANT_1001", limit=50, offset=0)
        assert result == fake_records

    def test_count_events_delegates_to_count_events_for_tenant(self):
        from app.repositories.postgres.audit_repository import AuditRepository

        db = MagicMock()
        with patch.object(
            AuditRepository, "count_events_for_tenant", return_value=17
        ) as mock_count:
            result = AuditRepository.count_events(db, tenant_id="TENANT_1001")

        mock_count.assert_called_once_with(db, "TENANT_1001")
        assert result == 17


# ---------------------------------------------------------------------------
# IntegrationRepository static aliases
# ---------------------------------------------------------------------------

class TestIntegrationRepositoryStaticAliases:
    def test_list_events_is_callable_as_static(self):
        """list_events(db, tenant_id, ...) must not require an instance."""
        from app.repositories.postgres.integration_repository import IntegrationRepository

        db = MagicMock()
        fake_results = [MagicMock(), MagicMock()]

        with patch.object(
            IntegrationRepository, "list_events_for_tenant", return_value=fake_results
        ) as mock_list:
            result = IntegrationRepository.list_events(db, tenant_id="T1", limit=10, offset=0)

        assert result == fake_results
        # The instance method was invoked (once, on the temporary instance)
        mock_list.assert_called_once_with(tenant_id="T1", limit=10, offset=0)

    def test_count_events_is_callable_as_static(self):
        from app.repositories.postgres.integration_repository import IntegrationRepository

        db = MagicMock()
        with patch.object(
            IntegrationRepository, "count_events_for_tenant", return_value=3
        ) as mock_count:
            result = IntegrationRepository.count_events(db, tenant_id="T1")

        assert result == 3
        mock_count.assert_called_once_with(tenant_id="T1")


# ---------------------------------------------------------------------------
# Regression: JobRepository._to_domain converts records correctly
# ---------------------------------------------------------------------------

class TestJobRepositoryToDomain:
    def test_to_domain_extracts_processor_history_from_result(self):
        from app.repositories.postgres.job_repository import JobRepository

        now = datetime.now(timezone.utc)
        rec = MagicMock()
        rec.job_id = "job-99"
        rec.tenant_id = "TENANT_1001"
        rec.job_type = "lead"
        rec.status = "completed"
        rec.input_data = {"x": 1}
        rec.result = {
            "status": "completed",
            "payload": {"key": "val"},
            "processor_history": [{"processor": "classification_processor", "result": {}}],
        }
        rec.created_at = now
        rec.updated_at = now

        job = JobRepository._to_domain(rec)

        assert job.job_id == "job-99"
        assert job.job_type == JobType.LEAD
        assert len(job.processor_history) == 1
        # processor_history must NOT appear inside job.result
        assert "processor_history" not in (job.result or {})

    def test_to_domain_handles_empty_result(self):
        from app.repositories.postgres.job_repository import JobRepository

        now = datetime.now(timezone.utc)
        rec = MagicMock()
        rec.job_id = "job-0"
        rec.tenant_id = "T"
        rec.job_type = "intake"
        rec.status = "pending"
        rec.input_data = {}
        rec.result = None
        rec.created_at = now
        rec.updated_at = now

        job = JobRepository._to_domain(rec)

        assert job.processor_history == []
        assert job.result == {}


# ---------------------------------------------------------------------------
# Response schema shape: list endpoints use {items, total}
# ---------------------------------------------------------------------------

class TestListResponseSchemaShapes:
    """
    Regression: all list response schemas must use {items, total}
    matching what main.py actually constructs.
    Previously AuditEventListResponse used {events, tenant_id, limit, offset}
    and IntegrationEventListResponse used {events, ...} — both caused 500s.
    """

    def test_audit_event_list_response_accepts_items_and_total(self):
        from app.core.audit_list_response_schemas import AuditEventListResponse

        resp = AuditEventListResponse(items=[], total=0)
        assert resp.items == []
        assert resp.total == 0

    def test_audit_event_list_response_has_no_events_field(self):
        from app.core.audit_list_response_schemas import AuditEventListResponse

        assert not hasattr(AuditEventListResponse.model_fields, "events"), (
            "AuditEventListResponse must use 'items', not 'events'"
        )
        assert "events" not in AuditEventListResponse.model_fields

    def test_audit_event_list_response_has_no_legacy_fields(self):
        from app.core.audit_list_response_schemas import AuditEventListResponse

        fields = AuditEventListResponse.model_fields
        for legacy in ("tenant_id", "limit", "offset", "events"):
            assert legacy not in fields, f"Unexpected legacy field '{legacy}' in AuditEventListResponse"

    def test_integration_event_list_response_accepts_items_and_total(self):
        from app.domain.integrations.response_schemas import IntegrationEventListResponse

        resp = IntegrationEventListResponse(items=[], total=0)
        assert resp.items == []
        assert resp.total == 0

    def test_integration_event_list_response_has_no_events_field(self):
        from app.domain.integrations.response_schemas import IntegrationEventListResponse

        assert "events" not in IntegrationEventListResponse.model_fields

    def test_audit_event_response_serializes_from_orm_record(self):
        """AuditEventResponse must deserialize from an ORM-like object (from_attributes)."""
        from app.core.audit_response_schemas import AuditEventResponse

        now = datetime.now(timezone.utc)
        rec = MagicMock()
        rec.event_id = "evt-42"
        rec.tenant_id = "TENANT_1001"
        rec.category = "workflow"
        rec.action = "job_created"
        rec.status = "success"
        rec.details = {"job_id": "job-1"}
        rec.created_at = now

        resp = AuditEventResponse.model_validate(rec, from_attributes=True)
        assert resp.event_id == "evt-42"
        assert resp.action == "job_created"
        assert resp.details == {"job_id": "job-1"}
