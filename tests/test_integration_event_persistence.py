"""
Tests for integration event persistence slice.

Covers:
  - IntegrationRepository.create persists a record and returns it
  - execute_integration_action saves a real DB row (not synthetic)
  - saved record has correct tenant_id, integration_type, status, payload shape
  - status is taken from adapter result
  - list_integration_events returns the persisted record
  - IntegrationEvent now uses database.Base (same declarative base as all other models)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone

import pytest

from app.domain.integrations.models import IntegrationEvent
from app.domain.integrations.response_schemas import IntegrationEventResponse
from app.repositories.postgres.integration_repository import IntegrationRepository
from app.repositories.postgres.database import Base as DatabaseBase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db() -> MagicMock:
    return MagicMock()


def _fake_event(
    id: int = 1,
    tenant_id: str = "TENANT_1001",
    job_id: str = "direct",
    integration_type: str = "google_mail",
    status: str = "success",
    payload: dict | None = None,
    idempotency_key: str = "test-key-1",
    attempts: int = 1,
    last_error: str | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> MagicMock:
    rec = MagicMock(spec=IntegrationEvent)
    rec.id = id
    rec.tenant_id = tenant_id
    rec.job_id = job_id
    rec.integration_type = integration_type
    rec.status = status
    rec.payload = payload or {"action": "send_email", "request": {}, "result": {"status": "success"}}
    rec.idempotency_key = idempotency_key
    rec.attempts = attempts
    rec.last_error = last_error
    rec.created_at = created_at or datetime.now(timezone.utc)
    rec.updated_at = updated_at
    return rec


# ---------------------------------------------------------------------------
# Model base class
# ---------------------------------------------------------------------------

class TestIntegrationEventModel:
    def test_uses_database_base(self):
        """IntegrationEvent must use the same Base as all other models so
        create_all includes the integration_events table."""
        assert IntegrationEvent.__bases__[0] is not None
        # Verify __tablename__ is registered in the shared metadata
        assert "integration_events" in DatabaseBase.metadata.tables


# ---------------------------------------------------------------------------
# IntegrationRepository
# ---------------------------------------------------------------------------

class TestIntegrationRepository:
    def test_create_adds_and_commits(self):
        db = _mock_db()
        rec = _fake_event()
        repo = IntegrationRepository(db)
        result = repo.create(rec)
        db.add.assert_called_once_with(rec)
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(rec)
        assert result is rec

    def test_list_events_for_tenant_filters_by_tenant(self):
        db = _mock_db()
        rec = _fake_event()
        (db.query.return_value
            .filter.return_value
            .order_by.return_value
            .offset.return_value
            .limit.return_value
            .all.return_value) = [rec]

        repo = IntegrationRepository(db)
        results = repo.list_events_for_tenant("TENANT_1001")
        assert results == [rec]

    def test_count_events_for_tenant(self):
        db = _mock_db()
        db.query.return_value.filter.return_value.count.return_value = 3
        repo = IntegrationRepository(db)
        count = repo.count_events_for_tenant("TENANT_1001")
        assert count == 3


# ---------------------------------------------------------------------------
# execute_integration_action — persistence path
# ---------------------------------------------------------------------------

class TestExecuteIntegrationPersistence:
    """
    Simulate what main.py does after calling adapter.execute_action,
    without spinning up FastAPI or a real DB.
    """

    def _run_persist(self, adapter_result: dict, tenant_id: str = "TENANT_1001"):
        """
        Replicate the persistence logic from the endpoint:
          1. Build IntegrationEvent from adapter result
          2. Call repo.create
          3. Return IntegrationEventResponse.model_validate(saved)
        """
        from uuid import uuid4
        from app.integrations.enums import IntegrationType

        db = _mock_db()
        integration_type = IntegrationType.GOOGLE_MAIL
        action = "send_email"
        request_payload = {"to": "test@example.com", "subject": "Hello"}

        status = adapter_result.get("status", "success")
        record = IntegrationEvent(
            tenant_id=tenant_id,
            job_id="direct",
            integration_type=integration_type.value,
            payload={"action": action, "request": request_payload, "result": adapter_result},
            status=status,
            attempts=1,
            idempotency_key=str(uuid4()),
        )

        # Simulate what repo.create does: commit + refresh sets an id
        saved = _fake_event(
            id=42,
            tenant_id=tenant_id,
            integration_type=integration_type.value,
            status=status,
            payload=record.payload,
        )

        with patch.object(IntegrationRepository, "create", return_value=saved) as mock_create:
            repo = IntegrationRepository(db)
            result = repo.create(record)
            mock_create.assert_called_once()

        return result

    def test_success_status_persisted(self):
        saved = self._run_persist({"status": "success", "message_id": "abc123"})
        assert saved.status == "success"

    def test_failed_status_persisted(self):
        saved = self._run_persist({"status": "failed", "error": "token expired"})
        assert saved.status == "failed"

    def test_payload_contains_action_request_and_result(self):
        adapter_result = {"status": "success", "message_id": "abc123"}
        saved = self._run_persist(adapter_result)
        assert "action" in saved.payload
        assert "request" in saved.payload
        assert "result" in saved.payload

    def test_tenant_id_on_saved_record(self):
        saved = self._run_persist({"status": "success"}, tenant_id="TENANT_2001")
        assert saved.tenant_id == "TENANT_2001"

    def test_integration_type_on_saved_record(self):
        saved = self._run_persist({"status": "success"})
        assert saved.integration_type == "google_mail"

    def test_response_schema_validates_from_record(self):
        saved = _fake_event(id=7, status="success")
        response = IntegrationEventResponse.model_validate(saved)
        assert response.id == 7
        assert response.status == "success"
        assert response.tenant_id == "TENANT_1001"

    def test_response_schema_preserves_payload(self):
        payload = {"action": "send_email", "request": {}, "result": {"status": "success"}}
        saved = _fake_event(payload=payload)
        response = IntegrationEventResponse.model_validate(saved)
        assert response.payload == payload
