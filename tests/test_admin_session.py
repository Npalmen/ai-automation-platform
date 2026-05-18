"""
Tests for Slice 3 — Admin Session Auth Vertical.

Covers:
- hash_password / verify_password round-trip
- verify_password with wrong password returns False
- create_session_token / validate_session_token round-trip
- validate_session_token with tampered signature returns None
- validate_session_token with expired token returns None
- validate_session_token with wrong secret returns None
- get_admin_from_session: no cookie returns None
- get_admin_from_session: valid cookie returns username
- get_admin_from_session: no SECRET_KEY configured returns None
- verify_admin_credentials: correct creds return True
- verify_admin_credentials: wrong password returns False
- verify_admin_credentials: wrong username returns False
- verify_admin_credentials: unconfigured hash returns False
- is_session_auth_configured: True when both fields set
- is_session_auth_configured: False when hash missing
- is_session_auth_configured: False when secret missing
- require_admin_api_key: valid session cookie bypasses key check
- require_admin_api_key: invalid session cookie falls through to key check
- POST /auth/admin/login: success with credentials sets cookie
- POST /auth/admin/login: wrong password returns 401
- POST /auth/admin/login: api-key fallback when hash not configured
- POST /auth/admin/logout: clears cookie
- GET /auth/admin/me: valid session returns username
- GET /auth/admin/me: no session returns 401
"""
from __future__ import annotations

import base64
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

class TestPasswordHashing:
    def test_round_trip(self):
        from app.core.admin_session import hash_password, verify_password
        h = hash_password("mysecretpassword")
        assert verify_password("mysecretpassword", h) is True

    def test_wrong_password_returns_false(self):
        from app.core.admin_session import hash_password, verify_password
        h = hash_password("correct")
        assert verify_password("wrong", h) is False

    def test_empty_password_round_trip(self):
        from app.core.admin_session import hash_password, verify_password
        h = hash_password("")
        assert verify_password("", h) is True
        assert verify_password("x", h) is False

    def test_different_hashes_same_password(self):
        """Salt ensures two hashes of the same password differ."""
        from app.core.admin_session import hash_password
        h1 = hash_password("pw")
        h2 = hash_password("pw")
        assert h1 != h2

    def test_verify_handles_garbage_gracefully(self):
        from app.core.admin_session import verify_password
        assert verify_password("pw", "not-a-valid-hash") is False
        assert verify_password("pw", "") is False


# ---------------------------------------------------------------------------
# Session tokens
# ---------------------------------------------------------------------------

SECRET = "test-secret-key-for-unit-tests"


class TestSessionTokens:
    def test_round_trip(self):
        from app.core.admin_session import create_session_token, validate_session_token
        token = create_session_token("admin", SECRET)
        result = validate_session_token(token, SECRET)
        assert result == "admin"

    def test_wrong_secret_returns_none(self):
        from app.core.admin_session import create_session_token, validate_session_token
        token = create_session_token("admin", SECRET)
        assert validate_session_token(token, "other-secret") is None

    def test_tampered_signature_returns_none(self):
        from app.core.admin_session import create_session_token, validate_session_token
        token = create_session_token("admin", SECRET)
        parts = token.rsplit(".", 1)
        tampered = parts[0] + "." + "aabbccddeeff00112233" + parts[1][20:]
        assert validate_session_token(tampered, SECRET) is None

    def test_tampered_payload_returns_none(self):
        from app.core.admin_session import create_session_token, validate_session_token
        token = create_session_token("admin", SECRET)
        encoded, sig = token.rsplit(".", 1)
        # Change last char of encoded part
        tampered = encoded[:-1] + ("A" if encoded[-1] != "A" else "B") + "." + sig
        assert validate_session_token(tampered, SECRET) is None

    def test_expired_token_returns_none(self):
        from app.core.admin_session import create_session_token, validate_session_token
        import json as _json
        # Build a token with exp in the past
        past = int(time.time()) - 3600
        payload = _json.dumps({"sub": "admin", "iat": past - 3600, "exp": past})
        import hmac as _hmac, hashlib as _hl
        encoded = base64.urlsafe_b64encode(payload.encode()).decode()
        sig = _hmac.new(SECRET.encode(), encoded.encode(), _hl.sha256).hexdigest()
        token = f"{encoded}.{sig}"
        assert validate_session_token(token, SECRET) is None

    def test_malformed_token_returns_none(self):
        from app.core.admin_session import validate_session_token
        assert validate_session_token("notavalidtoken", SECRET) is None
        assert validate_session_token("", SECRET) is None


# ---------------------------------------------------------------------------
# get_admin_from_session
# ---------------------------------------------------------------------------

class TestGetAdminFromSession:
    def _make_request(self, cookie_value=None, secret=""):
        request = MagicMock()
        request.cookies = {
            "admin_session": cookie_value
        } if cookie_value else {}
        settings_mock = MagicMock()
        settings_mock.SESSION_SECRET_KEY = secret
        return request, settings_mock

    def test_no_cookie_returns_none(self):
        from app.core.admin_session import get_admin_from_session
        request, settings = self._make_request(cookie_value=None, secret=SECRET)
        with patch("app.core.admin_session.get_settings", return_value=settings):
            assert get_admin_from_session(request) is None

    def test_no_secret_configured_returns_none(self):
        from app.core.admin_session import get_admin_from_session, create_session_token
        token = create_session_token("admin", SECRET)
        request, settings = self._make_request(cookie_value=token, secret="")
        with patch("app.core.admin_session.get_settings", return_value=settings):
            assert get_admin_from_session(request) is None

    def test_valid_cookie_returns_username(self):
        from app.core.admin_session import get_admin_from_session, create_session_token
        token = create_session_token("admin", SECRET)
        request, settings = self._make_request(cookie_value=token, secret=SECRET)
        with patch("app.core.admin_session.get_settings", return_value=settings):
            assert get_admin_from_session(request) == "admin"

    def test_invalid_cookie_returns_none(self):
        from app.core.admin_session import get_admin_from_session
        request, settings = self._make_request(cookie_value="garbage", secret=SECRET)
        with patch("app.core.admin_session.get_settings", return_value=settings):
            assert get_admin_from_session(request) is None


# ---------------------------------------------------------------------------
# verify_admin_credentials
# ---------------------------------------------------------------------------

class TestVerifyAdminCredentials:
    def _settings(self, username="admin", password_hash=""):
        s = MagicMock()
        s.ADMIN_USERNAME = username
        s.ADMIN_PASSWORD_HASH = password_hash
        return s

    def test_correct_credentials(self):
        from app.core.admin_session import verify_admin_credentials, hash_password
        h = hash_password("correct-password")
        settings = self._settings(username="admin", password_hash=h)
        with patch("app.core.admin_session.get_settings", return_value=settings):
            assert verify_admin_credentials("admin", "correct-password") is True

    def test_wrong_password(self):
        from app.core.admin_session import verify_admin_credentials, hash_password
        h = hash_password("correct-password")
        settings = self._settings(username="admin", password_hash=h)
        with patch("app.core.admin_session.get_settings", return_value=settings):
            assert verify_admin_credentials("admin", "wrong-password") is False

    def test_wrong_username(self):
        from app.core.admin_session import verify_admin_credentials, hash_password
        h = hash_password("correct-password")
        settings = self._settings(username="admin", password_hash=h)
        with patch("app.core.admin_session.get_settings", return_value=settings):
            assert verify_admin_credentials("notadmin", "correct-password") is False

    def test_unconfigured_hash_returns_false(self):
        from app.core.admin_session import verify_admin_credentials
        settings = self._settings(username="admin", password_hash="")
        with patch("app.core.admin_session.get_settings", return_value=settings):
            assert verify_admin_credentials("admin", "anything") is False

    def test_case_insensitive_username(self):
        from app.core.admin_session import verify_admin_credentials, hash_password
        h = hash_password("pw")
        settings = self._settings(username="Admin", password_hash=h)
        with patch("app.core.admin_session.get_settings", return_value=settings):
            assert verify_admin_credentials("admin", "pw") is True


# ---------------------------------------------------------------------------
# is_session_auth_configured
# ---------------------------------------------------------------------------

class TestIsSessionAuthConfigured:
    def _settings(self, hash_val="", secret=""):
        s = MagicMock()
        s.ADMIN_PASSWORD_HASH = hash_val
        s.SESSION_SECRET_KEY = secret
        return s

    def test_both_set_returns_true(self):
        from app.core.admin_session import is_session_auth_configured
        with patch("app.core.admin_session.get_settings", return_value=self._settings("somehash", "somesecret")):
            assert is_session_auth_configured() is True

    def test_hash_missing_returns_false(self):
        from app.core.admin_session import is_session_auth_configured
        with patch("app.core.admin_session.get_settings", return_value=self._settings("", "somesecret")):
            assert is_session_auth_configured() is False

    def test_secret_missing_returns_false(self):
        from app.core.admin_session import is_session_auth_configured
        with patch("app.core.admin_session.get_settings", return_value=self._settings("somehash", "")):
            assert is_session_auth_configured() is False

    def test_both_missing_returns_false(self):
        from app.core.admin_session import is_session_auth_configured
        with patch("app.core.admin_session.get_settings", return_value=self._settings("", "")):
            assert is_session_auth_configured() is False


# ---------------------------------------------------------------------------
# require_admin_api_key — session cookie integration
# ---------------------------------------------------------------------------

class TestRequireAdminApiKeyWithSession:
    def test_valid_session_bypasses_key_check(self):
        """A valid session cookie should let a request through even without X-Admin-API-Key."""
        from app.core.admin_auth import require_admin_api_key
        from app.core.admin_session import create_session_token

        token = create_session_token("admin", SECRET)
        request = MagicMock()
        request.cookies = {"admin_session": token}

        settings_mock = MagicMock()
        settings_mock.SESSION_SECRET_KEY = SECRET
        settings_mock.ADMIN_PASSWORD_HASH = "hash"

        with patch("app.core.admin_session.get_settings", return_value=settings_mock):
            result = require_admin_api_key(request=request, x_admin_api_key=None)
        assert result is None

    def test_invalid_session_falls_through_to_key(self):
        """Invalid cookie with no API key should still raise 401."""
        from app.core.admin_auth import require_admin_api_key

        request = MagicMock()
        request.cookies = {"admin_session": "invalid-garbage"}

        admin_settings = MagicMock()
        admin_settings.SESSION_SECRET_KEY = SECRET
        admin_settings.ADMIN_PASSWORD_HASH = "hash"

        auth_settings = MagicMock()
        auth_settings.ADMIN_API_KEY = "configured-key"
        auth_settings.ADMIN_API_KEYS = ""

        with patch("app.core.admin_session.get_settings", return_value=admin_settings):
            with patch("app.core.admin_auth.get_settings", return_value=auth_settings):
                with pytest.raises(HTTPException) as exc_info:
                    require_admin_api_key(request=request, x_admin_api_key=None)
        assert exc_info.value.status_code == 401

    def test_no_session_cookie_falls_through_to_key(self):
        """Empty cookies fall through to API key check."""
        from app.core.admin_auth import require_admin_api_key
        settings_mock = MagicMock()
        settings_mock.ADMIN_API_KEY = "my-key"
        settings_mock.ADMIN_API_KEYS = ""
        session_settings = MagicMock()
        session_settings.SESSION_SECRET_KEY = ""
        request = MagicMock()
        request.cookies = {}
        with patch("app.core.admin_auth.get_settings", return_value=settings_mock):
            with patch("app.core.admin_session.get_settings", return_value=session_settings):
                result = require_admin_api_key(request=request, x_admin_api_key="my-key")
        assert result is None


# ---------------------------------------------------------------------------
# Auth endpoints via TestClient
# ---------------------------------------------------------------------------

def _make_app_client():
    """Return a TestClient for the FastAPI app with DB mocked out."""
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


class TestAuthEndpoints:
    def test_login_success_with_credentials(self):
        from app.core.admin_session import hash_password

        h = hash_password("testpassword")
        settings_mock = MagicMock()
        settings_mock.SESSION_SECRET_KEY = SECRET
        settings_mock.ADMIN_PASSWORD_HASH = h
        settings_mock.ADMIN_USERNAME = "admin"
        settings_mock.ADMIN_API_KEY = ""
        settings_mock.ADMIN_API_KEYS = ""

        with patch("app.core.admin_session.get_settings", return_value=settings_mock):
            with patch("app.main.get_settings", return_value=settings_mock):
                client = _make_app_client()
                resp = client.post(
                    "/auth/admin/login",
                    json={"username": "admin", "password": "testpassword"},
                )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("ok") is True
        assert data.get("mode") == "session"

    def test_login_failure_wrong_password(self):
        from app.core.admin_session import hash_password

        h = hash_password("correctpassword")
        settings_mock = MagicMock()
        settings_mock.SESSION_SECRET_KEY = SECRET
        settings_mock.ADMIN_PASSWORD_HASH = h
        settings_mock.ADMIN_USERNAME = "admin"
        settings_mock.ADMIN_API_KEY = ""
        settings_mock.ADMIN_API_KEYS = ""

        with patch("app.core.admin_session.get_settings", return_value=settings_mock):
            with patch("app.main.get_settings", return_value=settings_mock):
                client = _make_app_client()
                resp = client.post(
                    "/auth/admin/login",
                    json={"username": "admin", "password": "wrongpassword"},
                )
        assert resp.status_code == 401

    def test_login_api_key_fallback(self):
        """When no password hash configured, password field is treated as API key."""
        settings_mock = MagicMock()
        settings_mock.SESSION_SECRET_KEY = ""
        settings_mock.ADMIN_PASSWORD_HASH = ""
        settings_mock.ADMIN_USERNAME = "admin"
        settings_mock.ADMIN_API_KEY = "my-admin-key"
        settings_mock.ADMIN_API_KEYS = ""

        with patch("app.core.admin_session.get_settings", return_value=settings_mock):
            with patch("app.main.get_settings", return_value=settings_mock):
                with patch("app.core.admin_auth.get_settings", return_value=settings_mock):
                    client = _make_app_client()
                    resp = client.post(
                        "/auth/admin/login",
                        json={"username": "admin", "password": "my-admin-key"},
                    )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("ok") is True
        assert data.get("mode") == "api_key"

    def test_login_api_key_fallback_wrong_key(self):
        settings_mock = MagicMock()
        settings_mock.SESSION_SECRET_KEY = ""
        settings_mock.ADMIN_PASSWORD_HASH = ""
        settings_mock.ADMIN_USERNAME = "admin"
        settings_mock.ADMIN_API_KEY = "my-admin-key"
        settings_mock.ADMIN_API_KEYS = ""

        with patch("app.core.admin_session.get_settings", return_value=settings_mock):
            with patch("app.main.get_settings", return_value=settings_mock):
                with patch("app.core.admin_auth.get_settings", return_value=settings_mock):
                    client = _make_app_client()
                    resp = client.post(
                        "/auth/admin/login",
                        json={"username": "admin", "password": "wrong-key"},
                    )
        assert resp.status_code == 401

    def test_logout_returns_200(self):
        client = _make_app_client()
        resp = client.post("/auth/admin/logout")
        assert resp.status_code == 200
        assert resp.json().get("ok") is True

    def test_me_without_session_returns_401(self):
        settings_mock = MagicMock()
        settings_mock.SESSION_SECRET_KEY = SECRET
        settings_mock.ADMIN_PASSWORD_HASH = "hash"

        with patch("app.core.admin_session.get_settings", return_value=settings_mock):
            client = _make_app_client()
            resp = client.get("/auth/admin/me")
        assert resp.status_code == 401

    def test_me_with_valid_session_returns_username(self):
        from app.core.admin_session import create_session_token

        token = create_session_token("admin", SECRET)
        settings_mock = MagicMock()
        settings_mock.SESSION_SECRET_KEY = SECRET
        settings_mock.ADMIN_PASSWORD_HASH = "hash"

        with patch("app.core.admin_session.get_settings", return_value=settings_mock):
            client = _make_app_client()
            client.cookies.set("admin_session", token)
            resp = client.get("/auth/admin/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("username") == "admin"
        assert data.get("authenticated") is True
