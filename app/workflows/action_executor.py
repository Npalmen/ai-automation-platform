from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


SUPPORTED_ACTIONS = {
    "send_email",
    "notify_slack",
    "notify_teams",
    "create_internal_task",
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


def _build_send_email_result(action: dict[str, Any]) -> dict[str, Any]:
    to = _ensure_str(action.get("to"), "to")
    subject = _ensure_str(action.get("subject"), "subject")
    body = _ensure_str(action.get("body"), "body")

    return {
        "type": "send_email",
        "status": "executed",
        "executed_at": _utcnow_iso(),
        "target": to,
        "provider": "internal_stub",
        "payload": {
            "to": to,
            "subject": subject,
            "body": body,
        },
    }


def _build_notify_slack_result(action: dict[str, Any]) -> dict[str, Any]:
    channel = _ensure_str(action.get("channel"), "channel")
    message = _ensure_str(action.get("message"), "message")

    return {
        "type": "notify_slack",
        "status": "executed",
        "executed_at": _utcnow_iso(),
        "target": channel,
        "provider": "internal_stub",
        "payload": {
            "channel": channel,
            "message": message,
        },
    }


def _build_notify_teams_result(action: dict[str, Any]) -> dict[str, Any]:
    channel = _ensure_str(action.get("channel"), "channel")
    message = _ensure_str(action.get("message"), "message")

    return {
        "type": "notify_teams",
        "status": "executed",
        "executed_at": _utcnow_iso(),
        "target": channel,
        "provider": "internal_stub",
        "payload": {
            "channel": channel,
            "message": message,
        },
    }


def _build_internal_task_result(action: dict[str, Any]) -> dict[str, Any]:
    title = _ensure_str(action.get("title"), "title")
    description = _ensure_str(action.get("description"), "description")
    assignee = action.get("assignee")

    if assignee is not None and (not isinstance(assignee, str) or not assignee.strip()):
        raise ValueError("Action field 'assignee' must be a non-empty string when provided.")

    metadata = action.get("metadata") or {}
    metadata = _ensure_dict(metadata, "metadata") if metadata else {}

    return {
        "type": "create_internal_task",
        "status": "executed",
        "executed_at": _utcnow_iso(),
        "target": assignee.strip() if isinstance(assignee, str) else None,
        "provider": "internal_stub",
        "payload": {
            "title": title,
            "description": description,
            "assignee": assignee.strip() if isinstance(assignee, str) else None,
            "metadata": metadata,
        },
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

    if action_type == "send_email":
        return _build_send_email_result(action)

    if action_type == "notify_slack":
        return _build_notify_slack_result(action)

    if action_type == "notify_teams":
        return _build_notify_teams_result(action)

    if action_type == "create_internal_task":
        return _build_internal_task_result(action)

    raise ValueError(f"Unhandled action type '{action_type}'.")