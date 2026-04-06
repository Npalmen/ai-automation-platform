from __future__ import annotations

from typing import Any

from app.integrations.base import BaseIntegrationAdapter
from app.integrations.google.calendar_client import GoogleCalendarClient
from app.integrations.google.mail_client import GoogleMailClient


class GoogleMailAdapter(BaseIntegrationAdapter):
    def __init__(self, connection_config: dict[str, Any] | None = None):
        super().__init__(connection_config=connection_config)

        self.client = GoogleMailClient(
            api_url=str(self.connection_config.get("api_url") or "").strip(),
            access_token=str(self.connection_config.get("access_token") or "").strip(),
            user_id=str(self.connection_config.get("user_id") or "me").strip(),
            timeout_seconds=int(self.connection_config.get("timeout_seconds") or 30),
        )

    def execute_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action != "send_email":
            raise ValueError(f"Unsupported Google Mail action '{action}'.")

        to = payload.get("to")
        subject = payload.get("subject")
        body = payload.get("body")

        if not to:
            raise ValueError("Google Mail payload requires 'to'.")
        if not subject:
            raise ValueError("Google Mail payload requires 'subject'.")
        if body is None:
            raise ValueError("Google Mail payload requires 'body'.")

        result = self.client.send_message(
            to=to,
            subject=str(subject),
            body=str(body),
            cc=payload.get("cc"),
            bcc=payload.get("bcc"),
            html_body=payload.get("html_body"),
            from_email=payload.get("from_email"),
            from_name=payload.get("from_name"),
        )

        return {
            "status": result["status"],
            "integration": "google_mail",
            "provider": result["provider"],
            "action": action,
            "payload": result["payload"],
            "message": result["message"],
            "external_id": result.get("external_id"),
        }

    def get_status(self) -> dict[str, Any]:
        is_configured = bool(
            self.connection_config.get("api_url")
            and self.connection_config.get("access_token")
            and self.connection_config.get("user_id")
        )

        return {
            "status": "connected" if is_configured else "not_configured",
            "integration": "google_mail",
            "provider": "google_mail",
            "message": (
                "Google Mail integration ready."
                if is_configured
                else "Google Mail integration is not configured."
            ),
        }


class GoogleCalendarAdapter(BaseIntegrationAdapter):
    def __init__(self, connection_config: dict[str, Any] | None = None):
        super().__init__(connection_config=connection_config)

        self.client = GoogleCalendarClient(
            api_url=str(self.connection_config.get("api_url") or "").strip(),
            access_token=str(self.connection_config.get("access_token") or "").strip(),
            calendar_id=str(self.connection_config.get("calendar_id") or "primary").strip(),
        )

    def execute_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "create_event":
            result = self.client.create_event(payload)
            return {
                "status": "success",
                "integration": "google_calendar",
                "provider": "google_calendar",
                "action": action,
                "payload": result,
                "message": "Google Calendar event created successfully.",
                "external_id": result.get("id"),
            }

        raise ValueError(f"Unsupported Google Calendar action '{action}'.")

    def get_status(self) -> dict[str, Any]:
        is_configured = bool(
            self.connection_config.get("api_url")
            and self.connection_config.get("access_token")
            and self.connection_config.get("calendar_id")
        )

        return {
            "status": "connected" if is_configured else "not_configured",
            "integration": "google_calendar",
            "provider": "google_calendar",
            "message": (
                "Google Calendar integration ready."
                if is_configured
                else "Google Calendar integration is not configured."
            ),
        }