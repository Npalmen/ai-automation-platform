import base64
from typing import Any

from app.integrations.base import BaseIntegrationAdapter
from app.integrations.google.mail_client import GoogleMailClient
from app.integrations.google.calendar_client import GoogleCalendarClient


class GoogleMailAdapter(BaseIntegrationAdapter):
    def __init__(self, connection_config: dict[str, Any] | None = None):
        super().__init__(connection_config=connection_config)

        access_token = self.connection_config.get("access_token")
        api_url = self.connection_config.get(
            "api_url",
            "https://gmail.googleapis.com/gmail/v1",
        )
        user_id = self.connection_config.get("user_id", "me")

        if not access_token:
            raise ValueError("Missing google mail access_token in connection_config.")

        self.user_id = user_id
        self.client = GoogleMailClient(
            access_token=access_token,
            api_url=api_url,
        )

    def execute_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "send_email":
            to = payload.get("to")
            subject = payload.get("subject")
            body = payload.get("body", "")
            cc = payload.get("cc")
            bcc = payload.get("bcc")
            from_email = payload.get("from_email")

            if not to:
                raise ValueError("Missing 'to' for google send_email action.")
            if not subject:
                raise ValueError("Missing 'subject' for google send_email action.")

            lines = []
            if from_email:
                lines.append(f"From: {from_email}")
            lines.append(f"To: {to}")
            if cc:
                lines.append(f"Cc: {cc}")
            if bcc:
                lines.append(f"Bcc: {bcc}")
            lines.append("Content-Type: text/plain; charset=utf-8")
            lines.append("MIME-Version: 1.0")
            lines.append(f"Subject: {subject}")
            lines.append("")
            lines.append(body)

            raw_message = "\r\n".join(lines)
            raw_message_base64 = base64.urlsafe_b64encode(
                raw_message.encode("utf-8")
            ).decode("utf-8")

            result = self.client.send_message(
                raw_message_base64=raw_message_base64,
                user_id=self.user_id,
            )

            return {
                "status": "success",
                "integration": "google_mail",
                "action": action,
                "result": result,
            }

        raise ValueError(f"Unsupported google mail action: {action}")

    def get_status(self) -> dict[str, Any]:
        result = self.client.get_profile(user_id=self.user_id)

        return {
            "status": "connected",
            "integration": "google_mail",
            "result": result,
        }


class GoogleCalendarAdapter(BaseIntegrationAdapter):
    def __init__(self, connection_config: dict[str, Any] | None = None):
        super().__init__(connection_config=connection_config)

        access_token = self.connection_config.get("access_token")
        api_url = self.connection_config.get(
            "api_url",
            "https://www.googleapis.com/calendar/v3",
        )
        calendar_id = self.connection_config.get("calendar_id", "primary")

        if not access_token:
            raise ValueError("Missing google calendar access_token in connection_config.")

        self.calendar_id = calendar_id
        self.client = GoogleCalendarClient(
            access_token=access_token,
            api_url=api_url,
        )

    def execute_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "create_calendar_event":
            summary = payload.get("summary")
            start = payload.get("start")
            end = payload.get("end")
            description = payload.get("description")
            location = payload.get("location")
            attendees = payload.get("attendees", [])
            conference_data = payload.get("conferenceData")
            timezone = payload.get("timezone", "Europe/Stockholm")

            if not summary:
                raise ValueError("Missing 'summary' for google create_calendar_event action.")
            if not start:
                raise ValueError("Missing 'start' for google create_calendar_event action.")
            if not end:
                raise ValueError("Missing 'end' for google create_calendar_event action.")

            event = {
                "summary": summary,
                "description": description,
                "location": location,
                "start": {
                    "dateTime": start,
                    "timeZone": timezone,
                },
                "end": {
                    "dateTime": end,
                    "timeZone": timezone,
                },
                "attendees": [{"email": email} for email in attendees],
            }

            if conference_data:
                event["conferenceData"] = conference_data

            event = {k: v for k, v in event.items() if v not in (None, "", [])}

            result = self.client.create_event(
                calendar_id=self.calendar_id,
                event=event,
            )

            return {
                "status": "success",
                "integration": "google_calendar",
                "action": action,
                "result": result,
            }

        raise ValueError(f"Unsupported google calendar action: {action}")

    def get_status(self) -> dict[str, Any]:
        result = self.client.get_calendar(calendar_id=self.calendar_id)

        return {
            "status": "connected",
            "integration": "google_calendar",
            "result": result,
        }