"""
Tests for app/core/auth.py — get_verified_tenant dependency.

Covers:
- Auth disabled (TENANT_API_KEYS empty): X-Tenant-ID header is used directly
- Auth enabled: valid key resolves to correct tenant_id
- Auth enabled: missing key returns 401
- Auth enabled: invalid key returns 403
- Auth enabled: X-Tenant-ID header is ignored when key map is set
- Startup error: TENANT_API_KEYS is malformed JSON
"""
from __future__ import annotations

import importlib
from unittest.mock import patch

import pytest
from fastapi import HTTPException


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reload_auth():
    """Reload auth module to reset the module-level _API_KEY_MAP cache."""
    import app.core.auth as auth_mod
    auth_mod._API_KEY_MAP = None
    return auth_mod


def _make_header(value: str | None):
    """Return a Header-like string or None."""
    return value


# ---------------------------------------------------------------------------
# Dev mode: auth disabled (empty TENANT_API_KEYS)
# ---------------------------------------------------------------------------

class TestAuthDisabled:

    def test_uses_x_tenant_id_when_no_key_map(self):
        auth = _reload_auth()
        with patch("app.core.auth.get_settings") as mock_settings:
            mock_settings.return_value.TENANT_API_KEYS = ""
            tenant_id = auth.get_verified_tenant(
                x_api_key=None,
                x_tenant_id="TENANT_1001",
            )
        assert tenant_id == "TENANT_1001"

    def test_defaults_to_tenant_1001_when_no_header(self):
        auth = _reload_auth()
        with patch("app.core.auth.get_settings") as mock_settings:
            mock_settings.return_value.TENANT_API_KEYS = ""
            tenant_id = auth.get_verified_tenant(
                x_api_key=None,
                x_tenant_id=None,
            )
        assert tenant_id == "TENANT_1001"

    def test_api_key_ignored_in_dev_mode(self):
        """When auth is disabled, a provided API key is simply ignored."""
        auth = _reload_auth()
        with patch("app.core.auth.get_settings") as mock_settings:
            mock_settings.return_value.TENANT_API_KEYS = ""
            tenant_id = auth.get_verified_tenant(
                x_api_key="some-key",
                x_tenant_id="TENANT_2001",
            )
        assert tenant_id == "TENANT_2001"


# ---------------------------------------------------------------------------
# Auth enabled: valid key
# ---------------------------------------------------------------------------

KEY_MAP_JSON = '{"TENANT_1001": "key-abc123", "TENANT_2001": "key-def456"}'


class TestAuthEnabled:

    def test_valid_key_returns_correct_tenant(self):
        auth = _reload_auth()
        with patch("app.core.auth.get_settings") as mock_settings:
            mock_settings.return_value.TENANT_API_KEYS = KEY_MAP_JSON
            tenant_id = auth.get_verified_tenant(
                x_api_key="key-abc123",
                x_tenant_id=None,
            )
        assert tenant_id == "TENANT_1001"

    def test_second_tenant_valid_key(self):
        auth = _reload_auth()
        with patch("app.core.auth.get_settings") as mock_settings:
            mock_settings.return_value.TENANT_API_KEYS = KEY_MAP_JSON
            tenant_id = auth.get_verified_tenant(
                x_api_key="key-def456",
                x_tenant_id=None,
            )
        assert tenant_id == "TENANT_2001"

    def test_x_tenant_id_ignored_when_auth_enabled(self):
        """Tenant is resolved from key, not from X-Tenant-ID header."""
        auth = _reload_auth()
        with patch("app.core.auth.get_settings") as mock_settings:
            mock_settings.return_value.TENANT_API_KEYS = KEY_MAP_JSON
            tenant_id = auth.get_verified_tenant(
                x_api_key="key-abc123",
                x_tenant_id="TENANT_9999",  # arbitrary — must be ignored
            )
        assert tenant_id == "TENANT_1001"
        assert tenant_id != "TENANT_9999"


# ---------------------------------------------------------------------------
# Auth enabled: missing key → 401
# ---------------------------------------------------------------------------

class TestMissingKey:

    def test_missing_key_raises_401(self):
        auth = _reload_auth()
        with patch("app.core.auth.get_settings") as mock_settings:
            mock_settings.return_value.TENANT_API_KEYS = KEY_MAP_JSON
            with pytest.raises(HTTPException) as exc_info:
                auth.get_verified_tenant(
                    x_api_key=None,
                    x_tenant_id="TENANT_1001",
                )
        assert exc_info.value.status_code == 401

    def test_missing_key_error_message(self):
        auth = _reload_auth()
        with patch("app.core.auth.get_settings") as mock_settings:
            mock_settings.return_value.TENANT_API_KEYS = KEY_MAP_JSON
            with pytest.raises(HTTPException) as exc_info:
                auth.get_verified_tenant(x_api_key=None, x_tenant_id=None)
        assert "Missing API key" in exc_info.value.detail

    def test_empty_string_key_raises_401(self):
        auth = _reload_auth()
        with patch("app.core.auth.get_settings") as mock_settings:
            mock_settings.return_value.TENANT_API_KEYS = KEY_MAP_JSON
            with pytest.raises(HTTPException) as exc_info:
                auth.get_verified_tenant(x_api_key="", x_tenant_id=None)
        assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Auth enabled: invalid key → 403
# ---------------------------------------------------------------------------

class TestInvalidKey:

    def test_wrong_key_raises_403(self):
        auth = _reload_auth()
        with patch("app.core.auth.get_settings") as mock_settings:
            mock_settings.return_value.TENANT_API_KEYS = KEY_MAP_JSON
            with pytest.raises(HTTPException) as exc_info:
                auth.get_verified_tenant(
                    x_api_key="key-totally-wrong",
                    x_tenant_id=None,
                )
        assert exc_info.value.status_code == 403

    def test_wrong_key_error_message(self):
        auth = _reload_auth()
        with patch("app.core.auth.get_settings") as mock_settings:
            mock_settings.return_value.TENANT_API_KEYS = KEY_MAP_JSON
            with pytest.raises(HTTPException) as exc_info:
                auth.get_verified_tenant(
                    x_api_key="not-a-real-key",
                    x_tenant_id=None,
                )
        assert "Invalid API key" in exc_info.value.detail

    def test_tenant_id_as_key_raises_403(self):
        """Passing the tenant ID itself as the key must not authenticate."""
        auth = _reload_auth()
        with patch("app.core.auth.get_settings") as mock_settings:
            mock_settings.return_value.TENANT_API_KEYS = KEY_MAP_JSON
            with pytest.raises(HTTPException) as exc_info:
                auth.get_verified_tenant(
                    x_api_key="TENANT_1001",
                    x_tenant_id=None,
                )
        assert exc_info.value.status_code == 403


# ---------------------------------------------------------------------------
# Malformed config
# ---------------------------------------------------------------------------

class TestMalformedConfig:

    def test_invalid_json_raises_runtime_error(self):
        auth = _reload_auth()
        with patch("app.core.auth.get_settings") as mock_settings:
            mock_settings.return_value.TENANT_API_KEYS = "not-valid-json"
            with pytest.raises(RuntimeError, match="not valid JSON"):
                auth.get_verified_tenant(x_api_key="any", x_tenant_id=None)

    def test_json_array_raises_runtime_error(self):
        """TENANT_API_KEYS must be a JSON object, not an array."""
        auth = _reload_auth()
        with patch("app.core.auth.get_settings") as mock_settings:
            mock_settings.return_value.TENANT_API_KEYS = '["key1", "key2"]'
            with pytest.raises(RuntimeError, match="JSON object"):
                auth.get_verified_tenant(x_api_key="key1", x_tenant_id=None)
