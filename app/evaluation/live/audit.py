"""Audit helpers for live evaluation (non-authoritative state)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.core.audit_service import create_audit_event


def emit_live_eval_audit(
    db: Session,
    *,
    tenant_id: str,
    action: str,
    status: str,
    details: dict[str, Any] | None = None,
    commit: bool = True,
) -> None:
    safe_details = dict(details or {})
    for forbidden in ("access_token", "refresh_token", "api_key", "message_text", "body"):
        safe_details.pop(forbidden, None)
    create_audit_event(
        db,
        tenant_id=tenant_id,
        category="live_eval",
        action=action,
        status=status,
        details=safe_details,
        commit=commit,
    )
