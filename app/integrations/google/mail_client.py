from __future__ import annotations

import base64
import logging
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr
from typing import Any

import requests


@dataclass(frozen=True)
class GmailMessageListResult:
    message_ids: list[str]
    truncated: bool


logger = logging.getLogger(__name__)

_GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


@dataclass(frozen=True)
class TokenRefreshResult:
    access_token: str
    granted_scopes: frozenset[str]


def _parse_granted_scopes(data: dict) -> frozenset[str]:
    raw = data.get("scope") or ""
    if not isinstance(raw, str) or not raw.strip():
        return frozenset()
    return frozenset(part.strip() for part in raw.split() if part.strip())


def refresh_access_token_with_metadata(
    refresh_token: str,
    client_id: str,
    client_secret: str,
    token_url: str = _GOOGLE_TOKEN_URL,
) -> TokenRefreshResult:
    """Exchange a refresh token for a new access token and granted scopes."""
    response = requests.post(
        token_url,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=10,
    )
    if response.status_code != 200:
        raise RuntimeError(
            f"Gmail token refresh failed ({response.status_code}): {response.text.strip()}"
        )
    data = response.json()
    new_token = data.get("access_token")
    if not new_token:
        raise RuntimeError("Gmail token refresh succeeded but response contained no access_token.")
    logger.info("Gmail access token refreshed successfully.")
    return TokenRefreshResult(
        access_token=new_token,
        granted_scopes=_parse_granted_scopes(data),
    )


def refresh_access_token(
    refresh_token: str,
    client_id: str,
    client_secret: str,
    token_url: str = _GOOGLE_TOKEN_URL,
) -> str:
    """Exchange a refresh token for a new access token.

    Returns the new access token string.
    Raises RuntimeError if the refresh request fails.
    """
    return refresh_access_token_with_metadata(
        refresh_token=refresh_token,
        client_id=client_id,
        client_secret=client_secret,
        token_url=token_url,
    ).access_token


class GoogleMailClient:
    def __init__(
        self,
        api_url: str,
        access_token: str,
        user_id: str = "me",
        timeout_seconds: int = 30,
        refresh_token: str = "",
        client_id: str = "",
        client_secret: str = "",
    ):
        self.api_url = api_url.rstrip("/")
        self.access_token = access_token
        self.user_id = user_id
        self.timeout_seconds = timeout_seconds
        self.refresh_token = refresh_token
        self.client_id = client_id
        self.client_secret = client_secret

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
        in_reply_to: str | None = None,
        references: str | None = None,
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
        if in_reply_to and in_reply_to.strip():
            message["In-Reply-To"] = in_reply_to.strip()
        if references and references.strip():
            message["References"] = references.strip()

        if html_body:
            message.set_content(body or " ")
            message.add_alternative(html_body, subtype="html")
        else:
            message.set_content(body or "")

        raw_bytes = base64.urlsafe_b64encode(message.as_bytes())
        return raw_bytes.decode("utf-8")

    def _can_refresh(self) -> bool:
        return bool(self.refresh_token and self.client_id and self.client_secret)

    def _post_message(self, raw_message: str, thread_id: str | None = None) -> requests.Response:
        url = f"{self.api_url}/users/{self.user_id}/messages/send"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        body: dict[str, Any] = {"raw": raw_message}
        if thread_id and thread_id.strip():
            body["threadId"] = thread_id.strip()
        return requests.post(
            url,
            headers=headers,
            json=body,
            timeout=self.timeout_seconds,
        )

    @staticmethod
    def _raise_for_response(response: requests.Response) -> None:
        if response.status_code < 400:
            return
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

    def _get(self, path: str, params: dict | None = None) -> requests.Response:
        url = f"{self.api_url}{path}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        return requests.get(url, headers=headers, params=params, timeout=self.timeout_seconds)

    def _get_with_refresh(self, path: str, params: dict | None = None) -> dict[str, Any]:
        response = self._get(path, params)
        if response.status_code == 401 and self._can_refresh():
            logger.info("Gmail 401 on read — attempting token refresh.")
            self.access_token = refresh_access_token(
                refresh_token=self.refresh_token,
                client_id=self.client_id,
                client_secret=self.client_secret,
            )
            response = self._get(path, params)
        if response.status_code >= 400:
            raise RuntimeError(
                f"Gmail API error ({response.status_code}): {response.text.strip()}"
            )
        return response.json()

    @staticmethod
    def _extract_header(headers: list[dict], name: str) -> str:
        for h in headers:
            if h.get("name", "").lower() == name.lower():
                return h.get("value", "")
        return ""

    @staticmethod
    def _extract_body_text(payload: dict) -> str:
        # Walk the MIME part tree depth-first; return the first text/plain body found.
        mime_type = payload.get("mimeType", "")
        parts = payload.get("parts") or []

        if mime_type == "text/plain":
            data = (payload.get("body") or {}).get("data", "")
            if data:
                try:
                    return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                except Exception:
                    return ""

        for part in parts:
            result = GoogleMailClient._extract_body_text(part)
            if result:
                return result

        return ""

    def get_message(self, message_id: str) -> dict[str, Any]:
        if not message_id or not message_id.strip():
            raise ValueError("message_id is required.")

        data = self._get_with_refresh(
            f"/users/{self.user_id}/messages/{message_id.strip()}",
            params={"format": "full"},
        )

        payload = data.get("payload") or {}
        hdrs = payload.get("headers") or []

        internal_date_raw = data.get("internalDate")
        internal_date_ms: int | None = None
        if internal_date_raw is not None:
            try:
                internal_date_ms = int(internal_date_raw)
            except (TypeError, ValueError):
                internal_date_ms = None

        return {
            "message_id": data.get("id", ""),
            "thread_id": data.get("threadId", ""),
            "from": self._extract_header(hdrs, "From"),
            "to": self._extract_header(hdrs, "To"),
            "cc": self._extract_header(hdrs, "Cc"),
            "delivered_to": self._extract_header(hdrs, "Delivered-To"),
            "subject": self._extract_header(hdrs, "Subject"),
            "internet_message_id": self._extract_header(hdrs, "Message-ID"),
            "received_at": self._extract_header(hdrs, "Date"),
            "snippet": data.get("snippet", ""),
            "label_ids": data.get("labelIds", []),
            "body_text": self._extract_body_text(payload),
            "internal_date_ms": internal_date_ms,
        }

    def _post_with_refresh(self, path: str, body: dict) -> dict[str, Any]:
        url = f"{self.api_url}{path}"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        response = requests.post(url, headers=headers, json=body, timeout=self.timeout_seconds)
        if response.status_code == 401 and self._can_refresh():
            logger.info("Gmail 401 on modify — attempting token refresh.")
            self.access_token = refresh_access_token(
                refresh_token=self.refresh_token,
                client_id=self.client_id,
                client_secret=self.client_secret,
            )
            headers["Authorization"] = f"Bearer {self.access_token}"
            response = requests.post(url, headers=headers, json=body, timeout=self.timeout_seconds)
        if response.status_code >= 400:
            raise RuntimeError(
                f"Gmail API error ({response.status_code}): {response.text.strip()}"
            )
        return response.json()

    def list_labels(self) -> list[dict[str, Any]]:
        data = self._get_with_refresh(f"/users/{self.user_id}/labels")
        return data.get("labels") or []

    def find_label_id(self, label_name: str) -> str | None:
        for label in self.list_labels():
            if label.get("name") == label_name:
                label_id = label.get("id")
                if label_id:
                    return str(label_id)
        return None

    def create_label(self, label_name: str) -> str:
        if not label_name or not label_name.strip():
            raise ValueError("label_name is required.")
        created = self._post_with_refresh(
            f"/users/{self.user_id}/labels",
            body={
                "name": label_name.strip(),
                "labelListVisibility": "labelShow",
                "messageListVisibility": "show",
            },
        )
        label_id = created.get("id")
        if not label_id:
            raise RuntimeError(f"Gmail label create succeeded but no id returned for '{label_name}'.")
        return str(label_id)

    def ensure_label(self, label_name: str) -> str:
        existing = self.find_label_id(label_name)
        if existing:
            return existing
        return self.create_label(label_name)

    def modify_message_labels(
        self,
        message_id: str,
        *,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> None:
        if not message_id or not message_id.strip():
            raise ValueError("message_id is required.")
        body: dict[str, Any] = {}
        if add_label_ids:
            body["addLabelIds"] = add_label_ids
        if remove_label_ids:
            body["removeLabelIds"] = remove_label_ids
        if not body:
            return
        self._post_with_refresh(
            f"/users/{self.user_id}/messages/{message_id.strip()}/modify",
            body=body,
        )

    def mark_as_read(self, message_id: str) -> None:
        if not message_id or not message_id.strip():
            raise ValueError("message_id is required.")
        self.modify_message_labels(message_id, remove_label_ids=["UNREAD"])

    def mark_as_unread(self, message_id: str) -> None:
        if not message_id or not message_id.strip():
            raise ValueError("message_id is required.")
        self.modify_message_labels(message_id, add_label_ids=["UNREAD"])

    def apply_label(self, message_id: str, label_name: str) -> str:
        if not message_id or not message_id.strip():
            raise ValueError("message_id is required.")
        label_id = self.ensure_label(label_name)
        self.modify_message_labels(message_id, add_label_ids=[label_id])
        return label_id

    def archive_from_inbox(self, message_id: str) -> None:
        """Remove from inbox without deleting (archive)."""
        if not message_id or not message_id.strip():
            raise ValueError("message_id is required.")
        self.modify_message_labels(message_id, remove_label_ids=["INBOX", "UNREAD"])

    def list_messages_page(self, max_results: int = 10, query: str = "") -> GmailMessageListResult:
        params: dict[str, Any] = {"maxResults": max_results}
        if query:
            params["q"] = query
        data = self._get_with_refresh(
            f"/users/{self.user_id}/messages",
            params=params,
        )
        stubs = data.get("messages") or []
        message_ids = [str(stub.get("id", "")) for stub in stubs if stub.get("id")]
        return GmailMessageListResult(
            message_ids=message_ids,
            truncated=bool(data.get("nextPageToken")),
        )

    def list_message_ids(self, max_results: int = 10, query: str = "") -> list[str]:
        return self.list_messages_page(max_results=max_results, query=query).message_ids

    def get_profile_email(self) -> str:
        data = self._get_with_refresh(f"/users/{self.user_id}/profile")
        return str(data.get("emailAddress") or "").strip().lower()

    def list_messages(self, max_results: int = 10, query: str = "") -> list[dict[str, Any]]:
        params: dict[str, Any] = {"maxResults": max_results, "format": "metadata"}
        if query:
            params["q"] = query

        data = self._get_with_refresh(
            f"/users/{self.user_id}/messages",
            params=params,
        )

        stubs = data.get("messages") or []
        messages = []

        for stub in stubs:
            msg_id = stub.get("id", "")
            detail = self._get_with_refresh(
                f"/users/{self.user_id}/messages/{msg_id}",
                params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
            )
            hdrs = detail.get("payload", {}).get("headers", [])
            messages.append({
                "message_id": msg_id,
                "thread_id": detail.get("threadId", ""),
                "from": self._extract_header(hdrs, "From"),
                "subject": self._extract_header(hdrs, "Subject"),
                "received_at": self._extract_header(hdrs, "Date"),
                "snippet": detail.get("snippet", ""),
                "label_ids": detail.get("labelIds", []),
            })

        return messages

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
        thread_id: str | None = None,
        in_reply_to: str | None = None,
        references: str | None = None,
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
            in_reply_to=in_reply_to,
            references=references,
        )

        logger.info(
            "Sending Gmail message",
            extra={
                "provider": "google_mail",
                "user_id": self.user_id,
                "to_count": len(self._normalize_recipients(to)),
            },
        )

        response = self._post_message(raw_message, thread_id=thread_id)

        # On 401, attempt token refresh and retry once.
        if response.status_code == 401 and self._can_refresh():
            logger.info("Gmail 401 received — attempting token refresh.")
            self.access_token = refresh_access_token(
                refresh_token=self.refresh_token,
                client_id=self.client_id,
                client_secret=self.client_secret,
            )
            response = self._post_message(raw_message, thread_id=thread_id)

        self._raise_for_response(response)

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