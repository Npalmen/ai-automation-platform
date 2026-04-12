"""
Tests for Gmail OAuth token refresh slice.

Covers:
  refresh_access_token():
    - returns new access token on success
    - raises RuntimeError when HTTP call fails
    - raises RuntimeError when response has no access_token field

  GoogleMailClient._can_refresh():
    - True when all three credentials present
    - False when any credential is missing

  GoogleMailClient.send_message() refresh flow:
    - no refresh attempted when first request succeeds (200)
    - no refresh attempted when 401 but refresh credentials absent
    - refresh attempted and retry succeeds when 401 + credentials present
    - raises after refresh if retry also returns 401
    - raises immediately on 403 (not a token expiry)
    - updated access_token used in retry request

  GoogleMailAdapter:
    - refresh credentials passed from connection_config to client

  service.py:
    - get_integration_connection_config includes refresh keys for GOOGLE_MAIL
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest

from app.integrations.google.mail_client import GoogleMailClient, refresh_access_token
from app.integrations.google.adapter import GoogleMailAdapter
from app.integrations.enums import IntegrationType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(status_code: int, json_data: dict | None = None, text: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.json.return_value = json_data or {}
    return resp


def _client(
    access_token: str = "tok-valid",
    refresh_token: str = "",
    client_id: str = "",
    client_secret: str = "",
) -> GoogleMailClient:
    return GoogleMailClient(
        api_url="https://gmail.googleapis.com/gmail/v1",
        access_token=access_token,
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
    )


def _client_with_refresh() -> GoogleMailClient:
    return _client(
        access_token="tok-expired",
        refresh_token="rtoken-123",
        client_id="client-id-abc",
        client_secret="client-secret-xyz",
    )


# ---------------------------------------------------------------------------
# refresh_access_token
# ---------------------------------------------------------------------------

class TestRefreshAccessToken:
    def test_returns_new_token_on_success(self):
        ok_resp = _mock_response(200, {"access_token": "new-tok-456"})
        with patch("app.integrations.google.mail_client.requests.post", return_value=ok_resp):
            result = refresh_access_token("rtoken", "cid", "csecret")
        assert result == "new-tok-456"

    def test_raises_on_http_error(self):
        err_resp = _mock_response(400, text="invalid_grant")
        with patch("app.integrations.google.mail_client.requests.post", return_value=err_resp):
            with pytest.raises(RuntimeError, match="token refresh failed"):
                refresh_access_token("rtoken", "cid", "csecret")

    def test_raises_when_no_access_token_in_response(self):
        ok_resp = _mock_response(200, {"token_type": "Bearer"})  # missing access_token
        with patch("app.integrations.google.mail_client.requests.post", return_value=ok_resp):
            with pytest.raises(RuntimeError, match="no access_token"):
                refresh_access_token("rtoken", "cid", "csecret")

    def test_posts_to_google_token_url(self):
        ok_resp = _mock_response(200, {"access_token": "new-tok"})
        with patch("app.integrations.google.mail_client.requests.post", return_value=ok_resp) as mock_post:
            refresh_access_token("rtoken", "cid", "csecret")
        url = mock_post.call_args[0][0]
        assert "oauth2.googleapis.com/token" in url

    def test_sends_correct_grant_type(self):
        ok_resp = _mock_response(200, {"access_token": "new-tok"})
        with patch("app.integrations.google.mail_client.requests.post", return_value=ok_resp) as mock_post:
            refresh_access_token("rtoken", "cid", "csecret")
        data = mock_post.call_args.kwargs["data"]
        assert data["grant_type"] == "refresh_token"
        assert data["refresh_token"] == "rtoken"
        assert data["client_id"] == "cid"
        assert data["client_secret"] == "csecret"


# ---------------------------------------------------------------------------
# GoogleMailClient._can_refresh
# ---------------------------------------------------------------------------

class TestCanRefresh:
    def test_true_when_all_credentials_present(self):
        c = _client(refresh_token="r", client_id="ci", client_secret="cs")
        assert c._can_refresh() is True

    def test_false_when_refresh_token_missing(self):
        c = _client(refresh_token="", client_id="ci", client_secret="cs")
        assert c._can_refresh() is False

    def test_false_when_client_id_missing(self):
        c = _client(refresh_token="r", client_id="", client_secret="cs")
        assert c._can_refresh() is False

    def test_false_when_client_secret_missing(self):
        c = _client(refresh_token="r", client_id="ci", client_secret="")
        assert c._can_refresh() is False


# ---------------------------------------------------------------------------
# send_message refresh flow
# ---------------------------------------------------------------------------

_SEND_KWARGS = dict(
    to="test@example.com",
    subject="Test",
    body="Hello",
)


class TestSendMessageRefreshFlow:
    def test_no_refresh_on_success(self):
        """200 on first try — refresh_access_token must not be called."""
        c = _client_with_refresh()
        ok_resp = _mock_response(200, {"id": "msg-1", "threadId": "t-1", "labelIds": []})
        with patch.object(c, "_post_message", return_value=ok_resp) as mock_post, \
             patch("app.integrations.google.mail_client.refresh_access_token") as mock_refresh:
            c.send_message(**_SEND_KWARGS)
        mock_post.assert_called_once()
        mock_refresh.assert_not_called()

    def test_no_refresh_when_credentials_absent(self):
        """401 but no refresh credentials — should raise immediately."""
        c = _client(access_token="tok-expired")  # no refresh credentials
        unauth_resp = _mock_response(401, text="Unauthorized")
        with patch.object(c, "_post_message", return_value=unauth_resp), \
             patch("app.integrations.google.mail_client.refresh_access_token") as mock_refresh:
            with pytest.raises(RuntimeError, match="unauthorized"):
                c.send_message(**_SEND_KWARGS)
        mock_refresh.assert_not_called()

    def test_refresh_and_retry_on_401(self):
        """401 + credentials present → refresh → retry succeeds."""
        c = _client_with_refresh()
        unauth_resp = _mock_response(401, text="Unauthorized")
        ok_resp = _mock_response(200, {"id": "msg-2", "threadId": "t-2", "labelIds": []})

        with patch.object(c, "_post_message", side_effect=[unauth_resp, ok_resp]) as mock_post, \
             patch("app.integrations.google.mail_client.refresh_access_token", return_value="new-tok") as mock_refresh:
            result = c.send_message(**_SEND_KWARGS)

        assert mock_post.call_count == 2
        mock_refresh.assert_called_once_with(
            refresh_token="rtoken-123",
            client_id="client-id-abc",
            client_secret="client-secret-xyz",
        )
        assert c.access_token == "new-tok"
        assert result["status"] == "success"

    def test_raises_when_retry_also_fails(self):
        """401 → refresh → retry also 401 → RuntimeError."""
        c = _client_with_refresh()
        unauth_resp = _mock_response(401, text="Unauthorized")

        with patch.object(c, "_post_message", return_value=unauth_resp), \
             patch("app.integrations.google.mail_client.refresh_access_token", return_value="new-tok"):
            with pytest.raises(RuntimeError, match="unauthorized"):
                c.send_message(**_SEND_KWARGS)

    def test_no_refresh_on_403(self):
        """403 is a permissions error, not expiry — must not refresh."""
        c = _client_with_refresh()
        forbidden_resp = _mock_response(403, text="Forbidden")
        with patch.object(c, "_post_message", return_value=forbidden_resp) as mock_post, \
             patch("app.integrations.google.mail_client.refresh_access_token") as mock_refresh:
            with pytest.raises(RuntimeError, match="forbidden"):
                c.send_message(**_SEND_KWARGS)
        mock_post.assert_called_once()
        mock_refresh.assert_not_called()

    def test_updated_token_used_in_retry(self):
        """After refresh, the retry _post_message call uses the new token."""
        c = _client_with_refresh()
        unauth_resp = _mock_response(401, text="Unauthorized")
        ok_resp = _mock_response(200, {"id": "msg-3", "threadId": "t-3", "labelIds": []})

        with patch.object(c, "_post_message", side_effect=[unauth_resp, ok_resp]), \
             patch("app.integrations.google.mail_client.refresh_access_token", return_value="refreshed-tok"):
            c.send_message(**_SEND_KWARGS)

        # After send_message, client holds the new token
        assert c.access_token == "refreshed-tok"

    def test_raises_when_refresh_itself_fails(self):
        """If refresh_access_token raises, the error propagates."""
        c = _client_with_refresh()
        unauth_resp = _mock_response(401, text="Unauthorized")

        with patch.object(c, "_post_message", return_value=unauth_resp), \
             patch(
                 "app.integrations.google.mail_client.refresh_access_token",
                 side_effect=RuntimeError("Gmail token refresh failed (400): invalid_grant"),
             ):
            with pytest.raises(RuntimeError, match="token refresh failed"):
                c.send_message(**_SEND_KWARGS)


# ---------------------------------------------------------------------------
# GoogleMailAdapter — credentials threaded through
# ---------------------------------------------------------------------------

class TestGoogleMailAdapterRefreshCredentials:
    def test_refresh_credentials_passed_to_client(self):
        config = {
            "api_url": "https://gmail.googleapis.com/gmail/v1",
            "access_token": "tok",
            "user_id": "me",
            "refresh_token": "rtoken-abc",
            "client_id": "cid-abc",
            "client_secret": "csecret-abc",
        }
        adapter = GoogleMailAdapter(connection_config=config)
        assert adapter.client.refresh_token == "rtoken-abc"
        assert adapter.client.client_id == "cid-abc"
        assert adapter.client.client_secret == "csecret-abc"

    def test_missing_refresh_credentials_default_to_empty(self):
        config = {
            "api_url": "https://gmail.googleapis.com/gmail/v1",
            "access_token": "tok",
            "user_id": "me",
        }
        adapter = GoogleMailAdapter(connection_config=config)
        assert adapter.client.refresh_token == ""
        assert adapter.client.client_id == ""
        assert adapter.client.client_secret == ""
        assert adapter.client._can_refresh() is False


# ---------------------------------------------------------------------------
# service.py — connection config includes refresh keys
# ---------------------------------------------------------------------------

class TestServiceConnectionConfig:
    def test_google_mail_config_includes_refresh_keys(self):
        from app.integrations.service import get_integration_connection_config
        with patch("app.integrations.service.get_settings") as mock_settings:
            s = MagicMock()
            s.GOOGLE_MAIL_ACCESS_TOKEN = "tok"
            s.GOOGLE_MAIL_API_URL = "https://gmail.googleapis.com/gmail/v1"
            s.GOOGLE_MAIL_USER_ID = "me"
            s.GOOGLE_OAUTH_REFRESH_TOKEN = "rtoken"
            s.GOOGLE_OAUTH_CLIENT_ID = "cid"
            s.GOOGLE_OAUTH_CLIENT_SECRET = "csecret"
            mock_settings.return_value = s

            config = get_integration_connection_config("TENANT_1001", IntegrationType.GOOGLE_MAIL)

        assert config["refresh_token"] == "rtoken"
        assert config["client_id"] == "cid"
        assert config["client_secret"] == "csecret"
