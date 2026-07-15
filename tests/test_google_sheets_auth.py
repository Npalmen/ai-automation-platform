"""Tests for Google Sheets OAuth token resolution."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.integrations.google.sheets_auth import resolve_google_sheets_access_token


class TestResolveGoogleSheetsAccessToken:
    def test_tenant_override_takes_precedence(self):
        token = resolve_google_sheets_access_token({"access_token": "tenant_override_token"})
        assert token == "tenant_override_token"

    def test_refresh_used_when_no_tenant_override(self):
        with patch(
            "app.integrations.google.sheets_auth.refresh_access_token",
            return_value="refreshed_token",
        ) as mock_refresh:
            token = resolve_google_sheets_access_token({})

        assert token == "refreshed_token"
        mock_refresh.assert_called_once()

    def test_missing_refresh_credentials_raises(self):
        with (
            patch("app.integrations.google.sheets_auth.get_settings") as mock_settings,
            patch("app.integrations.google.sheets_auth.refresh_access_token") as mock_refresh,
        ):
            mock_settings.return_value.GOOGLE_OAUTH_REFRESH_TOKEN = ""
            mock_settings.return_value.GOOGLE_OAUTH_CLIENT_ID = ""
            mock_settings.return_value.GOOGLE_OAUTH_CLIENT_SECRET = ""

            with pytest.raises(RuntimeError, match="refresh credentials"):
                resolve_google_sheets_access_token({})

        mock_refresh.assert_not_called()
