"""
Tests for GoogleMailClient.list_messages and adapter list_messages dispatch.

Covers:
  - list_messages returns correctly shaped dicts (message_id, thread_id, from, subject, etc.)
  - max_results and query params are forwarded
  - 401 on list triggers token refresh then retries
  - API error on list raises RuntimeError
  - empty inbox returns empty list
  - adapter dispatches list_messages and wraps result correctly
  - adapter raises ValueError for unsupported action (not send_email or list_messages)
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call

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


def _list_response(msg_ids: list[str]) -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = {"messages": [{"id": i, "threadId": f"t{i}"} for i in msg_ids]}
    return r


def _detail_response(msg_id: str) -> MagicMock:
    r = MagicMock()
    r.status_code = 200
    r.json.return_value = {
        "id": msg_id,
        "threadId": f"t{msg_id}",
        "snippet": f"snippet for {msg_id}",
        "labelIds": ["INBOX"],
        "payload": {
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "Subject", "value": f"Subject {msg_id}"},
                {"name": "Date", "value": "Mon, 14 Apr 2026 10:00:00 +0000"},
            ]
        },
    }
    return r


# ── client: list_messages ─────────────────────────────────────────────────────

class TestListMessages:
    def test_returns_shaped_messages(self):
        client = _client()
        responses = [_list_response(["abc123"]), _detail_response("abc123")]

        with patch("requests.get", side_effect=responses):
            result = client.list_messages(max_results=5)

        assert len(result) == 1
        msg = result[0]
        assert msg["message_id"] == "abc123"
        assert msg["thread_id"] == "tabc123"
        assert msg["from"] == "sender@example.com"
        assert msg["subject"] == "Subject abc123"
        assert msg["received_at"] == "Mon, 14 Apr 2026 10:00:00 +0000"
        assert msg["snippet"] == "snippet for abc123"
        assert msg["label_ids"] == ["INBOX"]

    def test_max_results_forwarded(self):
        client = _client()
        captured_params = []

        def fake_get(url, headers, params, timeout):
            captured_params.append(params)
            if "messages/" in url:
                return _detail_response("id1")
            return _list_response(["id1"])

        with patch("requests.get", side_effect=fake_get):
            client.list_messages(max_results=3)

        assert captured_params[0]["maxResults"] == 3

    def test_query_forwarded_when_provided(self):
        client = _client()
        captured_params = []

        def fake_get(url, headers, params, timeout):
            captured_params.append(params)
            if "messages/" in url:
                return _detail_response("id1")
            return _list_response(["id1"])

        with patch("requests.get", side_effect=fake_get):
            client.list_messages(query="from:boss@example.com")

        assert captured_params[0].get("q") == "from:boss@example.com"

    def test_empty_inbox_returns_empty_list(self):
        client = _client()
        empty_response = MagicMock()
        empty_response.status_code = 200
        empty_response.json.return_value = {}

        with patch("requests.get", return_value=empty_response):
            result = client.list_messages()

        assert result == []

    def test_401_triggers_token_refresh_and_retry(self):
        client = _client()

        r401 = MagicMock()
        r401.status_code = 401

        call_count = {"n": 0}

        def fake_get(url, headers, params, timeout):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return r401
            if "messages/" in url:
                return _detail_response("id1")
            return _list_response(["id1"])

        with patch("requests.get", side_effect=fake_get), \
             patch(
                 "app.integrations.google.mail_client.refresh_access_token",
                 return_value="new-token",
             ) as mock_refresh:
            result = client.list_messages()

        mock_refresh.assert_called_once()
        assert len(result) == 1

    def test_api_error_raises_runtime_error(self):
        client = _client()
        r500 = MagicMock()
        r500.status_code = 500
        r500.text = "Internal Server Error"

        with patch("requests.get", return_value=r500):
            with pytest.raises(RuntimeError, match="Gmail API error"):
                client.list_messages()

    def test_multiple_messages_returned(self):
        client = _client()
        responses = [
            _list_response(["id1", "id2"]),
            _detail_response("id1"),
            _detail_response("id2"),
        ]

        with patch("requests.get", side_effect=responses):
            result = client.list_messages(max_results=2)

        assert len(result) == 2
        assert result[0]["message_id"] == "id1"
        assert result[1]["message_id"] == "id2"


# ── adapter: list_messages dispatch ──────────────────────────────────────────

class TestAdapterListMessages:
    def test_adapter_dispatches_list_messages(self):
        adapter = _adapter()
        adapter.client.list_messages = MagicMock(return_value=[
            {
                "message_id": "abc",
                "thread_id": "tabc",
                "from": "x@y.com",
                "subject": "Hello",
                "received_at": "Mon, 14 Apr 2026 10:00:00 +0000",
                "snippet": "Hi there",
                "label_ids": ["INBOX"],
            }
        ])

        result = adapter.execute_action("list_messages", {"max_results": 5})

        assert result["status"] == "success"
        assert result["action"] == "list_messages"
        assert result["count"] == 1
        assert result["messages"][0]["message_id"] == "abc"
        adapter.client.list_messages.assert_called_once_with(max_results=5, query="")

    def test_adapter_passes_query(self):
        adapter = _adapter()
        adapter.client.list_messages = MagicMock(return_value=[])

        adapter.execute_action("list_messages", {"query": "is:unread", "max_results": 3})

        adapter.client.list_messages.assert_called_once_with(max_results=3, query="is:unread")

    def test_adapter_defaults_max_results_to_10(self):
        adapter = _adapter()
        adapter.client.list_messages = MagicMock(return_value=[])

        adapter.execute_action("list_messages", {})

        adapter.client.list_messages.assert_called_once_with(max_results=10, query="")

    def test_adapter_rejects_unknown_action(self):
        adapter = _adapter()
        with pytest.raises(ValueError, match="Unsupported Google Mail action"):
            adapter.execute_action("delete_message", {})
