# app/integrations/slack/adapter.py
from __future__ import annotations

from typing import Any

from app.integrations.base import BaseIntegrationAdapter
from app.integrations.slack.webhook_client import SlackWebhookClient


class SlackAdapter(BaseIntegrationAdapter):
    def __init__(self, connection_config: dict[str, Any] | None = None):
        super().__init__(connection_config=connection_config)

    def execute_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        provider = str(self.connection_config.get("provider") or "webhook").strip().lower()

        if action != "notify_slack":
            raise ValueError(f"Unsupported slack action '{action}'.")

        if provider == "webhook":
            client = SlackWebhookClient(connection_config=self.connection_config)
            result = client.send_message(payload=payload)
            return {
                "status": result["status"],
                "integration": "slack",
                "provider": result["provider"],
                "action": action,
                "payload": result["payload"],
                "message": result["message"],
                "external_id": result.get("external_id"),
            }

        raise ValueError(f"Unsupported slack provider '{provider}'.")

    def get_status(self) -> dict[str, Any]:
        provider = str(self.connection_config.get("provider") or "webhook").strip().lower()

        if provider == "webhook":
            is_configured = bool(self.connection_config.get("webhook_url"))
            return {
                "status": "connected" if is_configured else "not_configured",
                "integration": "slack",
                "provider": "webhook",
                "message": "Slack webhook integration ready." if is_configured else "Slack webhook integration is not configured.",
            }

        return {
            "status": "not_configured",
            "integration": "slack",
            "provider": provider,
            "message": f"Unsupported slack provider '{provider}'.",
        }