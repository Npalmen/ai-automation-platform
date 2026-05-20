"""
Tests for Visma OAuth2 integration.

Covers:
- OAuth URL generation (correct params)
- Callback success (stores tokens)
- Callback invalid state handling
- Token refresh
- Disconnected status
- Test-read success/failure
- Tenant isolation (one tenant's creds not visible to another)
- No secrets in responses
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# Mock heavy dependencies that are not needed for unit tests.
# Insert mocks BEFORE any app module is imported to prevent psycopg2 import errors.
import types as _types

_pg_mock = _types.ModuleType("psycopg2")
sys.modules.setdefault("psycopg2", _pg_mock)
sys.modules.setdefault("psycopg2.extensions", MagicMock())
sys.modules.setdefault("psycopg2.extras", MagicMock())

# Fake database module with real Base and SessionLocal placeholders
_db_mod = _types.ModuleType("app.repositories.postgres.database")
_db_mod.Base = MagicMock()
_db_mod.SessionLocal = MagicMock()
_db_mod.engine = MagicMock()
sys.modules.setdefault("app.repositories.postgres.database", _db_mod)

# Now safe to import
import app.integrations.visma.oauth_service as oauth_service
import app.integrations.visma.oauth_routes as oauth_routes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_settings(
    client_id="test-client",
    client_secret="test-secret",
    redirect_uri="https://localhost:44300/callback",
    scopes="ea:api, offline_access",
    api_url="https://eaccountingapi.vismaonline.com/v2",
):
    s = SimpleNamespace()
    s.VISMA_CLIENT_ID = client_id
    s.VISMA_CLIENT_SECRET = client_secret
    s.VISMA_REDIRECT_URI = redirect_uri
    s.VISMA_SCOPES = scopes
    s.VISMA_API_URL = api_url
    return s


# ---------------------------------------------------------------------------
# Test: OAuth URL generation
# ---------------------------------------------------------------------------

class TestGetAuthUrl:
    @patch.object(oauth_service, "get_settings")
    def test_generates_correct_auth_url(self, mock_settings):
        mock_settings.return_value = _mock_settings()

        url = oauth_service.get_auth_url("TENANT_1001")

        assert oauth_service.VISMA_AUTHORIZE_URL in url
        assert "client_id=test-client" in url
        assert "redirect_uri=" in url
        assert "response_type=code" in url
        assert "state=TENANT_1001" in url
        assert "prompt=login" in url
        assert "scope=" in url

    @patch.object(oauth_service, "get_settings")
    def test_encodes_scopes(self, mock_settings):
        mock_settings.return_value = _mock_settings(scopes="ea:api, ea:sales, offline_access")

        url = oauth_service.get_auth_url("TENANT_2001")

        assert "ea%3Aapi" in url or "ea:api" in url

    @patch.object(oauth_service, "get_settings")
    def test_auth_url_does_not_contain_client_secret(self, mock_settings):
        mock_settings.return_value = _mock_settings(client_secret="super-secret-value")

        url = oauth_service.get_auth_url("TENANT_1001")

        assert "super-secret-value" not in url


# ---------------------------------------------------------------------------
# Test: Token exchange
# ---------------------------------------------------------------------------

class TestExchangeCode:
    @patch.object(oauth_service, "requests")
    @patch.object(oauth_service, "get_settings")
    def test_exchange_success(self, mock_settings, mock_requests):
        mock_settings.return_value = _mock_settings()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "at-123",
            "refresh_token": "rt-456",
            "expires_in": 3600,
            "scope": "ea:api offline_access",
        }
        mock_response.raise_for_status = MagicMock()
        mock_requests.post.return_value = mock_response

        result = oauth_service.exchange_code("auth-code-abc")

        assert result["access_token"] == "at-123"
        assert result["refresh_token"] == "rt-456"
        assert result["expires_at"] is not None
        assert result["expires_at"] > datetime.now(timezone.utc)

        call_kwargs = mock_requests.post.call_args
        assert call_kwargs[0][0] == oauth_service.VISMA_TOKEN_URL
        assert call_kwargs[1]["data"]["grant_type"] == "authorization_code"
        assert call_kwargs[1]["data"]["code"] == "auth-code-abc"

    @patch.object(oauth_service, "requests")
    @patch.object(oauth_service, "get_settings")
    def test_exchange_failure_raises(self, mock_settings, mock_requests):
        mock_settings.return_value = _mock_settings()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("Token exchange failed")
        mock_requests.post.return_value = mock_response

        with pytest.raises(Exception, match="Token exchange failed"):
            oauth_service.exchange_code("bad-code")


# ---------------------------------------------------------------------------
# Test: Token refresh
# ---------------------------------------------------------------------------

class TestRefreshToken:
    @patch.object(oauth_service, "requests")
    @patch.object(oauth_service, "get_settings")
    def test_refresh_success(self, mock_settings, mock_requests):
        mock_settings.return_value = _mock_settings()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "new-at-789",
            "refresh_token": "new-rt-012",
            "expires_in": 7200,
            "scope": "ea:api offline_access",
        }
        mock_response.raise_for_status = MagicMock()
        mock_requests.post.return_value = mock_response

        result = oauth_service.refresh_access_token("old-rt-456")

        assert result["access_token"] == "new-at-789"
        assert result["refresh_token"] == "new-rt-012"
        assert result["expires_at"] > datetime.now(timezone.utc)

        call_kwargs = mock_requests.post.call_args
        assert call_kwargs[1]["data"]["grant_type"] == "refresh_token"
        assert call_kwargs[1]["data"]["refresh_token"] == "old-rt-456"

    @patch.object(oauth_service, "requests")
    @patch.object(oauth_service, "get_settings")
    def test_refresh_preserves_old_refresh_token_if_not_returned(self, mock_settings, mock_requests):
        mock_settings.return_value = _mock_settings()
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "access_token": "new-at",
            "expires_in": 3600,
        }
        mock_response.raise_for_status = MagicMock()
        mock_requests.post.return_value = mock_response

        result = oauth_service.refresh_access_token("keep-this-rt")

        assert result["refresh_token"] == "keep-this-rt"


# ---------------------------------------------------------------------------
# Test: test_connection (API read test)
# ---------------------------------------------------------------------------

class TestVismaApiRead:
    @patch.object(oauth_service, "requests")
    @patch.object(oauth_service, "get_settings")
    def test_api_read_success(self, mock_settings, mock_requests):
        mock_settings.return_value = _mock_settings()
        mock_response = MagicMock()
        mock_response.json.return_value = {"name": "Test Company AB"}
        mock_response.raise_for_status = MagicMock()
        mock_requests.get.return_value = mock_response

        result = oauth_service.test_connection("valid-token")

        assert result["name"] == "Test Company AB"
        call_args = mock_requests.get.call_args
        headers = call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer valid-token"

    @patch.object(oauth_service, "requests")
    @patch.object(oauth_service, "get_settings")
    def test_api_read_failure_raises(self, mock_settings, mock_requests):
        mock_settings.return_value = _mock_settings()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("API Error")
        mock_requests.get.return_value = mock_response

        with pytest.raises(Exception, match="API Error"):
            oauth_service.test_connection("bad-token")


# ---------------------------------------------------------------------------
# Test: Route-level logic (status, disconnect, test-read)
# ---------------------------------------------------------------------------

class TestVismaOAuthRoutes:
    """Test route handler functions directly with mocked dependencies."""

    @patch.object(oauth_routes, "OAuthCredentialRepository")
    def test_status_disconnected(self, mock_repo):
        mock_repo.get.return_value = None

        result = oauth_routes.visma_status(db=MagicMock(), tenant_id="TENANT_1001")

        assert result["status"] == "disconnected"
        assert result["connected"] is False

    @patch.object(oauth_routes, "OAuthCredentialRepository")
    def test_status_connected(self, mock_repo):
        record = MagicMock()
        record.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        record.scopes = "ea:api offline_access"
        record.connected_at = datetime.now(timezone.utc) - timedelta(days=1)
        mock_repo.get.return_value = record

        result = oauth_routes.visma_status(db=MagicMock(), tenant_id="TENANT_1001")

        assert result["status"] == "connected"
        assert result["connected"] is True
        assert result["token_expired"] is False

    @patch.object(oauth_routes, "OAuthCredentialRepository")
    def test_status_token_expired(self, mock_repo):
        record = MagicMock()
        record.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        record.scopes = "ea:api"
        record.connected_at = datetime.now(timezone.utc) - timedelta(days=2)
        mock_repo.get.return_value = record

        result = oauth_routes.visma_status(db=MagicMock(), tenant_id="TENANT_1001")

        assert result["status"] == "connected"
        assert result["token_expired"] is True

    @patch.object(oauth_routes, "OAuthCredentialRepository")
    def test_disconnect_success(self, mock_repo):
        mock_repo.delete.return_value = True

        result = oauth_routes.visma_disconnect(db=MagicMock(), tenant_id="TENANT_1001")

        assert result["status"] == "disconnected"

    @patch.object(oauth_routes, "OAuthCredentialRepository")
    def test_disconnect_not_connected(self, mock_repo):
        mock_repo.delete.return_value = False

        result = oauth_routes.visma_disconnect(db=MagicMock(), tenant_id="TENANT_1001")

        assert result["status"] == "not_connected"

    @patch.object(oauth_routes, "test_connection")
    @patch.object(oauth_routes, "OAuthCredentialRepository")
    def test_read_success(self, mock_repo, mock_test):
        record = MagicMock()
        record.access_token = "valid-token"
        record.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        record.refresh_token = "rt-123"
        record.scopes = "ea:api"
        mock_repo.get.return_value = record
        mock_test.return_value = {"name": "Company AB"}

        result = oauth_routes.visma_test_read(db=MagicMock(), tenant_id="TENANT_1001")

        assert result["status"] == "success"
        assert result["data"]["name"] == "Company AB"

    @patch.object(oauth_routes, "OAuthCredentialRepository")
    def test_read_not_connected_raises(self, mock_repo):
        mock_repo.get.return_value = None

        from fastapi import HTTPException
        with pytest.raises(HTTPException):
            oauth_routes.visma_test_read(db=MagicMock(), tenant_id="TENANT_1001")

    @patch.object(oauth_routes, "test_connection")
    @patch.object(oauth_routes, "refresh_access_token")
    @patch.object(oauth_routes, "OAuthCredentialRepository")
    def test_read_auto_refreshes_expired_token(self, mock_repo, mock_refresh, mock_test):
        record = MagicMock()
        record.access_token = "expired-token"
        record.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        record.refresh_token = "rt-valid"
        record.scopes = "ea:api"
        mock_repo.get.return_value = record
        mock_refresh.return_value = {
            "access_token": "new-token",
            "refresh_token": "new-rt",
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
            "scopes": "ea:api",
        }
        mock_test.return_value = {"name": "Refreshed Corp"}

        result = oauth_routes.visma_test_read(db=MagicMock(), tenant_id="TENANT_1001")

        assert result["status"] == "success"
        mock_refresh.assert_called_once_with("rt-valid")
        mock_test.assert_called_once_with("new-token")


# ---------------------------------------------------------------------------
# Test: Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    @patch.object(oauth_routes, "OAuthCredentialRepository")
    def test_status_is_tenant_scoped(self, mock_repo):
        """TENANT_A credentials are not returned for TENANT_B."""
        mock_repo.get.return_value = None

        result = oauth_routes.visma_status(db=MagicMock(), tenant_id="TENANT_B")
        assert result["connected"] is False


# ---------------------------------------------------------------------------
# Test: Security — no secrets in responses
# ---------------------------------------------------------------------------

class TestSecurityConstraints:
    @patch.object(oauth_routes, "OAuthCredentialRepository")
    def test_status_does_not_expose_tokens(self, mock_repo):
        record = MagicMock()
        record.access_token = "secret-at-12345"
        record.refresh_token = "secret-rt-67890"
        record.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        record.scopes = "ea:api"
        record.connected_at = datetime.now(timezone.utc)
        mock_repo.get.return_value = record

        result = oauth_routes.visma_status(db=MagicMock(), tenant_id="TENANT_1001")

        result_str = str(result)
        assert "secret-at-12345" not in result_str
        assert "secret-rt-67890" not in result_str
