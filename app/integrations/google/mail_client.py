from __future__ import annotations

import base64
import logging
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any

import requests


logger = logging.getLogger(__name__)


class GoogleMailClient:
    def __init__(
        self,
        api_url: str,
        access_token: str,
        user_id: str = "me",
        timeout_seconds: int = 30,
    ):
        self.api_url = api_url.rstrip("/")
        self.access_token = access_token
        self.user_id = user_id
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _normalize_recipients(value: str | list[str] | None) -> list[str]:
        if value is None:
            return []

        if isinstance(value, str):
            parts = [item.strip() for item in value.split(",")]
            return [item for item in parts if item]

        if isinstance(value, list):
            return [item.strip() for item in value if isinstance(item, str) and item.strip()]

        raise ValueError("Recipients must be a string, list of strings, or None.")

    def _build_raw_message(
        self,
        *,
        to: str | list[str],
        subject: str,
        body: str,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
        html_body: str | None = None,
        from_email: str | None = None,
        from_name: str | None = None,
    ) -> str:
        to_recipients = self._normalize_recipients(to)
        cc_recipients = self._normalize_recipients(cc)
        bcc_recipients = self._normalize_recipients(bcc)

        if not to_recipients:
            raise ValueError("Email recipient is missing.")
        if not subject or not subject.strip():
            raise ValueError("Email subject is missing.")

        message = EmailMessage()
        message["To"] = ", ".join(to_recipients)
        message["Subject"] = subject.strip()

        if cc_recipients:
            message["Cc"] = ", ".join(cc_recipients)

        if from_email:
            message["From"] = (
                formataddr((from_name.strip(), from_email.strip()))
                if from_name and from_name.strip()
                else from_email.strip()
            )

        if html_body:
            message.set_content(body or " ")
            message.add_alternative(html_body, subtype="html")
        else:
            message.set_content(body or "")

        raw_bytes = base64.urlsafe_b64encode(message.as_bytes())
        return raw_bytes.decode("utf-8")

    def send_message(
        self,
        *,
        to: str | list[str],
        subject: str,
        body: str,
        cc: str | list[str] | None = None,
        bcc: str | list[str] | None = None,
        html_body: str | None = None,
        from_email: str | None = None,
        from_name: str | None = None,
    ) -> dict[str, Any]:
        if not self.access_token or not self.access_token.strip():
            raise ValueError("GOOGLE_MAIL_ACCESS_TOKEN is missing.")

        raw_message = self._build_raw_message(
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            html_body=html_body,
            from_email=from_email,
            from_name=from_name,
        )

        url = f"{self.api_url}/users/{self.user_id}/messages/send"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {"raw": raw_message}

        logger.info(
            "Sending Gmail message",
            extra={
                "provider": "google_mail",
                "user_id": self.user_id,
                "url": url,
                "to_count": len(self._normalize_recipients(to)),
            },
        )

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=self.timeout_seconds,
        )

        if response.status_code >= 400:
            response_text = response.text.strip()
            logger.error(
                "Gmail send failed",
                extra={
                    "provider": "google_mail",
                    "status_code": response.status_code,
                    "response_text": response_text,
                },
            )

            if response.status_code == 401:
                raise RuntimeError(
                    "Google Mail unauthorized. The access token is invalid, expired, "
                    "or missing the gmail.send scope. Response: "
                    f"{response_text}"
                )

            if response.status_code == 403:
                raise RuntimeError(
                    "Google Mail forbidden. The token likely lacks permission to send mail. "
                    "Expected scope includes https://www.googleapis.com/auth/gmail.send. "
                    f"Response: {response_text}"
                )

            raise RuntimeError(
                f"Google Mail send failed with status {response.status_code}: {response_text}"
            )

        data = response.json()

        return {
            "status": "success",
            "provider": "google_mail",
            "message": "Email sent successfully via Google Mail.",
            "external_id": data.get("id"),
            "payload": {
                "google_message_id": data.get("id"),
                "thread_id": data.get("threadId"),
                "label_ids": data.get("labelIds", []),
            },
        }