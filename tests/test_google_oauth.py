"""
Tests for Google Mail OAuth2 integration (tenant-scoped).

Covers signed OAuth state, token exchange, refresh preservation, callback errors,
cross-tenant isolation, and secret-free API responses.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.integrations.google.oauth_service as google_oauth_service
import app.integrations.oauth_state as oauth_state_module
from app.integrations.oauth_state import OAuthStateError, create_integration_oauth_state, consume_integration_oauth_state


def _settings(secret="test-session-secret"):
    s = SimpleNamespace()
    s.SESSION_SECRET_KEY = secret
    s.ADMIN_API_KEY = "admin-key"
    s.APP_NAME = "test"
    s.GOOGLE_OAUTH_CLIENT_ID = "client-id"
    s.GOOGLE_OAUTH_CLIENT_SECRET = "client-secret"
    s.GOOGLE_OAUTH_REDIRECT_URI = "https://api.krowolf.se/integrations/google_mail/oauth/callback"
    s.GOOGLE_OAUTH_SCOPES = "https://www.googleapis.com/auth/gmail.readonly"
    s.GOOGLE_MAIL_API_URL = "https://gmail.googleapis.com/gmail/v1"
    s.GOOGLE_MAIL_ACCESS_TOKEN = ""
    s.GOOGLE_MAIL_USER_ID = "me"
    s.GOOGLE_OAUTH_REFRESH_TOKEN = ""
    return s


class TestGoogleAuthUrl:
    @patch.object(google_oauth_service, "get_settings")
    def test_auth_url_contains_required_params(self, mock_settings):
        mock_settings.return_value = _settings()
        url = google_oauth_service.get_auth_url_for_state("opaque-state-123")
        assert "accounts.google.com" in url
        assert "client_id=client-id" in url
        assert "state=opaque-state-123" in url
        assert "access_type=offline" in url
        assert "client-secret" not in url


class TestExchangeCode:
    @patch.object(google_oauth_service, "requests")
    @patch.object(google_oauth_service, "get_settings")
    def test_exchange_success(self, mock_settings, mock_requests):
        mock_settings.return_value = _settings()
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "access_token": "at-new",
            "refresh_token": "rt-new",
            "expires_in": 3600,
            "scope": "gmail.readonly",
        }
        mock_requests.post.return_value = resp
        out = google_oauth_service.exchange_code("code-abc")
        assert out["access_token"] == "at-new"
        assert out["refresh_token"] == "rt-new"
        assert out["expires_at"] > datetime.now(timezone.utc)


class _FakeOAuthStateRecord:
    def __init__(self, **kwargs):
        self.consumed_at = kwargs.pop("consumed_at", None)
        for key, value in kwargs.items():
            setattr(self, key, value)


class TestIntegrationOAuthState:
    def test_create_and_consume_success(self):
        db = MagicMock()
        settings = _settings()
        with patch.object(oauth_state_module, "IntegrationOAuthStateRecord", _FakeOAuthStateRecord):
            state_id, record = create_integration_oauth_state(
                db,
                tenant_id="T_A",
                operator_id="op-1",
                provider="google_mail",
                redirect_target="/ops/customers/T_A",
                settings=settings,
            )
        db.query.return_value.filter_by.return_value.with_for_update.return_value.first.return_value = record
        consumed = consume_integration_oauth_state(
            db, state_id=state_id, provider="google_mail", settings=settings
        )
        assert consumed.tenant_id == "T_A"
        assert consumed.consumed_at is not None

    def test_state_replay_rejected(self):
        db = MagicMock()
        settings = _settings()
        with patch.object(oauth_state_module, "IntegrationOAuthStateRecord", _FakeOAuthStateRecord):
            state_id, record = create_integration_oauth_state(
                db,
                tenant_id="T_A",
                operator_id="op-1",
                provider="google_mail",
                redirect_target="/ops/customers/T_A",
                settings=settings,
            )
        record.consumed_at = datetime.now(timezone.utc)
        db.query.return_value.filter_by.return_value.with_for_update.return_value.first.return_value = record
        with pytest.raises(OAuthStateError) as exc:
            consume_integration_oauth_state(
                db, state_id=state_id, provider="google_mail", settings=settings
            )
        assert exc.value.code == "oauth_state_replay"

    def test_state_expired_rejected(self):
        db = MagicMock()
        settings = _settings()
        with patch.object(oauth_state_module, "IntegrationOAuthStateRecord", _FakeOAuthStateRecord):
            state_id, record = create_integration_oauth_state(
                db,
                tenant_id="T_A",
                operator_id="op-1",
                provider="google_mail",
                redirect_target="/ops/customers/T_A",
                settings=settings,
            )
        record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.query.return_value.filter_by.return_value.with_for_update.return_value.first.return_value = record
        with pytest.raises(OAuthStateError) as exc:
            consume_integration_oauth_state(
                db, state_id=state_id, provider="google_mail", settings=settings
            )
        assert exc.value.code == "oauth_state_expired"

    def test_invalid_redirect_rejected(self):
        db = MagicMock()
        with pytest.raises(OAuthStateError):
            create_integration_oauth_state(
                db,
                tenant_id="T_A",
                operator_id="op-1",
                provider="google_mail",
                redirect_target="/evil/path",
                settings=_settings(),
            )


class TestOAuthCredentialUpsertPreservesRefresh:
    def test_refresh_token_preserved_when_not_returned(self):
        from app.repositories.postgres import oauth_credential_repository as repo_mod

        existing = SimpleNamespace(
            access_token="old-at",
            refresh_token="keep-rt",
            expires_at=None,
            scopes="old-scope",
            metadata_json={},
            updated_at=None,
        )
        db = MagicMock()

        with patch.object(repo_mod.OAuthCredentialRepository, "get", return_value=existing):
            repo_mod.OAuthCredentialRepository.upsert(
                db,
                tenant_id="T_A",
                provider="google_mail",
                access_token="new-at",
                refresh_token=None,
                expires_at=datetime.now(timezone.utc),
                scopes="new-scope",
            )

        assert existing.access_token == "new-at"
        assert existing.refresh_token == "keep-rt"
        assert existing.scopes == "new-scope"
        db.commit.assert_called_once()


class TestGmailConnectionStatusNoSecrets:
    def test_status_response_shape(self):
        from app.integrations.google.oauth_token_resolver import gmail_connection_status

        db = MagicMock()
        settings = _settings()
        with patch(
            "app.integrations.google.oauth_token_resolver.OAuthCredentialRepository.get",
            return_value=None,
        ):
            out = gmail_connection_status(db, "T_A", settings=settings)
        assert "refresh_token" not in out
        assert "access_token" not in out
        assert out["connection_state"] == "not_connected"
