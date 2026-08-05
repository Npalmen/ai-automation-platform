"""Read-only R4 mailbox baseline (no mutations)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable


def build_r4_mailbox_baseline(
    *,
    campaign_id: str,
    sender_identity: str | None = None,
    recipient_identity: str | None = None,
    existing_draft_count: int = 0,
    r3_subject_tokens: list[str] | None = None,
    r3_provider_message_ids_redacted: list[str] | None = None,
    existing_r4_subject_tokens: list[str] | None = None,
    probe_fn: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Register baseline before future execute. Never mutates mailboxes."""
    probed = probe_fn() if probe_fn else {}
    draft_count = int(probed.get("draft_count", existing_draft_count) or 0)
    r4_tokens = list(probed.get("r4_subject_tokens") or existing_r4_subject_tokens or [])
    blockers: list[str] = []
    if r4_tokens:
        blockers.append("existing_r4_subject_tokens_present")
    return {
        "baseline_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "campaign_id": campaign_id,
        "existing_draft_count": draft_count,
        "r3_campaign_subject_tokens": list(
            probed.get("r3_subject_tokens") or r3_subject_tokens or []
        ),
        "r3_provider_message_ids_redacted": list(
            probed.get("r3_provider_message_ids_redacted")
            or r3_provider_message_ids_redacted
            or []
        ),
        "existing_r4_subject_tokens": r4_tokens,
        "sender_mailbox_identity": probed.get("sender_identity") or sender_identity,
        "recipient_mailbox_identity": probed.get("recipient_identity") or recipient_identity,
        "mutations_performed": False,
        "gmail_sends": 0,
        "gmail_drafts": 0,
        "gmail_triggers": 0,
        "external_writes": 0,
        "passed": not blockers,
        "blockers": blockers,
        "subject_prefix": f"KROWOLF-R4/{campaign_id}",
    }
