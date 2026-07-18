"""Server-generated config fingerprints for integration verification binding."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any


def _hash_payload(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fingerprint_gmail(*, label_scope_slug: str, tenant_slug: str) -> str:
    return _hash_payload(
        {
            "integration": "gmail",
            "label_scope_slug": label_scope_slug.strip().lower(),
            "unread_only": True,
            "tenant_slug": tenant_slug.strip().lower(),
        }
    )


def fingerprint_visma(*, connection_updated_at: datetime | None) -> str:
    ts = connection_updated_at.isoformat() if connection_updated_at else ""
    return _hash_payload({"integration": "visma", "connection_updated_at": ts})


def fingerprint_google_sheets(*, spreadsheet_id: str, export_tabs: list[str]) -> str:
    return _hash_payload(
        {
            "integration": "google_sheets",
            "spreadsheet_id": spreadsheet_id.strip(),
            "export_tabs": sorted(export_tabs),
        }
    )


def fingerprint_monday(*, board_id: str, group_id: str | None) -> str:
    return _hash_payload(
        {
            "integration": "monday",
            "board_id": board_id.strip(),
            "group_id": (group_id or "").strip() or None,
        }
    )


def build_gmail_label_query(label_scope_slug: str) -> str:
    slug = label_scope_slug.strip().lower()
    if not slug:
        raise ValueError("label_scope_slug is required.")
    if not all(ch.isalnum() or ch == "-" for ch in slug):
        raise ValueError("label_scope_slug contains invalid characters.")
    return f"label:krowolf-{slug} is:unread"
