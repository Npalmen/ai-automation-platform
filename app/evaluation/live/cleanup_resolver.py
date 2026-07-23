"""Resolve exact recipient Gmail message ID from run journal for cleanup."""

from __future__ import annotations

from dataclasses import dataclass

from app.evaluation.live.journal import RunCheckpoint, load_run_config


@dataclass(frozen=True)
class RecipientCleanupResolution:
    recipient_gmail_message_id: str | None = None
    blocked_reason: str | None = None

    @property
    def resolved(self) -> bool:
        return self.recipient_gmail_message_id is not None and self.blocked_reason is None


def resolve_recipient_from_journal(checkpoint: RunCheckpoint) -> RecipientCleanupResolution:
    """
    Derive exactly one recipient message ID from validated delivery_confirmed transitions.

  Fail-closed when journal is missing, ambiguous, or contradicts run metadata.
    """
    run_config = load_run_config(checkpoint.evaluation_run_id)
    if not run_config and not checkpoint.transitions:
        return RecipientCleanupResolution(blocked_reason="missing_or_invalid_journal")

    expected_run_id = str(
        run_config.get("evaluation_run_id") or checkpoint.evaluation_run_id
    )
    if expected_run_id != checkpoint.evaluation_run_id:
        return RecipientCleanupResolution(blocked_reason="evaluation_run_id_mismatch")

    expected_tenant = str(run_config.get("tenant_id") or checkpoint.tenant_id or "")
    if checkpoint.tenant_id and expected_tenant and expected_tenant != checkpoint.tenant_id:
        return RecipientCleanupResolution(blocked_reason="tenant_id_mismatch")

    expected_scenario = str(run_config.get("scenario_id") or checkpoint.scenario_id or "")
    if checkpoint.scenario_id and expected_scenario and expected_scenario != checkpoint.scenario_id:
        return RecipientCleanupResolution(blocked_reason="scenario_id_mismatch")

    expected_attempt = int(run_config.get("attempt_id") or checkpoint.attempt_id or 0)
    if checkpoint.attempt_id and expected_attempt and expected_attempt != checkpoint.attempt_id:
        return RecipientCleanupResolution(blocked_reason="attempt_id_mismatch")

    recipient_ids: list[str] = []
    for transition in checkpoint.transitions:
        if transition.get("state") != "delivery_confirmed":
            continue
        message_id = transition.get("recipient_gmail_message_id")
        if message_id:
            recipient_ids.append(str(message_id))

    unique_ids = list(dict.fromkeys(recipient_ids))
    if not unique_ids:
        return RecipientCleanupResolution(blocked_reason="no_delivery_confirmed_recipient_id")
    if len(unique_ids) > 1:
        return RecipientCleanupResolution(blocked_reason="multiple_distinct_recipient_ids")

    recipient_id = unique_ids[0]
    sender_id = checkpoint.sender_gmail_message_id
    if sender_id and recipient_id == sender_id:
        return RecipientCleanupResolution(
            blocked_reason="recipient_gmail_message_id matches sender_gmail_message_id"
        )

    return RecipientCleanupResolution(recipient_gmail_message_id=recipient_id)
