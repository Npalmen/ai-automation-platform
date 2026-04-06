# app/integrations/slack/webhook_client.py
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any


logger = logging.getLogger(__name__)


class SlackWebhookClient:
    def __init__(self, connection_config: dict[str, Any]):
        self.connection_config = connection_config

    def send_message(self, payload: dict[str, Any]) -> dict[str, Any]:
        webhook_url = str(self.connection_config.get("webhook_url") or "").strip()
        timeout_seconds = int(self.connection_config.get("timeout_seconds") or 10)

        message = str(payload.get("message") or payload.get("text") or "").strip()
        channel = payload.get("channel")
        username = payload.get("username")
        icon_emoji = payload.get("icon_emoji")
        blocks = payload.get("blocks")

        if not webhook_url:
            raise ValueError("Slack webhook_url is missing.")

        if not message and not blocks:
            raise ValueError("Slack payload must contain 'message'/'text' or 'blocks'.")

        body: dict[str, Any] = {}

        if message:
            body["text"] = message
        if blocks:
            body["blocks"] = blocks
        if channel:
            body["channel"] = channel
        if username:
            body["username"] = username
        if icon_emoji:
            body["icon_emoji"] = icon_emoji

        request = urllib.request.Request(
            url=webhook_url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        logger.info(
            "Sending Slack webhook",
            extra={
                "provider": "webhook",
                "channel": channel,
                "has_blocks": bool(blocks),
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                response_body = response.read().decode("utf-8").strip()
                status_code = getattr(response, "status", 200)

                if status_code < 200 or status_code >= 300:
                    raise RuntimeError(f"Slack webhook failed with status {status_code}: {response_body}")

                return {
                    "status": "success",
                    "provider": "webhook",
                    "message": "Slack notification sent successfully.",
                    "external_id": None,
                    "payload": {
                        "channel": channel,
                        "message": message,
                        "response_body": response_body,
                    },
                }
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Slack webhook failed with status {exc.code}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Slack webhook connection error: {exc.reason}") from exc