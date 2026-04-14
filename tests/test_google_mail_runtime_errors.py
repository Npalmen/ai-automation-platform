"""
Tests for Google Mail runtime error handling and config diagnostics.

Covers:
  - RuntimeError from token refresh propagates as 503 (not 500) from the route
  - RuntimeError from Gmail send failure propagates as 503
  - ValueError (bad payload) still returns 400
  - _log_config_diagnostics warns when refresh credentials are incomplete
  - _mask helper never returns the full token value
  - Adapter logs diagnostics on execute_action
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch, call

import pytest
from fastapi import HTTPException

from app.integrations.schemas import IntegrationActionRequest
from app.integrations.google.adapter import GoogleMailAdapter, _mask


# ---------------------------------------------------------------------------
# _mask helper
# ---------------------------------------------------------------------------

class TestMaskHelper:
    def test_empty_string_returns_not_set(self):
        assert _mask("") == "<not set>"

    def test_none_equivalent_empty_returns_not_set(self):
        # _mask expects str; empty string covers the None case after str() cast
        assert _mask("") == "<not set>"

    def test_long_value_is_truncated(self):
        result = _mask("ya29.abcdefghij1234567890")
        assert result.startswith("ya29.abc")
        assert result.endswith("...")
        assert "abcdefghij1234567890" not in result

    def test_short_value_does_not_reveal_content(self):
        result = _mask("abc", prefix_len=8)
        assert result == "<set, short>"

    def test_prefix_len_respected(self):
        result = _mask("0123456789abcdef", prefix_len=4)
        assert result == "0123..."
        assert "56789abcdef" not in result


# ---------------------------------------------------------------------------
# Config diagnostics logging
# ---------------------------------------------------------------------------

class TestConfigDiagnostics:
    def _adapter(self, access_token="", refresh_token="", client_id="", client_secret=""):
        return GoogleMailAdapter(connection_config={
            "api_url": "https://gmail.googleapis.com/gmail/v1",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
            "user_id": "me",
        })

    def test_logs_access_token_presence(self, caplog):
        adapter = self._adapter(access_token="ya29.token")
        with caplog.at_level(logging.INFO, logger="app.integrations.google.adapter"):
            adapter._log_config_diagnostics()
        assert "access_token" in caplog.text
        assert "ya29.tok" in caplog.text  # prefix only
        assert "ya29.token" not in caplog.text  # full value never logged

    def test_warns_when_partial_refresh_credentials(self, caplog):
        # Only refresh_token set — client_id and client_secret missing
        adapter = self._adapter(refresh_token="1//0gRefreshToken", client_id="", client_secret="")
        with caplog.at_level(logging.WARNING, logger="app.integrations.google.adapter"):
            adapter._log_config_diagnostics()
        assert "1 of 3" in caplog.text
        assert "Token refresh will fail" in caplog.text
        assert "invalid_grant" in caplog.text

    def test_no_warning_when_no_refresh_credentials(self, caplog):
        # All refresh fields absent — this is the "access token only" mode, no warning needed
        adapter = self._adapter(access_token="ya29.token")
        with caplog.at_level(logging.WARNING, logger="app.integrations.google.adapter"):
            adapter._log_config_diagnostics()
        assert "invalid_grant" not in caplog.text

    def test_no_warning_when_all_refresh_credentials_set(self, caplog):
        adapter = self._adapter(
            refresh_token="1//0g", client_id="client-id", client_secret="secret"
        )
        with caplog.at_level(logging.WARNING, logger="app.integrations.google.adapter"):
            adapter._log_config_diagnostics()
        assert "invalid_grant" not in caplog.text

    def test_diagnostics_called_on_execute_action(self, caplog):
        adapter = self._adapter(access_token="ya29.token")
        with caplog.at_level(logging.INFO, logger="app.integrations.google.adapter"), \
             patch.object(adapter.client, "send_message", return_value={
                 "status": "success", "provider": "google_mail",
                 "message": "Sent.", "external_id": "id1",
                 "payload": {},
             }):
            adapter.execute_action("send_email", {"to": "x@x.com", "subject": "S", "body": "B"})
        assert "OAuth config diagnostics" in caplog.text


# ---------------------------------------------------------------------------
# Route: RuntimeError → 503
# ---------------------------------------------------------------------------

def _mock_db():
    return MagicMock()


def _make_saved_event():
    from app.domain.integrations.models import IntegrationEvent
    from datetime import datetime, timezone
    ev = IntegrationEvent(
        tenant_id="TENANT_TEST", job_id="direct",
        integration_type="google_mail",
        payload={}, status="success", attempts=1, idempotency_key="k",
    )
    ev.id = "evt-001"
    ev.created_at = datetime.now(timezone.utc)
    return ev


def _call_route(action: str, payload: dict, adapter_side_effect):
    from app.main import execute_integration_action
    from app.integrations.enums import IntegrationType

    mock_adapter = MagicMock()
    mock_adapter.execute_action.side_effect = adapter_side_effect
    request = IntegrationActionRequest(action=action, payload=payload)

    with patch("app.main.is_integration_enabled_for_tenant", return_value=True), \
         patch("app.main.get_integration_connection_config", return_value={}), \
         patch("app.main.get_integration_adapter", return_value=mock_adapter):
        return execute_integration_action(
            integration_type=IntegrationType.GOOGLE_MAIL,
            request=request,
            db=_mock_db(),
            tenant_id="TENANT_TEST",
        )


class TestRouteRuntimeErrors:
    def test_token_refresh_failure_returns_503(self):
        with pytest.raises(HTTPException) as exc_info:
            _call_route(
                "send_email",
                {"to": "x@x.com", "subject": "S", "body": "B"},
                adapter_side_effect=RuntimeError(
                    "Gmail token refresh failed (400): {\"error\": \"invalid_grant\"}"
                ),
            )
        assert exc_info.value.status_code == 503

    def test_token_refresh_failure_detail_is_descriptive(self):
        with pytest.raises(HTTPException) as exc_info:
            _call_route(
                "send_email",
                {"to": "x@x.com", "subject": "S", "body": "B"},
                adapter_side_effect=RuntimeError(
                    "Gmail token refresh failed (400): {\"error\": \"invalid_grant\"}"
                ),
            )
        assert "invalid_grant" in exc_info.value.detail

    def test_gmail_send_failure_returns_503(self):
        with pytest.raises(HTTPException) as exc_info:
            _call_route(
                "send_email",
                {"to": "x@x.com", "subject": "S", "body": "B"},
                adapter_side_effect=RuntimeError(
                    "Google Mail unauthorized. The access token is invalid."
                ),
            )
        assert exc_info.value.status_code == 503

    def test_gmail_403_returns_503(self):
        with pytest.raises(HTTPException) as exc_info:
            _call_route(
                "send_email",
                {"to": "x@x.com", "subject": "S", "body": "B"},
                adapter_side_effect=RuntimeError(
                    "Google Mail forbidden. The token likely lacks permission."
                ),
            )
        assert exc_info.value.status_code == 503

    def test_value_error_still_returns_400(self):
        """ValueError (bad payload) must remain a 400, not 503."""
        with pytest.raises(HTTPException) as exc_info:
            _call_route(
                "send_email",
                {},
                adapter_side_effect=ValueError("Google Mail payload requires 'to'."),
            )
        assert exc_info.value.status_code == 400
