"""
Focused tests for MondayClient.create_item column_values serialization
and MondayAdapter integration.

Covers:
  - create_item with no column_values (None) → sends "{}"
  - create_item with empty dict → sends "{}"
  - create_item with populated dict → sends json.dumps(dict)
  - create_item with pre-serialized string → passes through unchanged
  - GraphQL variable shape is correct (board_id str, column_values str)
  - monday API errors surface as RuntimeError with readable message, not raw list
  - adapter routes monday errors as RuntimeError (route will convert to 503)
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.integrations.monday.client import MondayClient
from app.integrations.monday.adapter import MondayAdapter


# ── helpers ──────────────────────────────────────────────────────────────────

def _client() -> MondayClient:
    return MondayClient(api_key="test-key", api_url="https://api.monday.com/v2")


def _adapter() -> MondayAdapter:
    return MondayAdapter(connection_config={
        "api_key": "test-key",
        "api_url": "https://api.monday.com/v2",
        "board_id": "123456789",
    })


def _success_response(item_id: str = "999") -> dict:
    return {
        "data": {
            "create_item": {
                "id": item_id,
                "name": "Test Item",
                "state": "active",
                "board": {"id": "123456789", "name": "Test Board"},
            }
        }
    }


# ── column_values serialization ───────────────────────────────────────────────

class TestCreateItemColumnValuesSerialization:
    """MondayClient must send column_values as a JSON string."""

    def _captured_variables(self, column_values_arg) -> dict:
        """Call create_item and return the variables dict sent to _post."""
        captured = {}

        def fake_post(query, variables=None):
            captured.update(variables or {})
            return _success_response()

        client = _client()
        client._post = fake_post
        client.create_item(board_id=123, item_name="Test", column_values=column_values_arg)
        return captured

    def test_none_sends_empty_json_string(self):
        variables = self._captured_variables(None)
        assert variables["column_values"] == "{}"

    def test_empty_dict_sends_empty_json_string(self):
        variables = self._captured_variables({})
        assert variables["column_values"] == "{}"

    def test_populated_dict_is_json_serialized(self):
        cv = {"text": "Erik Lindqvist", "status": {"label": "New"}}
        variables = self._captured_variables(cv)
        assert isinstance(variables["column_values"], str)
        parsed = json.loads(variables["column_values"])
        assert parsed == cv

    def test_string_passthrough_unchanged(self):
        cv_str = '{"text":"already a string"}'
        variables = self._captured_variables(cv_str)
        assert variables["column_values"] == cv_str

    def test_board_id_is_sent_as_string(self):
        variables = self._captured_variables(None)
        assert variables["board_id"] == "123"
        assert isinstance(variables["board_id"], str)

    def test_item_name_in_variables(self):
        captured = {}

        def fake_post(query, variables=None):
            captured.update(variables or {})
            return _success_response()

        client = _client()
        client._post = fake_post
        client.create_item(board_id=123, item_name="My New Item")
        assert captured["item_name"] == "My New Item"

    def test_group_id_none_by_default(self):
        captured = {}

        def fake_post(query, variables=None):
            captured.update(variables or {})
            return _success_response()

        client = _client()
        client._post = fake_post
        client.create_item(board_id=123, item_name="Test")
        assert captured["group_id"] is None

    def test_group_id_passed_when_provided(self):
        captured = {}

        def fake_post(query, variables=None):
            captured.update(variables or {})
            return _success_response()

        client = _client()
        client._post = fake_post
        client.create_item(board_id=123, item_name="Test", group_id="topics")
        assert captured["group_id"] == "topics"


# ── error handling ────────────────────────────────────────────────────────────

class TestMondayClientErrorHandling:
    """monday API errors should surface as RuntimeError with a readable message."""

    def test_api_errors_raise_runtime_error(self):
        client = _client()
        error_response = {
            "errors": [
                {"message": "Variable $column_values of type JSON was provided invalid value"},
                {"message": "Invalid type, expected a JSON string"},
            ]
        }

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = error_response

        with patch("requests.post", return_value=mock_response):
            with pytest.raises(RuntimeError) as exc_info:
                client.create_item(board_id=123, item_name="Test")

        assert "monday API error" in str(exc_info.value)
        assert "column_values" in str(exc_info.value)

    def test_single_error_message_readable(self):
        client = _client()
        error_response = {"errors": [{"message": "Board not found"}]}

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = error_response

        with patch("requests.post", return_value=mock_response):
            with pytest.raises(RuntimeError) as exc_info:
                client.get_me()

        assert "Board not found" in str(exc_info.value)

    def test_empty_errors_list_does_not_raise(self):
        client = _client()
        ok_response = {"data": {"me": {"id": "1", "name": "Test", "email": "t@t.com"}}, "errors": []}

        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = ok_response

        with patch("requests.post", return_value=mock_response):
            result = client.get_me()  # should not raise

        assert result["data"]["me"]["name"] == "Test"


# ── adapter routing ───────────────────────────────────────────────────────────

class TestMondayAdapterCreateItem:
    """Adapter should pass column_values through and surface errors correctly."""

    def test_create_item_no_column_values_succeeds(self):
        adapter = _adapter()
        adapter.client.create_item = MagicMock(return_value=_success_response("42"))

        result = adapter.execute_action("create_item", {"item_name": "Test Item"})

        assert result["status"] == "success"
        assert result["item_id"] == "42"
        adapter.client.create_item.assert_called_once_with(
            board_id=123456789,
            item_name="Test Item",
            group_id=None,
            column_values={},  # adapter passes {} when not in payload; client serializes
        )

    def test_create_item_with_dict_column_values(self):
        adapter = _adapter()
        cv = {"text": "Erik", "status": {"label": "New"}}
        adapter.client.create_item = MagicMock(return_value=_success_response("77"))

        result = adapter.execute_action("create_item", {"item_name": "Lead", "column_values": cv})

        assert result["status"] == "success"
        assert result["item_id"] == "77"
        adapter.client.create_item.assert_called_once_with(
            board_id=123456789,
            item_name="Lead",
            group_id=None,
            column_values=cv,
        )

    def test_create_item_missing_item_name_raises_value_error(self):
        adapter = _adapter()
        with pytest.raises(ValueError, match="item_name"):
            adapter.execute_action("create_item", {})

    def test_create_item_monday_api_error_surfaces_as_runtime_error(self):
        adapter = _adapter()
        adapter.client.create_item = MagicMock(
            side_effect=RuntimeError("monday API error: Board not found")
        )
        with pytest.raises(RuntimeError, match="monday API error"):
            adapter.execute_action("create_item", {"item_name": "Test"})

    def test_unsupported_action_raises_value_error(self):
        adapter = _adapter()
        with pytest.raises(ValueError, match="Unsupported monday action"):
            adapter.execute_action("delete_item", {})


# ── HTTP-level failure handling ───────────────────────────────────────────────

class TestMondayClientHttpErrors:
    """HTTP-level errors (429, 403, 503) must surface as HTTPError, not be swallowed."""

    def _error_response(self, status_code: int) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        from requests.exceptions import HTTPError
        resp.raise_for_status.side_effect = HTTPError(
            f"{status_code} Error", response=resp
        )
        return resp

    def test_429_rate_limit_raises_http_error(self):
        """Monday rate-limit (429) must propagate, not be silently ignored."""
        from requests.exceptions import HTTPError
        client = _client()
        with patch("requests.post", return_value=self._error_response(429)):
            with pytest.raises(HTTPError):
                client.create_item(board_id=123, item_name="Test")

    def test_403_permission_raises_http_error(self):
        """Monday permission error (403) must propagate."""
        from requests.exceptions import HTTPError
        client = _client()
        with patch("requests.post", return_value=self._error_response(403)):
            with pytest.raises(HTTPError):
                client.create_item(board_id=123, item_name="Test")

    def test_503_service_unavailable_raises_http_error(self):
        """Monday service unavailable (503) must propagate."""
        from requests.exceptions import HTTPError
        client = _client()
        with patch("requests.post", return_value=self._error_response(503)):
            with pytest.raises(HTTPError):
                client.create_item(board_id=123, item_name="Test")

    def test_bad_board_id_surfaces_as_monday_api_error(self):
        """Monday returns an error payload for a non-existent board ID."""
        client = _client()
        error_response = {"errors": [{"message": "Board not found"}]}
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = error_response
        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="Board not found"):
                client.create_item(board_id=99999999, item_name="Test")

    def test_missing_column_in_payload_surfaces_as_monday_api_error(self):
        """Monday returns an error if a required column is missing from column_values."""
        client = _client()
        error_response = {"errors": [{"message": "Column 'status' is required"}]}
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = error_response
        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="Column 'status' is required"):
                client.create_item(board_id=123, item_name="Test", column_values={})

    def test_adapter_propagates_http_error_from_client(self):
        """Adapter must not swallow HTTPError from client — it propagates for route to handle."""
        from requests.exceptions import HTTPError
        adapter = _adapter()
        adapter.client.create_item = MagicMock(
            side_effect=HTTPError("429 Too Many Requests")
        )
        with pytest.raises(HTTPError):
            adapter.execute_action("create_item", {"item_name": "Test"})
