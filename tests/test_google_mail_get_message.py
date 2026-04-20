"""
Tests for GoogleMailClient.get_message and adapter get_message dispatch.

Covers:
  - get_message returns all required fields
  - body_text extracted from text/plain single-part message
  - body_text extracted from text/plain part inside multipart/alternative
  - body_text is empty string when no text/plain part exists (html-only)
  - message_id is required — raises ValueError when missing
  - 401 triggers token refresh and retry
  - API error raises RuntimeError
  - adapter dispatches get_message correctly
  - adapter raises ValueError when message_id missing from payload
"""
from __future__ import annotations

import base64
from unittest.mock import MagicMock, patch

import pytest

from app.integrations.google.mail_client import GoogleMailClient
from app.integrations.google.adapter import GoogleMailAdapter


# ── helpers ───────────────────────────────────────────────────────────────────

def _client() -> GoogleMailClient:
    return GoogleMailClient(
        api_url="https://gmail.googleapis.com/gmail/v1",
        access_token="test-token",
        user_id="me",
        refresh_token="ref-token",
        client_id="client-id",
        client_secret="client-secret",
    )


def _adapter() -> GoogleMailAdapter:
    return GoogleMailAdapter(connection_config={
        "api_url": "https://gmail.googleapis.com/gmail/v1",
        "access_token": "test-token",
        "user_id": "me",
        "refresh_token": "ref-token",
        "client_id": "client-id",
        "client_secret": "client-secret",
    })


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def _full_response(
    msg_id: str = "abc123",
    body_text: str = "Hello from sender.",
    mime_type: str = "text/plain",
    multipart: bool = False,
) -> MagicMock:
    if multipart:
        payload = {
            "mimeType": "multipart/alternative",
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "recipient@example.com"},
                {"name": "Subject", "value": "Test subject"},
                {"name": "Date", "value": "Mon, 14 Apr 2026 10:00:00 +0000"},
            ],
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {"data": _b64(body_text)},
                    "parts": [],
                },
                {
                    "mimeType": "text/html",
                    "body": {"data": _b64("<p>Hello</p>")},
                    "parts": [],
                },
            ],
        }
    else:
        payload = {
            "mimeType": mime_type,
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "To", "value": "recipient@example.com"},
                {"name": "Subject", "value": "Test subject"},
                {"name": "Date", "value": "Mon, 14 Apr 2026 10:00:00 +0000"},
            ],
            "body": {"data": _b64(body_text)},
            "parts": [],
        }

    r = MagicMock()
    r.status_code = 200
    r.json.return_value = {
        "id": msg_id,
        "threadId": f"t{msg_id}",
        "snippet": "Hello from sender...",
        "labelIds": ["INBOX", "UNREAD"],
        "payload": payload,
    }
    return r


# ── client: get_message ───────────────────────────────────────────────────────

class TestGetMessage:
    def test_returns_all_required_fields(self):
        client = _client()
        with patch("requests.get", return_value=_full_response()):
            result = client.get_message("abc123")

        assert result["message_id"] == "abc123"
        assert result["thread_id"] == "tabc123"
        assert result["from"] == "sender@example.com"
        assert result["to"] == "recipient@example.com"
        assert result["subject"] == "Test subject"
        assert result["received_at"] == "Mon, 14 Apr 2026 10:00:00 +0000"
        assert result["snippet"] == "Hello from sender..."
        assert result["label_ids"] == ["INBOX", "UNREAD"]
        assert "body_text" in result

    def test_body_text_extracted_from_plain_single_part(self):
        client = _client()
        with patch("requests.get", return_value=_full_response(body_text="Plain body here.")):
            result = client.get_message("abc123")

        assert result["body_text"] == "Plain body here."

    def test_body_text_extracted_from_multipart_alternative(self):
        client = _client()
        with patch("requests.get", return_value=_full_response(body_text="Plain part text.", multipart=True)):
            result = client.get_message("abc123")

        assert result["body_text"] == "Plain part text."

    def test_body_text_empty_when_html_only(self):
        client = _client()
        # Simulate html-only: mime_type=text/html, no text/plain part
        r = _full_response(body_text="<p>HTML only</p>", mime_type="text/html")
        with patch("requests.get", return_value=r):
            result = client.get_message("abc123")

        assert result["body_text"] == ""

    def test_uses_format_full_param(self):
        client = _client()
        captured = {}

        def fake_get(url, headers, params, timeout):
            captured.update(params or {})
            return _full_response()

        with patch("requests.get", side_effect=fake_get):
            client.get_message("abc123")

        assert captured.get("format") == "full"

    def test_missing_message_id_raises_value_error(self):
        client = _client()
        with pytest.raises(ValueError, match="message_id is required"):
            client.get_message("")

    def test_whitespace_message_id_raises_value_error(self):
        client = _client()
        with pytest.raises(ValueError, match="message_id is required"):
            client.get_message("   ")

    def test_401_triggers_token_refresh_and_retry(self):
        client = _client()
        r401 = MagicMock()
        r401.status_code = 401
        call_count = {"n": 0}

        def fake_get(url, headers, params, timeout):
            call_count["n"] += 1
            return r401 if call_count["n"] == 1 else _full_response()

        with patch("requests.get", side_effect=fake_get), \
             patch(
                 "app.integrations.google.mail_client.refresh_access_token",
                 return_value="new-token",
             ) as mock_refresh:
            result = client.get_message("abc123")

        mock_refresh.assert_called_once()
        assert result["message_id"] == "abc123"

    def test_api_error_raises_runtime_error(self):
        client = _client()
        r404 = MagicMock()
        r404.status_code = 404
        r404.text = "Message not found"

        with patch("requests.get", return_value=r404):
            with pytest.raises(RuntimeError, match="Gmail API error"):
                client.get_message("nonexistent")


# ── adapter: get_message dispatch ─────────────────────────────────────────────

class TestAdapterGetMessage:
    def test_adapter_dispatches_get_message(self):
        adapter = _adapter()
        expected = {
            "message_id": "abc123",
            "thread_id": "tabc123",
            "from": "sender@example.com",
            "to": "recipient@example.com",
            "subject": "Test subject",
            "received_at": "Mon, 14 Apr 2026 10:00:00 +0000",
            "snippet": "Hello...",
            "label_ids": ["INBOX"],
            "body_text": "Hello from sender.",
        }
        adapter.client.get_message = MagicMock(return_value=expected)

        result = adapter.execute_action("get_message", {"message_id": "abc123"})

        assert result["status"] == "success"
        assert result["action"] == "get_message"
        assert result["message"] == expected
        adapter.client.get_message.assert_called_once_with(message_id="abc123")

    def test_adapter_raises_when_message_id_missing(self):
        adapter = _adapter()
        with pytest.raises(ValueError, match="message_id"):
            adapter.execute_action("get_message", {})
