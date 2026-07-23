"""Fail-closed cleanup phase resolution for live-eval."""

from __future__ import annotations

from dataclasses import dataclass

from app.evaluation.live.cleanup_resolver import resolve_recipient_from_journal
from app.evaluation.live.journal import RunCheckpoint


@dataclass(frozen=True)
class CleanupPhaseResolution:
    phase: str | None = None
    blocked_reason: str | None = None

    @property
    def resolved(self) -> bool:
        return self.phase in {"pre_claim", "post_claim"} and self.blocked_reason is None


def resolve_cleanup_phase(
    checkpoint: RunCheckpoint,
    *,
    root_job_bound: bool,
    root_gmail_message_id: str | None,
) -> CleanupPhaseResolution:
    """
    Choose pre_claim vs post_claim cleanup.

    pre_claim: root not bound, exactly one journal recipient ID, delivery_confirmed present.
    post_claim: root_job_bound with trusted root_gmail_message_id.
    """
    if root_job_bound:
        if not root_gmail_message_id:
            return CleanupPhaseResolution(blocked_reason="root_job_bound_without_message_id")
        return CleanupPhaseResolution(phase="post_claim")

    if root_gmail_message_id:
        return CleanupPhaseResolution(blocked_reason="root_message_id_without_binding")

    if not any(item.get("state") == "delivery_confirmed" for item in checkpoint.transitions):
        return CleanupPhaseResolution(blocked_reason="missing_delivery_confirmed")

    resolution = resolve_recipient_from_journal(checkpoint)
    if not resolution.resolved:
        return CleanupPhaseResolution(blocked_reason=resolution.blocked_reason)
    return CleanupPhaseResolution(phase="pre_claim")
