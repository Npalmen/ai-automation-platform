"""Shared fail-closed authorization for approval-gated LIVE_EVAL Gmail customer replies."""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy.orm import Session

from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.integrations.enums import IntegrationType

CUSTOMER_REPLY_ACTION = "send_customer_auto_reply"
SAFE_ACK_APPROVAL_REASON = "safe_acknowledgement_requires_approval"

AuthorizationPhase = Literal["dispatch_materialize", "execute"]


def is_approval_gated_customer_reply(action: dict[str, Any]) -> bool:
    return (
        str(action.get("type") or "") == CUSTOMER_REPLY_ACTION
        and action.get("_needs_approval") is True
    )


def _google_mail_selected(tenant_id: str, db: Session | None) -> bool:
    if tenant_id == LIVE_EVAL_TENANT_ID:
        from app.evaluation.live.config import get_live_eval_config

        if get_live_eval_config().gmail_enabled:
            return True
    from app.integrations.policies import is_integration_enabled_for_tenant

    return is_integration_enabled_for_tenant(
        tenant_id,
        IntegrationType.GOOGLE_MAIL,
        db=db,
    )


def _safe_acknowledgement_action(action: dict[str, Any]) -> bool:
    reason = str(action.get("_approval_reason") or "")
    if reason == SAFE_ACK_APPROVAL_REASON:
        return True
    return action.get("_safe_acknowledgement_path") is True


def allows_live_eval_approval_gated_customer_reply(
    action: dict[str, Any],
    tenant_id: str,
    db: Session | None,
    *,
    phase: AuthorizationPhase,
) -> bool:
    """Narrow eval contract: approval-gated safe-ack customer reply on google_mail only."""
    if tenant_id != LIVE_EVAL_TENANT_ID:
        return False
    if not is_approval_gated_customer_reply(action):
        return False
    if not _google_mail_selected(tenant_id, db):
        return False
    if not _safe_acknowledgement_action(action):
        return False
    if phase == "execute":
        if str(action.get("_authorization") or "") != "execution_allowed":
            return False
    return True
