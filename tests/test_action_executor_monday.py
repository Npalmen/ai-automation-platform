"""
Tests for create_monday_item action in action_executor.

Covers:
  - create_monday_item in SUPPORTED_ACTIONS
  - routes to MondayAdapter when configured (api_key + board_id present)
  - falls back to stub when Monday not configured
  - item_name is required
  - column_values and group_id are optional, passed through
  - is_integration_configured returns True for api_key + board_id config
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.workflows.action_executor import SUPPORTED_ACTIONS, execute_action
from app.integrations.service import is_integration_configured


# ── SUPPORTED_ACTIONS ─────────────────────────────────────────────────────────

def test_create_monday_item_in_supported_actions():
    assert "create_monday_item" in SUPPORTED_ACTIONS


# ── is_integration_configured for Monday ─────────────────────────────────────

def test_monday_configured_when_api_key_and_board_id_present():
    config = {"api_key": "test-key", "board_id": "123456789", "api_url": "https://api.monday.com/v2"}
    assert is_integration_configured(config) is True


def test_monday_not_configured_when_api_key_missing():
    config = {"board_id": "123456789", "api_url": "https://api.monday.com/v2"}
    assert is_integration_configured(config) is False


def test_monday_not_configured_when_board_id_missing():
    config = {"api_key": "test-key", "api_url": "https://api.monday.com/v2"}
    assert is_integration_configured(config) is False


# ── execute_action routing ────────────────────────────────────────────────────

_MONDAY_CONFIG = {
    "api_key": "test-key",
    "api_url": "https://api.monday.com/v2",
    "board_id": "123456789",
}

_MONDAY_ADAPTER_RESULT = {
    "status": "success",
    "integration": "monday",
    "action": "create_item",
    "item_id": "999",
    "result": {"data": {"create_item": {"id": "999"}}},
}


def _run_monday_action(extra: dict | None = None):
    action = {
        "type": "create_monday_item",
        "item_name": "Lead: Erik Lindqvist – Solar inquiry",
        "tenant_id": "TENANT_1001",
    }
    if extra:
        action.update(extra)

    mock_adapter = MagicMock()
    mock_adapter.execute_action.return_value = _MONDAY_ADAPTER_RESULT

    with patch(
        "app.workflows.action_executor.get_integration_connection_config",
        return_value=_MONDAY_CONFIG,
    ), patch(
        "app.workflows.action_executor.is_integration_configured",
        return_value=True,
    ), patch(
        "app.workflows.action_executor.get_integration_adapter",
        return_value=mock_adapter,
    ):
        return execute_action(action), mock_adapter


def test_create_monday_item_routes_to_adapter():
    result, mock_adapter = _run_monday_action()

    assert result["type"] == "create_monday_item"
    assert result["status"] == "executed"
    assert result["provider"] == "monday"
    assert result["target"] == "Lead: Erik Lindqvist – Solar inquiry"
    assert result["integration_result"]["item_id"] == "999"

    mock_adapter.execute_action.assert_called_once_with(
        action="create_item",
        payload={
            "item_name": "Lead: Erik Lindqvist – Solar inquiry",
            "column_values": {},
            "group_id": None,
        },
    )


def test_create_monday_item_passes_column_values():
    cv = {"text": "Erik Lindqvist", "status": {"label": "New"}}
    result, mock_adapter = _run_monday_action({"column_values": cv})

    call_payload = mock_adapter.execute_action.call_args[1]["payload"]
    assert call_payload["column_values"] == cv


def test_create_monday_item_passes_group_id():
    result, mock_adapter = _run_monday_action({"group_id": "topics"})

    call_payload = mock_adapter.execute_action.call_args[1]["payload"]
    assert call_payload["group_id"] == "topics"


def test_create_monday_item_missing_item_name_raises():
    action = {"type": "create_monday_item", "tenant_id": "TENANT_1001"}
    with pytest.raises(ValueError, match="item_name"):
        execute_action(action)


def test_create_monday_item_falls_back_to_stub_when_not_configured():
    action = {
        "type": "create_monday_item",
        "item_name": "Test Item",
        "tenant_id": "TENANT_1001",
    }

    with patch(
        "app.workflows.action_executor.get_integration_connection_config",
        return_value={"api_key": None, "board_id": None},
    ), patch(
        "app.workflows.action_executor.is_integration_configured",
        return_value=False,
    ):
        result = execute_action(action)

    assert result["status"] == "executed"
    assert result["provider"] == "internal_stub"
    assert "monday" in result["integration_result"].get("message", "").lower() or \
           result["integration_result"].get("provider") == "internal_stub"
