"""
Tests for Google OAuth callback state routing (state_invalid root-cause fix).

Verifies integration-panel states route to integration_oauth_states, not
onboarding heuristic. Callback must work without admin session cookie.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.integrations.oauth_state_resolver import lookup_oauth_state_source


def _settings():
    return SimpleNamespace(
        SESSION_SECRET_KEY="callback-test-secret",
        ADMIN_API_KEY="admin-key",
        APP_NAME="test",
        GOOGLE_OAUTH_CLIENT_ID="client-id",
        GOOGLE_OAUTH_CLIENT_SECRET="client-secret",
        GOOGLE_OAUTH_REDIRECT_URI="https://api.krowolf.se/integrations/google_mail/oauth/callback",
        GOOGLE_OAUTH_SCOPES="https://www.googleapis.com/auth/gmail.readonly",
        GOOGLE_MAIL_API_URL="https://gmail.googleapis.com/gmail/v1",
    )


class _FakeIntegrationState:
    def __init__(self, **kwargs):
        self.consumed_at = kwargs.pop("consumed_at", None)
        for k, v in kwargs.items():
            setattr(self, k, v)


class TestLookupOAuthStateSource:
    def test_integration_state_found(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.side_effect = [
            object(),  # integration hit
        ]
        assert lookup_oauth_state_source(db, "opaque-integration-state-id-32charsxx") == "integration"

    def test_onboarding_state_found_when_not_integration(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.side_effect = [
            None,
            object(),
        ]
        assert lookup_oauth_state_source(db, "opaque-onboarding-state-id-32charsxxx") == "onboarding"

    def test_unknown_state(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None
        assert lookup_oauth_state_source(db, "missing-state") is None


class TestCallbackWithoutSessionCookie:
    def test_integration_state_reaches_consume_not_onboarding(self):
        """Regression: opaque integration state must not hit onboarding consumer."""
        from app.api.dependencies import get_db
        from app.core.settings import get_settings
        from app.main import app

        settings = _settings()
        expires = datetime.now(timezone.utc) + timedelta(minutes=10)
        record = _FakeIntegrationState(
            state_id="opaque-integration-state-id-32charsxx",
            state_hash="will-be-recomputed",
            tenant_id="T_NIKLAS_DEMO_001",
            operator_id="op-1",
            provider="google_mail",
            redirect_target="/ops/customers/T_NIKLAS_DEMO_001",
            expires_at=expires,
        )

        mock_db = MagicMock()

        def _db():
            yield mock_db

        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_settings] = lambda: settings

        with (
            patch(
                "app.integrations.google.oauth_routes.lookup_oauth_state_source",
                return_value="integration",
            ),
            patch(
                "app.integrations.google.oauth_routes.consume_integration_oauth_state",
                return_value=record,
            ) as mock_consume,
            patch(
                "app.integrations.google.oauth_routes.consume_oauth_state",
            ) as mock_onboarding_consume,
            patch(
                "app.integrations.google.oauth_routes.exchange_code",
                return_value={
                    "access_token": "at-new",
                    "refresh_token": "rt-new",
                    "expires_at": expires,
                    "scopes": settings.GOOGLE_OAUTH_SCOPES,
                },
            ),
            patch(
                "app.integrations.google.oauth_routes.fetch_user_email",
                return_value="user@example.com",
            ),
            patch(
                "app.integrations.google.oauth_routes.OAuthCredentialRepository.upsert",
            ),
            patch(
                "app.integrations.google.oauth_routes.emit_onboarding_audit",
            ),
        ):
            client = TestClient(app, raise_server_exceptions=False, follow_redirects=False)
            resp = client.get(
                "/integrations/google_mail/oauth/callback",
                params={"code": "auth-code-value", "state": record.state_id},
                # deliberately no admin_session cookie
            )

        app.dependency_overrides.clear()

        assert resp.status_code == 302
        assert "oauth=complete" in resp.headers["location"]
        mock_consume.assert_called_once()
        mock_onboarding_consume.assert_not_called()

    def test_missing_state_returns_oauth_state_invalid(self):
        from app.api.dependencies import get_db
        from app.core.settings import get_settings
        from app.main import app

        mock_db = MagicMock()
        app.dependency_overrides[get_db] = lambda: (yield mock_db)
        app.dependency_overrides[get_settings] = lambda: _settings()

        with patch(
            "app.integrations.google.oauth_routes.lookup_oauth_state_source",
            return_value=None,
        ):
            client = TestClient(app, raise_server_exceptions=False, follow_redirects=False)
            resp = client.get(
                "/integrations/google_mail/oauth/callback",
                params={"code": "auth-code-value", "state": "unknown-state-id"},
            )

        app.dependency_overrides.clear()
        assert resp.status_code == 302
        assert "oauth_state_invalid" in resp.headers["location"]

    def test_expired_integration_state_returns_specific_reason(self):
        from app.api.dependencies import get_db
        from app.core.settings import get_settings
        from app.integrations.oauth_state import OAuthStateError
        from app.main import app

        mock_db = MagicMock()
        app.dependency_overrides[get_db] = lambda: (yield mock_db)
        app.dependency_overrides[get_settings] = lambda: _settings()

        with (
            patch(
                "app.integrations.google.oauth_routes.lookup_oauth_state_source",
                return_value="integration",
            ),
            patch(
                "app.integrations.google.oauth_routes.consume_integration_oauth_state",
                side_effect=OAuthStateError("expired", code="oauth_state_expired"),
            ),
        ):
            client = TestClient(app, raise_server_exceptions=False, follow_redirects=False)
            resp = client.get(
                "/integrations/google_mail/oauth/callback",
                params={"code": "auth-code-value", "state": "some-integration-state"},
            )

        app.dependency_overrides.clear()
        assert resp.status_code == 302
        assert "oauth_state_expired" in resp.headers["location"]


class TestOnboardingHeuristicWouldHaveMisrouted:
    def test_opaque_integration_state_matches_old_heuristic(self):
        """Document why DB lookup replaced is_onboarding_oauth_state."""
        from app.admin.onboarding.oauth_state_service import is_onboarding_oauth_state

        integration_like = "gYATDif3S75hi-I8c-po4C6kwfe0n6GMHwPAwbtiXXQ"
        assert is_onboarding_oauth_state(integration_like) is True
