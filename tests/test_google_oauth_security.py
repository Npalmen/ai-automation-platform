"""
Focused security tests for tenant Google Mail OAuth (pre-deploy gate).

Covers: state tenant binding, revoked refresh, cross-tenant isolation,
secret-free audit/API responses, and admin same-origin on connect/disconnect.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.admin.google_oauth import (
    GoogleMailConnectRequest,
    admin_google_mail_connect,
    admin_google_mail_disconnect,
    admin_google_mail_status,
)
from app.admin.onboarding.audit_events import emit_onboarding_audit, sanitize_audit_details
from app.integrations.google.oauth_routes import google_mail_oauth_callback
from app.integrations.google.oauth_token_resolver import (
    PROVIDER,
    gmail_connection_status,
    refresh_tenant_google_mail_token,
    resolve_google_mail_connection_config,
)
from app.integrations.oauth_state import OAuthStateError, create_integration_oauth_state
from app.repositories.postgres.database import Base
from app.repositories.postgres.oauth_credential_models import OAuthCredentialRecord
from app.repositories.postgres.oauth_credential_repository import OAuthCredentialRepository
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from tests.onboarding_db_tables import onboarding_sqlite_tables

TENANT_A = "TENANT_A"
TENANT_B = "TENANT_B"
OPERATOR = {"id": "op-sec-1", "role": "operations", "display_name": "Ops"}

SECRET_PATTERNS = [
    re.compile(r'"access_token"\s*:\s*"[A-Za-z0-9._\-]{20,}"'),
    re.compile(r'"refresh_token"\s*:\s*"[A-Za-z0-9._\-]{20,}"'),
    re.compile(r'"client_secret"\s*:\s*"[A-Za-z0-9._\-]{8,}"'),
    re.compile(r'"authorization_code"\s*:\s*"[A-Za-z0-9._\-]{8,}"'),
    re.compile(r"ya29\.[A-Za-z0-9._\-]{20,}"),
    re.compile(r"1//[A-Za-z0-9._\-]{20,}"),
]


def _settings(**overrides):
    s = SimpleNamespace(
        SESSION_SECRET_KEY="gate-secret-key",
        ADMIN_API_KEY="admin-key",
        APP_NAME="test",
        GOOGLE_OAUTH_CLIENT_ID="client-id",
        GOOGLE_OAUTH_CLIENT_SECRET="client-secret-value",
        GOOGLE_OAUTH_REDIRECT_URI="https://api.krowolf.se/integrations/google_mail/oauth/callback",
        GOOGLE_OAUTH_SCOPES=(
            "https://www.googleapis.com/auth/gmail.readonly "
            "https://www.googleapis.com/auth/gmail.modify"
        ),
        GOOGLE_MAIL_API_URL="https://gmail.googleapis.com/gmail/v1",
        GOOGLE_MAIL_ACCESS_TOKEN="",
        GOOGLE_MAIL_USER_ID="me",
        GOOGLE_OAUTH_REFRESH_TOKEN="",
    )
    for key, value in overrides.items():
        setattr(s, key, value)
    return s


def _scan_no_secrets(text: str, label: str) -> list[str]:
    hits = []
    for pattern in SECRET_PATTERNS:
        if pattern.search(text):
            hits.append(f"{label}: {pattern.pattern}")
    return hits


def _mock_request(origin: str = "http://testserver"):
    req = MagicMock()
    req.headers = {"origin": origin}
    return req


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    tables = onboarding_sqlite_tables()
    Base.metadata.create_all(bind=engine, tables=tables)
    Session = sessionmaker(bind=engine)
    session = Session()
    for tid, name in ((TENANT_A, "Tenant A"), (TENANT_B, "Tenant B")):
        session.add(
            TenantConfigRecord(
                tenant_id=tid,
                name=name,
                slug=tid.lower(),
                status="active",
                settings={},
            )
        )
    session.commit()
    yield session
    session.close()


class TestOAuthStateTenantBinding:
    def test_cannot_create_state_with_mismatched_redirect_tenant(self, db):
        with pytest.raises(OAuthStateError) as exc:
            create_integration_oauth_state(
                db,
                tenant_id=TENANT_A,
                operator_id=OPERATOR["id"],
                provider=PROVIDER,
                redirect_target=f"/ops/customers/{TENANT_B}",
                settings=_settings(),
            )
        assert exc.value.code == "oauth_redirect_invalid"

    def test_tampered_state_tenant_fails_closed(self, db):
        settings = _settings()
        state_id, record = create_integration_oauth_state(
            db,
            tenant_id=TENANT_A,
            operator_id=OPERATOR["id"],
            provider=PROVIDER,
            redirect_target=f"/ops/customers/{TENANT_A}",
            settings=settings,
        )
        record.tenant_id = TENANT_B
        db.commit()

        from app.integrations.oauth_state import consume_integration_oauth_state

        with pytest.raises(OAuthStateError) as exc:
            consume_integration_oauth_state(
                db, state_id=state_id, provider=PROVIDER, settings=settings
            )
        assert exc.value.code == "oauth_state_invalid"

    @patch("app.integrations.google.oauth_routes.lookup_oauth_state_source", return_value="integration")
    @patch("app.integrations.google.oauth_routes.fetch_user_email", return_value="a@example.com")
    @patch("app.integrations.google.oauth_routes.exchange_code")
    def test_callback_persists_credential_for_state_tenant_only(
        self, mock_exchange, _mock_email, _mock_onboarding, db
    ):
        settings = _settings()
        state_id, _ = create_integration_oauth_state(
            db,
            tenant_id=TENANT_A,
            operator_id=OPERATOR["id"],
            provider=PROVIDER,
            redirect_target=f"/ops/customers/{TENANT_A}",
            settings=settings,
        )
        db.commit()

        mock_exchange.return_value = {
            "access_token": "at-callback-new",
            "refresh_token": "rt-callback-new",
            "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
            "scopes": settings.GOOGLE_OAUTH_SCOPES,
        }

        with patch("app.integrations.google.oauth_routes.get_settings", return_value=settings):
            resp = google_mail_oauth_callback(
                code="auth-code-xyz",
                state=state_id,
                error=None,
                db=db,
                settings=settings,
            )

        assert resp.status_code == 302
        assert TENANT_B not in resp.headers["location"]

        row_a = OAuthCredentialRepository.get(db, TENANT_A, PROVIDER)
        row_b = OAuthCredentialRepository.get(db, TENANT_B, PROVIDER)
        assert row_a is not None
        assert row_a.access_token == "at-callback-new"
        assert row_b is None


class TestRevokedRefreshToken:
    def test_invalid_grant_maps_to_reconnect_required(self, db):
        row = OAuthCredentialRecord(
            tenant_id=TENANT_A,
            provider=PROVIDER,
            access_token="stale-at",
            refresh_token="revoked-rt",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            scopes=_settings().GOOGLE_OAUTH_SCOPES,
            metadata_json={"email": "a@example.com"},
            connected_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()

        with patch(
            "app.integrations.google.oauth_token_resolver.refresh_access_token",
            side_effect=RuntimeError("invalid_grant: Token has been revoked."),
        ):
            with pytest.raises(RuntimeError) as exc:
                refresh_tenant_google_mail_token(db, TENANT_A)
            assert "reconnect" in str(exc.value).lower()

    def test_resolver_does_not_return_stale_access_token_on_revoke(self, db):
        row = OAuthCredentialRecord(
            tenant_id=TENANT_A,
            provider=PROVIDER,
            access_token="stale-at-should-not-use",
            refresh_token="revoked-rt",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            scopes=_settings().GOOGLE_OAUTH_SCOPES,
            metadata_json={},
            connected_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()

        with patch(
            "app.integrations.google.oauth_token_resolver.refresh_access_token",
            side_effect=RuntimeError("invalid_grant"),
        ):
            with pytest.raises(RuntimeError) as exc:
                resolve_google_mail_connection_config(TENANT_A, db=db, settings=_settings())
            assert "reconnect" in str(exc.value).lower()

    def test_status_shows_reconnect_when_refresh_missing(self, db):
        row = OAuthCredentialRecord(
            tenant_id=TENANT_A,
            provider=PROVIDER,
            access_token="expired-at",
            refresh_token=None,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            scopes=_settings().GOOGLE_OAUTH_SCOPES,
            metadata_json={},
            connected_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()

        out = gmail_connection_status(db, TENANT_A, settings=_settings())
        assert out["connection_state"] == "reconnect_required"
        assert out["reconnect_required"] is True
        assert "refresh_token" not in json.dumps(out)
        assert "expired-at" not in json.dumps(out)

    def test_oauth_failure_audit_is_secret_free(self, db):
        emit_onboarding_audit(
            db,
            tenant_id=TENANT_A,
            action="oauth_connection_failed",
            status="failed",
            details={
                "provider": PROVIDER,
                "error_code": "invalid_grant",
                "access_token": "must-not-persist",
                "refresh_token": "must-not-persist",
                "authorization_code": "must-not-persist",
                "client_secret": "must-not-persist",
            },
            require_allowlist=True,
        )
        db.commit()
        from app.repositories.postgres.audit_models import AuditEventRecord

        row = db.query(AuditEventRecord).first()
        blob = json.dumps(row.details)
        assert _scan_no_secrets(blob, "audit") == []
        assert "must-not-persist" not in blob


class TestCrossTenantIsolation:
    def _seed_credential(self, db, tenant_id: str):
        db.add(
            OAuthCredentialRecord(
                tenant_id=tenant_id,
                provider=PROVIDER,
                access_token=f"at-{tenant_id}",
                refresh_token=f"rt-{tenant_id}",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                scopes=_settings().GOOGLE_OAUTH_SCOPES,
                metadata_json={"email": f"{tenant_id}@example.com"},
                connected_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

    def test_admin_status_cannot_see_other_tenant_credential(self, db):
        self._seed_credential(db, TENANT_A)
        settings = _settings()

        status_b = admin_google_mail_status(
            TENANT_B, db=db, operator=OPERATOR, settings=settings
        )
        assert status_b["connection_state"] == "not_connected"
        assert status_b["connected"] is False

        status_a = admin_google_mail_status(
            TENANT_A, db=db, operator=OPERATOR, settings=settings
        )
        assert status_a["connection_state"] == "connected"
        assert status_a["email"] == f"{TENANT_A}@example.com"

    def test_admin_disconnect_other_tenant_does_not_remove_credential(self, db):
        self._seed_credential(db, TENANT_A)
        with patch("app.admin.google_oauth.require_same_origin"):
            result = admin_google_mail_disconnect(
                TENANT_B,
                request=_mock_request(),
                db=db,
                operator=OPERATOR,
            )
        assert result["status"] == "not_connected"
        assert OAuthCredentialRepository.get(db, TENANT_A, PROVIDER) is not None

    def test_tenant_api_test_read_isolated(self):
        from app.api.dependencies import get_db
        from app.core.auth import get_verified_tenant
        from app.core.settings import get_settings
        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)
        settings = _settings()
        mock_db = MagicMock()

        def _tenant_b():
            return TENANT_B

        def _db():
            yield mock_db

        app.dependency_overrides[get_verified_tenant] = _tenant_b
        app.dependency_overrides[get_db] = _db
        app.dependency_overrides[get_settings] = lambda: settings
        try:
            with (
                patch("app.core.auth._load_env_key_map", return_value={TENANT_B: "key-b"}),
                patch("app.core.auth._lookup_db_key", return_value=None),
                patch(
                    "app.integrations.google.oauth_routes.OAuthCredentialRepository.get",
                    return_value=None,
                ),
            ):
                resp = client.post(
                    "/integrations/google_mail/test-read",
                    headers={"X-API-Key": "key-b"},
                )
        finally:
            app.dependency_overrides.pop(get_verified_tenant, None)
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_settings, None)

        assert resp.status_code == 400
        assert "not connected" in resp.json().get("detail", "").lower()

    def test_admin_connect_uses_path_tenant_not_body(self, db):
        settings = _settings()
        with (
            patch("app.admin.google_oauth.require_same_origin"),
            patch("app.admin.google_oauth.get_auth_url_for_state", return_value="https://accounts.google.com/o/oauth2/v2/auth?state=x"),
        ):
            out = admin_google_mail_connect(
                TENANT_A,
                body=GoogleMailConnectRequest(redirect_target=f"/ops/customers/{TENANT_A}"),
                request=_mock_request(),
                db=db,
                operator=OPERATOR,
                settings=settings,
            )
        assert out["authorization_url"].startswith("https://accounts.google.com")
        from app.integrations.oauth_state_models import IntegrationOAuthStateRecord

        state_row = db.query(IntegrationOAuthStateRecord).first()
        assert state_row.tenant_id == TENANT_A
        assert state_row.tenant_id != TENANT_B


class TestSecretScanAndAuditRedaction:
    def test_sanitize_audit_details_blocks_oauth_secrets(self):
        clean = sanitize_audit_details(
            {
                "access_token": "ya29.secret",
                "refresh_token": "1//secret",
                "authorization_code": "4/code",
                "client_secret": "cs-secret",
                "raw_oauth_response": {"access_token": "nested"},
                "operator_id": "op-1",
                "error_code": "invalid_grant",
            }
        )
        blob = json.dumps(clean)
        assert _scan_no_secrets(blob, "sanitize") == []
        assert "ya29" not in blob
        assert "operator_id" in blob
        assert "error_code" not in blob  # blocked key fragment "code"

    def test_admin_status_response_has_no_secrets(self, db):
        db.add(
            OAuthCredentialRecord(
                tenant_id=TENANT_A,
                provider=PROVIDER,
                access_token="ya29.super-secret-access-token-value",
                refresh_token="1//super-secret-refresh-token-value",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                scopes=_settings().GOOGLE_OAUTH_SCOPES,
                metadata_json={"email": "a@example.com"},
                connected_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        out = admin_google_mail_status(
            TENANT_A, db=db, operator=OPERATOR, settings=_settings()
        )
        blob = json.dumps(out)
        assert _scan_no_secrets(blob, "admin_status") == []
        assert "ya29" not in blob
        assert "1//" not in blob

    @patch("app.integrations.google.oauth_service.get_settings")
    def test_auth_url_excludes_send_scope_and_secrets(self, mock_settings):
        import app.integrations.google.oauth_service as oauth_service

        mock_settings.return_value = _settings()
        url = oauth_service.get_auth_url_for_state("opaque-state")
        assert "gmail.send" not in url
        assert "client-secret-value" not in url
        assert "gmail.readonly" in url
        assert "gmail.modify" in url


class TestAdminSameOriginConnectDisconnect:
    def test_connect_rejects_foreign_origin(self, db):
        settings = _settings()
        with patch("app.admin.google_oauth.get_settings", return_value=settings):
            with pytest.raises(HTTPException) as exc:
                admin_google_mail_connect(
                    TENANT_A,
                    body=GoogleMailConnectRequest(redirect_target=f"/ops/customers/{TENANT_A}"),
                    request=_mock_request(origin="https://attacker.example"),
                    db=db,
                    operator=OPERATOR,
                    settings=settings,
                )
        assert exc.value.status_code == 403

    def test_disconnect_rejects_foreign_origin(self, db):
        with pytest.raises(HTTPException) as exc:
            admin_google_mail_disconnect(
                TENANT_A,
                request=_mock_request(origin="https://attacker.example"),
                db=db,
                operator=OPERATOR,
            )
        assert exc.value.status_code == 403
