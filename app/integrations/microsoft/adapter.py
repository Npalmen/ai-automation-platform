from typing import Any

from app.integrations.base import BaseIntegrationAdapter
from app.integrations.microsoft.mail_client import MicrosoftMailClient
from app.integrations.microsoft.calendar_client import MicrosoftCalendarClient


class MicrosoftMailAdapter(BaseIntegrationAdapter):
    def __init__(self, connection_config: dict[str, Any] | None = None):
        super().__init__(connection_config=connection_config)

        access_token = self.connection_config.get("access_token")
        api_url = self.connection_config.get(
            "api_url",
            "https://graph.microsoft.com/v1.0",
        )

        if not access_token:
            raise ValueError("Missing microsoft mail access_token in connection_config.")

        self.client = MicrosoftMailClient(
            access_token=access_token,
            api_url=api_url,
        )

    def execute_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "send_email":
            to = payload.get("to", [])
            cc = payload.get("cc", [])
            bcc = payload.get("bcc", [])
            subject = payload.get("subject")
            body = payload.get("body", "")
            content_type = payload.get("content_type", "Text")

            if isinstance(to, str):
                to = [to]
            if isinstance(cc, str):
                cc = [cc]
            if isinstance(bcc, str):
                bcc = [bcc]

            if not to:
                raise ValueError("Missing 'to' for microsoft send_email action.")
            if not subject:
                raise ValueError("Missing 'subject' for microsoft send_email action.")

            message = {
                "subject": subject,
                "body": {
                    "contentType": content_type,
                    "content": body,
                },
                "toRecipients": [
                    {"emailAddress": {"address": email}} for email in to
                ],
                "ccRecipients": [
                    {"emailAddress": {"address": email}} for email in cc
                ],
                "bccRecipients": [
                    {"emailAddress": {"address": email}} for email in bcc
                ],
            }

            result = self.client.send_mail(message=message)

            return {
                "status": "success",
                "integration": "microsoft_mail",
                "action": action,
                "result": result,
            }

        raise ValueError(f"Unsupported microsoft mail action: {action}")

    def get_status(self) -> dict[str, Any]:
        result = self.client.get_me()

        return {
            "status": "connected",
            "integration": "microsoft_mail",
            "result": result,
        }


class MicrosoftCalendarAdapter(BaseIntegrationAdapter):
    def __init__(self, connection_config: dict[str, Any] | None = None):
        super().__init__(connection_config=connection_config)

        access_token = self.connection_config.get("access_token")
        api_url = self.connection_config.get(
            "api_url",
            "https://graph.microsoft.com/v1.0",
        )
        timezone = self.connection_config.get("timezone", "W. Europe Standard Time")

        if not access_token:
            raise ValueError("Missing microsoft calendar access_token in connection_config.")

        self.timezone = timezone
        self.client = MicrosoftCalendarClient(
            access_token=access_token,
            api_url=api_url,
        )

    def execute_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "create_calendar_event":
            subject = payload.get("summary") or payload.get("subject")
            start = payload.get("start")
            end = payload.get("end")
            body = payload.get("description", "")
            location = payload.get("location")
            attendees = payload.get("attendees", [])
            is_online_meeting = payload.get("is_online_meeting", False)

            if not subject:
                raise ValueError("Missing 'summary' or 'subject' for microsoft create_calendar_event action.")
            if not start:
                raise ValueError("Missing 'start' for microsoft create_calendar_event action.")
            if not end:
                raise ValueError("Missing 'end' for microsoft create_calendar_event action.")

            if isinstance(attendees, str):
                attendees = [attendees]

            event = {
                "subject": subject,
                "body": {
                    "contentType": "Text",
                    "content": body,
                },
                "start": {
                    "dateTime": start,
                    "timeZone": self.timezone,
                },
                "end": {
                    "dateTime": end,
                    "timeZone": self.timezone,
                },
                "location": {
                    "displayName": location,
                } if location else None,
                "attendees": [
                    {
                        "emailAddress": {"address": email},
                        "type": "required",
                    }
                    for email in attendees
                ],
                "isOnlineMeeting": is_online_meeting,
            }

            event = {k: v for k, v in event.items() if v not in (None, "", [])}

            result = self.client.create_event(event=event)

            return {
                "status": "success",
                "integration": "microsoft_calendar",
                "action": action,
                "result": result,
            }

        raise ValueError(f"Unsupported microsoft calendar action: {action}")

    def get_status(self) -> dict[str, Any]:
        result = self.client.get_me()

        return {
            "status": "connected",
            "integration": "microsoft_calendar",
            "result": result,
        }