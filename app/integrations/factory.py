# app/integrations/factory.py
from app.integrations.base import BaseIntegrationAdapter
from app.integrations.enums import IntegrationType
from app.integrations.fortnox.adapter import FortnoxAdapter
from app.integrations.google.adapter import GoogleCalendarAdapter, GoogleMailAdapter
from app.integrations.microsoft.adapter import MicrosoftCalendarAdapter, MicrosoftMailAdapter
from app.integrations.monday.adapter import MondayAdapter
from app.integrations.slack.adapter import SlackAdapter
from app.integrations.visma.adapter import VismaAdapter


class WebhookPassthroughAdapter(BaseIntegrationAdapter):
    def execute_action(self, action: str, payload: dict) -> dict:
        return {
            "status": "success",
            "integration": self.connection_config.get("name", "webhook"),
            "action": action,
            "payload": payload,
            "message": "Generic webhook adapter placeholder.",
        }

    def get_status(self) -> dict:
        return {
            "status": "connected",
            "integration": self.connection_config.get("name", "webhook"),
            "message": "Generic webhook adapter placeholder.",
        }


def get_integration_adapter(
    integration_type: IntegrationType,
    connection_config: dict | None = None,
) -> BaseIntegrationAdapter:
    if integration_type == IntegrationType.SLACK:
        return SlackAdapter(connection_config=connection_config)

    if integration_type == IntegrationType.MONDAY:
        return MondayAdapter(connection_config=connection_config)

    if integration_type == IntegrationType.FORTNOX:
        return FortnoxAdapter(connection_config=connection_config)

    if integration_type == IntegrationType.VISMA:
        return VismaAdapter(connection_config=connection_config)

    if integration_type == IntegrationType.GOOGLE_MAIL:
        return GoogleMailAdapter(connection_config=connection_config)

    if integration_type == IntegrationType.GOOGLE_CALENDAR:
        return GoogleCalendarAdapter(connection_config=connection_config)

    if integration_type == IntegrationType.MICROSOFT_MAIL:
        return MicrosoftMailAdapter(connection_config=connection_config)

    if integration_type == IntegrationType.MICROSOFT_CALENDAR:
        return MicrosoftCalendarAdapter(connection_config=connection_config)

    if integration_type == IntegrationType.CRM:
        return WebhookPassthroughAdapter(
            connection_config={
                **(connection_config or {}),
                "name": "crm",
            }
        )

    if integration_type == IntegrationType.ACCOUNTING:
        return WebhookPassthroughAdapter(
            connection_config={
                **(connection_config or {}),
                "name": "accounting",
            }
        )

    if integration_type == IntegrationType.SUPPORT:
        return WebhookPassthroughAdapter(
            connection_config={
                **(connection_config or {}),
                "name": "support",
            }
        )

    raise ValueError(f"Unsupported integration type: {integration_type}")