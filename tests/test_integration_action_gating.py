"""
Regression tests for allowed_integrations fail-closed gating in action_executor.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.workflows.action_executor import execute_action


_MONDAY_CONFIG = {
    "api_key": "test-key",
    "api_url": "https://api.monday.com/v2",
    "board_id": "123456789",
}


class TestIntegrationActionGating:
    def test_monday_blocked_when_not_allowed(self):
        action = {
            "type": "create_monday_item",
            "item_name": "Lead: Demo",
            "tenant_id": "T_DEMO_ONLY_GMAIL",
        }
        mock_adapter = MagicMock()

        with (
            patch(
                "app.integrations.policies.get_tenant_config",
                return_value={"allowed_integrations": ["google_mail"]},
            ),
            patch(
                "app.workflows.action_executor.get_integration_connection_config",
                return_value=_MONDAY_CONFIG,
            ),
            patch(
                "app.workflows.action_executor.is_integration_configured",
                return_value=True,
            ),
            patch(
                "app.workflows.action_executor.get_integration_adapter",
                return_value=mock_adapter,
            ),
        ):
            result = execute_action(action)

        mock_adapter.execute_action.assert_not_called()
        assert result["status"] == "skipped"
        assert result["skip_reason"] == "integration_not_allowed"
        assert result["integration_result"]["reason"] == "integration_not_allowed"

    def test_monday_executes_when_allowed(self):
        action = {
            "type": "create_monday_item",
            "item_name": "Lead: Demo",
            "tenant_id": "TENANT_1001",
        }
        mock_adapter = MagicMock()
        mock_adapter.execute_action.return_value = {
            "status": "success",
            "integration": "monday",
            "action": "create_item",
            "item_id": "1",
        }

        with (
            patch(
                "app.workflows.action_executor.get_integration_connection_config",
                return_value=_MONDAY_CONFIG,
            ),
            patch(
                "app.workflows.action_executor.is_integration_configured",
                return_value=True,
            ),
            patch(
                "app.workflows.action_executor.get_integration_adapter",
                return_value=mock_adapter,
            ),
        ):
            result = execute_action(action)

        mock_adapter.execute_action.assert_called_once()
        assert result["status"] == "executed"

    def test_email_blocked_when_google_mail_not_allowed(self):
        action = {
            "type": "send_customer_auto_reply",
            "tenant_id": "T_DEMO_ONLY_MONDAY",
            "to": "customer@example.com",
            "subject": "Hej",
            "body": "Tack",
        }

        with patch(
            "app.integrations.policies.get_tenant_config",
            return_value={"allowed_integrations": ["monday"]},
        ):
            result = execute_action(action)

        assert result["status"] == "skipped"
        assert result["skip_reason"] == "integration_not_allowed"
