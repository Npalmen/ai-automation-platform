"""Identify real pilot inbound messages vs synthetic/eval traffic."""

from __future__ import annotations

from typing import Any


def extract_gmail_source(input_data: dict[str, Any] | None) -> dict[str, Any]:
    return dict((input_data or {}).get("source") or {})


def is_real_pilot_inbound_message(input_data: dict[str, Any] | None) -> bool:
    source = extract_gmail_source(input_data)
    if source.get("system") != "gmail":
        return False
    message_id = str(source.get("message_id") or "").strip()
    if not message_id:
        return False
    if message_id.startswith("synthetic-"):
        return False
    if source.get("synthetic") is True:
        return False
    data = input_data or {}
    if data.get("live_eval") or data.get("_live_eval"):
        return False
    if data.get("production_pilot_preflight"):
        return False
    return True


def gmail_message_id(input_data: dict[str, Any] | None) -> str | None:
    source = extract_gmail_source(input_data)
    message_id = str(source.get("message_id") or "").strip()
    return message_id or None
