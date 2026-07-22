"""Recipient cleanup for live Gmail eval."""

from __future__ import annotations

from typing import Literal

from sqlalchemy.orm import Session

from app.evaluation.live.config import get_live_eval_config
from app.evaluation.live.delivery import validate_delivery_candidate, resolve_intake_label_id
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.gmail_transport import archive_unexpected_reply
from app.evaluation.live.safety import require_live_eval_mutation_context, validate_live_gmail_run_for_mutation
from app.integrations.enums import IntegrationType
from app.integrations.factory import get_integration_adapter
from app.integrations.service import get_integration_connection_config
from app.repositories.postgres.live_eval_repository import LiveEvalRunRepository

CleanupPhase = Literal["pre_claim", "post_claim"]


def cleanup_recipient_message(
    db: Session,
    *,
    evaluation_run_id: str,
    tenant_id: str,
    recipient_gmail_message_id: str,
    phase: CleanupPhase,
) -> dict:
    require_live_eval_mutation_context(tenant_id)
    row = LiveEvalRunRepository.get_run(db, evaluation_run_id, tenant_id=tenant_id)
    if row is None:
        raise LiveEvalSafetyError("unknown evaluation_run_id")

    validate_live_gmail_run_for_mutation(
        row,
        tenant_id=tenant_id,
        recipient_message_id=recipient_gmail_message_id,
        allow_active_idempotent=(phase == "post_claim"),
    )

    if phase == "post_claim":
        if not row.root_gmail_message_id:
            raise LiveEvalSafetyError("post_claim cleanup requires root_gmail_message_id")
        if row.root_gmail_message_id != recipient_gmail_message_id:
            raise LiveEvalSafetyError("recipient message id does not match registry root")

    connection_config = get_integration_connection_config(
        tenant_id=tenant_id,
        integration_type=IntegrationType.GOOGLE_MAIL,
        db=db,
    )
    adapter = get_integration_adapter(
        integration_type=IntegrationType.GOOGLE_MAIL,
        connection_config=connection_config,
    )
    intake_label_id = resolve_intake_label_id(adapter, get_live_eval_config().intake_label)
    detail = adapter.execute_action(
        action="get_message",
        payload={"message_id": recipient_gmail_message_id},
    )
    msg = detail.get("message") or {}
    ok, reason = validate_delivery_candidate(
        msg, row=row, config=get_live_eval_config(), intake_label_id=intake_label_id
    )
    if not ok:
        raise LiveEvalSafetyError(f"recipient cleanup validation failed: {reason}")

    if phase == "pre_claim" and row.root_job_id:
        raise LiveEvalSafetyError("pre_claim cleanup not allowed after root job exists")

    adapter.client.archive_from_inbox(recipient_gmail_message_id)
    return {
        "phase": phase,
        "recipient_gmail_message_id": recipient_gmail_message_id,
        "result": "archived",
    }


def cleanup_unexpected_reply(*, message_id: str) -> dict:
    archive_unexpected_reply(message_id=message_id)
    return {"unexpected_reply_message_id": message_id, "archived": True}
