from __future__ import annotations

import logging
from typing import Any

from app.integrations.base import BaseIntegrationAdapter
from app.integrations.google.calendar_client import GoogleCalendarClient
from app.integrations.google.mail_client import GoogleMailClient

logger = logging.getLogger(__name__)


def _mask(value: str, prefix_len: int = 8) -> str:
    """Return a masked representation for logging — never logs the full value."""
    if not value:
        return "<not set>"
    return f"{value[:prefix_len]}..." if len(value) > prefix_len else "<set, short>"


class GoogleMailAdapter(BaseIntegrationAdapter):
    def __init__(self, connection_config: dict[str, Any] | None = None):
        super().__init__(connection_config=connection_config)

        self.client = GoogleMailClient(
            api_url=str(self.connection_config.get("api_url") or "").strip(),
            access_token=str(self.connection_config.get("access_token") or "").strip(),
            user_id=str(self.connection_config.get("user_id") or "me").strip(),
            timeout_seconds=int(self.connection_config.get("timeout_seconds") or 30),
            refresh_token=str(self.connection_config.get("refresh_token") or "").strip(),
            client_id=str(self.connection_config.get("client_id") or "").strip(),
            client_secret=str(self.connection_config.get("client_secret") or "").strip(),
        )

    def _log_config_diagnostics(self) -> None:
        """Log masked presence of OAuth credentials to assist debugging without leaking secrets."""
        cfg = self.connection_config
        access_token = str(cfg.get("access_token") or "")
        refresh_token = str(cfg.get("refresh_token") or "")
        client_id = str(cfg.get("client_id") or "")
        client_secret = str(cfg.get("client_secret") or "")

        logger.info(
            "[GoogleMail] OAuth config diagnostics: "
            "access_token=%s refresh_token=%s client_id=%s client_secret=%s",
            _mask(access_token),
            _mask(refresh_token),
            _mask(client_id),
            _mask(client_secret),
        )

        # Warn about incomplete refresh credential set — a common misconfiguration.
        refresh_fields = [refresh_token, client_id, client_secret]
        refresh_set = sum(bool(f) for f in refresh_fields)
        if 0 < refresh_set < 3:
            logger.warning(
                "[GoogleMail] Incomplete OAuth refresh credentials: "
                "%d of 3 fields set (GOOGLE_OAUTH_REFRESH_TOKEN, "
                "GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET). "
                "Token refresh will fail with invalid_grant. "
                "Set all three or none.",
                refresh_set,
            )

    def execute_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._log_config_diagnostics()

        if action == "list_messages":
            max_results = int(payload.get("max_results") or 10)
            query = str(payload.get("query") or "")
            messages = self.client.list_messages(max_results=max_results, query=query)
            return {
                "status": "success",
                "integration": "google_mail",
                "provider": "google_mail",
                "action": action,
                "count": len(messages),
                "messages": messages,
            }

        if action == "get_message":
            message_id = payload.get("message_id")
            if not message_id:
                raise ValueError("get_message requires 'message_id' in payload.")
            message = self.client.get_message(message_id=str(message_id))
            return {
                "status": "success",
                "integration": "google_mail",
                "provider": "google_mail",
                "action": action,
                "message": message,
            }

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