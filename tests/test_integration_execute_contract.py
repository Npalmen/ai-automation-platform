"""
Tests for POST /integrations/{type}/execute contract.

Covers:
  - Schema uses 'payload' field (not 'input') — contract is canonical
  - Valid google_mail execute request passes payload correctly to the adapter
  - Missing 'to' field returns 400 (not 500)
  - Missing 'subject' returns 400
  - Missing 'payload' key (empty dict default) returns 400 when adapter validates
  - Unsupported action returns 400
  - Request with 'input' key instead of 'payload' silently gets empty payload → 400

These tests call execute_integration_action directly with mocked dependencies,
following the established pattern in this repo.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.integrations.schemas import IntegrationActionRequest


# ---------------------------------------------------------------------------
# Schema contract
# ---------------------------------------------------------------------------

class TestIntegrationActionRequestSchema:
    def test_schema_field_is_payload_not_input(self):
        req = IntegrationActionRequest(action="send_email", payload={"to": "x@x.com"})
        assert req.payload == {"to": "x@x.com"}
        assert not hasattr(req, "input")

    def test_payload_defaults_to_empty_dict(self):
        req = IntegrationActionRequest(action="send_email")
        assert req.payload == {}

    def test_unknown_field_input_is_not_accepted(self):
        """Pydantic should ignore or reject 'input'; it must not be treated as payload."""
        # Pydantic v2 ignores extra fields by default — 'input' ends up discarded,
        # meaning payload stays empty. This is the root cause of the original bug.
        req = IntegrationActionRequest(action="send_email", **{"input": {"to": "x@x.com"}})
        # payload is empty because 'input' is not the schema field
        assert req.payload == {}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db():
    return MagicMock()


def _make_saved_event(tenant_id="TENANT_TEST"):
    from app.domain.integrations.models import IntegrationEvent
    from datetime import datetime, timezone
    ev = IntegrationEvent(
        tenant_id=tenant_id,
        job_id="direct",
        integration_type="google_mail",
        payload={"action": "send_email", "request": {}, "result": {}},
        status="success",
        attempts=1,
        idempotency_key="key-123",
    )
    ev.id = "evt-001"
    ev.created_at = datetime.now(timezone.utc)
    return ev


def _call_execute(action: str, payload: dict, adapter_result=None, adapter_side_effect=None):
    """Call execute_integration_action with mocked adapter and DB."""
    from app.main import execute_integration_action
    from app.integrations.enums import IntegrationType

    if adapter_result is None:
        adapter_result = {
            "status": "success",
            "integration": "google_mail",
            "provider": "google_mail",
            "action": action,
            "payload": {},
            "message": "Sent.",
            "external_id": "msg-001",
        }

    mock_adapter = MagicMock()
    if adapter_side_effect is not None:
        mock_adapter.execute_action.side_effect = adapter_side_effect
    else:
        mock_adapter.execute_action.return_value = adapter_result

    request = IntegrationActionRequest(action=action, payload=payload)
    saved = _make_saved_event()

    with patch("app.main.is_integration_enabled_for_tenant", return_value=True), \
         patch("app.main.get_integration_connection_config", return_value={}), \
         patch("app.main.get_integration_adapter", return_value=mock_adapter), \
         patch("app.repositories.postgres.integration_repository.IntegrationRepository.create", return_value=saved), \
         patch("app.domain.integrations.response_schemas.IntegrationEventResponse.model_validate", return_value=MagicMock()):
        return execute_integration_action(
            integration_type=IntegrationType.GOOGLE_MAIL,
            request=request,
            db=_mock_db(),
            tenant_id="TENANT_TEST",
        ), mock_adapter


# ---------------------------------------------------------------------------
# Valid request
# ---------------------------------------------------------------------------

class TestValidGoogleMailExecute:
    def test_valid_request_calls_adapter_with_correct_payload(self):
        payload = {"to": "test@example.com", "subject": "Test", "body": "Hello"}
        _, mock_adapter = _call_execute("send_email", payload)
        mock_adapter.execute_action.assert_called_once_with(
            action="send_email",
            payload=payload,
        )

    def test_valid_request_does_not_raise(self):
        payload = {"to": "test@example.com", "subject": "Test", "body": "Hello"}
        _call_execute("send_email", payload)  # should not raise


# ---------------------------------------------------------------------------
# Adapter ValueError → 400 (not 500)
# ---------------------------------------------------------------------------

class TestAdapterValidationErrors:
    def test_missing_to_returns_400(self):
        with pytest.raises(HTTPException) as exc_info:
            _call_execute(
                "send_email",
                {"subject": "Test", "body": "Hello"},
                adapter_side_effect=ValueError("Google Mail payload requires 'to'."),
            )
        assert exc_info.value.status_code == 400

    def test_missing_to_error_detail_is_descriptive(self):
        with pytest.raises(HTTPException) as exc_info:
            _call_execute(
                "send_email",
                {},
                adapter_side_effect=ValueError("Google Mail payload requires 'to'."),
            )
        assert "to" in exc_info.value.detail

    def test_missing_subject_returns_400(self):
        with pytest.raises(HTTPException) as exc_info:
            _call_execute(
                "send_email",
                {"to": "x@x.com"},
                adapter_side_effect=ValueError("Google Mail payload requires 'subject'."),
            )
        assert exc_info.value.status_code == 400

    def test_unsupported_action_returns_400(self):
        with pytest.raises(HTTPException) as exc_info:
            _call_execute(
                "delete_all",
                {},
                adapter_side_effect=ValueError("Unsupported Google Mail action 'delete_all'."),
            )
        assert exc_info.value.status_code == 400

    def test_empty_payload_due_to_wrong_key_returns_400(self):
        """Sending 'input' instead of 'payload' produces an empty payload dict.
        The adapter then raises ValueError('to' missing) → should be 400, not 500."""
        with pytest.raises(HTTPException) as exc_info:
            _call_execute(
                "send_email",
                {},  # empty — simulates what happens when caller sends 'input' key
                adapter_side_effect=ValueError("Google Mail payload requires 'to'."),
            )
        assert exc_info.value.status_code == 400
