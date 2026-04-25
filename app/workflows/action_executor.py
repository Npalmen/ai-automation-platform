from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from app.integrations.enums import IntegrationType
from app.integrations.factory import get_integration_adapter
from app.integrations.internal_stub import InternalStubAdapter
from app.integrations.service import (
    get_integration_connection_config,
    is_integration_configured,
)


logger = logging.getLogger(__name__)

SUPPORTED_ACTIONS = {
    "send_email",
    "send_customer_auto_reply",
    "send_internal_handoff",
    "notify_slack",
    "notify_teams",
    "create_internal_task",
    "create_monday_item",
}


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Action field '{field_name}' must be a non-empty string.")
    return value.strip()


def _ensure_dict(value: Any, field_name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"Action field '{field_name}' must be an object.")
    return value


def _get_tenant_id(action: dict[str, Any]) -> str:
    tenant_id = action.get("tenant_id") or "TENANT_1001"
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("Action field 'tenant_id' must be a non-empty string when provided.")
    return tenant_id.strip()


def _build_stub_result(
    action_type: str,
    target: str | None,
    payload: dict[str, Any],
    integration: str,
    message: str,
) -> dict[str, Any]:
    stub_adapter = InternalStubAdapter(
        connection_config={
            "integration": integration,
            "provider": "internal_stub",
            "message": message,
        }
    )
    stub_result = stub_adapter.execute_action(action=action_type, payload=payload)

    return {
        "type": action_type,
        "status": "executed",
        "executed_at": _utcnow_iso(),
        "target": target,
        "provider": stub_result["provider"],
        "payload": payload,
        "integration_result": stub_result,
    }


def _build_email_result(action: dict[str, Any]) -> dict[str, Any]:
    tenant_id = _get_tenant_id(action)
    to = _ensure_str(action.get("to"), "to")
    subject = _ensure_str(action.get("subject"), "subject")
    body = _ensure_str(action.get("body"), "body")

    payload: dict[str, Any] = {
        "to": to,
        "subject": subject,
        "body": body,
    }

    if "cc" in action:
        payload["cc"] = action.get("cc")
    if "bcc" in action:
        payload["bcc"] = action.get("bcc")
    if "html_body" in action:
        payload["html_body"] = action.get("html_body")
    if "from_email" in action:
        payload["from_email"] = action.get("from_email")
    if "from_name" in action:
        payload["from_name"] = action.get("from_name")

    connection_config = get_integration_connection_config(
        tenant_id=tenant_id,
        integration_type=IntegrationType.GOOGLE_MAIL,
    )

    if not is_integration_configured(connection_config):
        return _build_stub_result(
            action_type="send_email",
            target=to,
            payload=payload,
            integration="email",
            message="Email integration is not configured for this tenant. Falling back to internal stub.",
        )

    adapter = get_integration_adapter(
        integration_type=IntegrationType.GOOGLE_MAIL,
        connection_config=connection_config,
    )
    result = adapter.execute_action(action="send_email", payload=payload)

    return {
        "type": "send_email",
        "status": "executed",
        "executed_at": _utcnow_iso(),
        "target": to,
        "provider": result.get("provider", "smtp"),
        "payload": payload,
        "integration_result": result,
    }


def _build_slack_result(action: dict[str, Any]) -> dict[str, Any]:
    tenant_id = _get_tenant_id(action)
    channel = _ensure_str(action.get("channel"), "channel")
    message = _ensure_str(action.get("message"), "message")

    payload: dict[str, Any] = {
        "channel": channel,
        "message": message,
    }

    if "username" in action:
        payload["username"] = action.get("username")
    if "icon_emoji" in action:
        payload["icon_emoji"] = action.get("icon_emoji")
    if "blocks" in action:
        payload["blocks"] = action.get("blocks")

    connection_config = get_integration_connection_config(
        tenant_id=tenant_id,
        integration_type=IntegrationType.SLACK,
    )

    if not is_integration_configured(connection_config):
        return _build_stub_result(
            action_type="notify_slack",
            target=channel,
            payload=payload,
            integration="slack",
            message="Slack integration is not configured for this tenant. Falling back to internal stub.",
        )

    adapter = get_integration_adapter(
        integration_type=IntegrationType.SLACK,
        connection_config=connection_config,
    )
    result = adapter.execute_action(action="notify_slack", payload=payload)

    return {
        "type": "notify_slack",
        "status": "executed",
        "executed_at": _utcnow_iso(),
        "target": channel,
        "provider": result.get("provider", "webhook"),
        "payload": payload,
        "integration_result": result,
    }


def _build_notify_teams_result(action: dict[str, Any]) -> dict[str, Any]:
    channel = _ensure_str(action.get("channel"), "channel")
    message = _ensure_str(action.get("message"), "message")

    payload = {
        "channel": channel,
        "message": message,
    }

    return _build_stub_result(
        action_type="notify_teams",
        target=channel,
        payload=payload,
        integration="teams",
        message="Teams integration is not implemented yet. Falling back to internal stub.",
    )


def _build_internal_task_result(action: dict[str, Any]) -> dict[str, Any]:
    title = _ensure_str(action.get("title"), "title")
    description = _ensure_str(action.get("description"), "description")
    assignee = action.get("assignee")

    if assignee is not None and (not isinstance(assignee, str) or not assignee.strip()):
        raise ValueError("Action field 'assignee' must be a non-empty string when provided.")

    metadata = action.get("metadata") or {}
    metadata = _ensure_dict(metadata, "metadata") if metadata else {}

    payload = {
        "title": title,
        "description": description,
        "assignee": assignee.strip() if isinstance(assignee, str) else None,
        "metadata": metadata,
    }

    return _build_stub_result(
        action_type="create_internal_task",
        target=payload["assignee"],
        payload=payload,
        integration="internal_task",
        message="Internal task provider is not implemented yet. Falling back to internal stub.",
    )


def _build_monday_item_result(action: dict[str, Any]) -> dict[str, Any]:
    tenant_id = _get_tenant_id(action)
    item_name = _ensure_str(action.get("item_name"), "item_name")

    payload: dict[str, Any] = {
        "item_name": item_name,
        "column_values": action.get("column_values", {}),
        "group_id": action.get("group_id"),
    }

    connection_config = get_integration_connection_config(
        tenant_id=tenant_id,
        integration_type=IntegrationType.MONDAY,
    )

    if not is_integration_configured(connection_config):
        return _build_stub_result(
            action_type="create_monday_item",
            target=item_name,
            payload=payload,
            integration="monday",
            message="Monday integration is not configured for this tenant. Falling back to internal stub.",
        )

    adapter = get_integration_adapter(
        integration_type=IntegrationType.MONDAY,
        connection_config=connection_config,
    )
    result = adapter.execute_action(action="create_item", payload=payload)

    return {
        "type": "create_monday_item",
        "status": "executed",
        "executed_at": _utcnow_iso(),
        "target": item_name,
        "provider": "monday",
        "payload": payload,
        "integration_result": result,
    }


def execute_action(action: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(action, dict):
        raise ValueError("Each action must be an object.")

    action_type = action.get("type")

    if action_type not in SUPPORTED_ACTIONS:
        raise ValueError(
            f"Unsupported action type '{action_type}'. "
            f"Supported: {sorted(SUPPORTED_ACTIONS)}"
        )

    logger.info(
        "Executing workflow action",
        extra={
            "action_type": action_type,
            "tenant_id": action.get("tenant_id"),
        },
    )

    if action_type in ("send_email", "send_customer_auto_reply", "send_internal_handoff"):
        result = _build_email_result(action)
        result["type"] = action_type
        return result

    if action_type == "notify_slack":
        return _build_slack_result(action)

    if action_type == "notify_teams":
        return _build_notify_teams_result(action)

    if action_type == "create_internal_task":
        return _build_internal_task_result(action)

    if action_type == "create_monday_item":
        return _build_monday_item_result(action)

    raise ValueError(f"Unhandled action type '{action_type}'.")