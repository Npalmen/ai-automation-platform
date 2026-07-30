"""Mailbox deliverability and provider binding for profile testbot readiness."""

from __future__ import annotations

import hashlib
import os
from typing import Any, Callable

from app.evaluation.live.config import LiveEvalConfig
from app.evaluation.live.gmail_transport import (
    build_recipient_client,
    build_sender_client,
    is_synthetic_live_eval_recipient,
)

_NON_DELIVERABLE_PLACEHOLDER_SUFFIXES = (
    "@eval.test",
    ".eval.test",
    "@example.com",
    "@example.org",
    "@test",
)
_DELIVERABLE_DOMAIN_SUFFIXES = (
    "@gmail.com",
    "@googlemail.com",
)


def mailbox_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()


def operator_approved_mailbox_hashes() -> frozenset[str]:
    raw = os.environ.get("PROFILE_TESTBOT_OPERATOR_APPROVED_MAILBOX_HASHES", "")
    return frozenset(item.strip().lower() for item in raw.split(",") if item.strip())


def is_operator_approved_mailbox(email: str) -> bool:
    normalized = (email or "").strip().lower()
    if not normalized:
        return False
    return mailbox_hash(normalized) in operator_approved_mailbox_hashes()


def is_non_deliverable_placeholder(email: str) -> bool:
    normalized = (email or "").strip().lower()
    if not normalized or normalized.count("@") != 1:
        return True
    if is_synthetic_live_eval_recipient(normalized):
        return True
    return any(normalized.endswith(suffix) for suffix in _NON_DELIVERABLE_PLACEHOLDER_SUFFIXES)


def looks_deliverable_mailbox(email: str) -> bool:
    normalized = (email or "").strip().lower()
    if is_operator_approved_mailbox(normalized):
        return True
    if is_non_deliverable_placeholder(normalized):
        return False
    local, domain = normalized.split("@", 1)
    if not local or "." not in domain:
        return False
    return any(normalized.endswith(suffix) for suffix in _DELIVERABLE_DOMAIN_SUFFIXES)


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("yes", "true", "1")


def _oauth_credentials_complete(*, role: str) -> tuple[bool, list[str]]:
    prefix = "LIVE_EVAL_SENDER_GMAIL" if role == "sender" else "LIVE_EVAL_RECIPIENT_GMAIL"
    required = (
        f"{prefix}_REFRESH_TOKEN",
        f"{prefix}_CLIENT_ID",
        f"{prefix}_CLIENT_SECRET",
    )
    missing = [name for name in required if not os.environ.get(name, "").strip()]
    if missing:
        return False, [f"{role} OAuth missing env: {', '.join(missing)}"]
    return True, []


def _verify_mailbox_provider_read_only(
    *,
    role: str,
    expected_email: str,
    build_client: Callable[[], Any],
) -> tuple[bool, list[str]]:
    issues: list[str] = []
    profile_email: str | None = None
    try:
        client = build_client()
        profile_email = client.get_profile_email()
        client.list_messages_page(max_results=1, query="in:anywhere")
    except Exception as exc:
        issues.append(f"{role}_provider_read_only_failed: {type(exc).__name__}")
        return False, issues

    expected = expected_email.strip().lower()
    profile = (profile_email or "").strip().lower()
    if not profile:
        issues.append(f"{role}_provider_profile_missing")
        return False, issues
    if profile != expected:
        issues.append(f"{role}_oauth_mailbox_mismatch")
        return False, issues
    return True, issues


def verify_profile_testbot_mailboxes(
    *,
    sender_email: str,
    recipient_email: str,
    config: LiveEvalConfig,
) -> dict[str, Any]:
    """Verify mailbox readiness without exposing addresses in the returned payload."""
    blocking: list[str] = []
    sender = sender_email.strip().lower()
    recipient = recipient_email.strip().lower()

    if not sender:
        blocking.append("sender mailbox missing from allowlist")
    if not recipient:
        blocking.append("recipient mailbox missing from allowlist")
    if sender and recipient and sender == recipient:
        blocking.append("sender and recipient must be distinct mailboxes")
    if sender and is_non_deliverable_placeholder(sender):
        blocking.append("sender mailbox is a non-deliverable placeholder")
    if recipient and is_non_deliverable_placeholder(recipient):
        blocking.append("recipient mailbox is a non-deliverable placeholder")
    if sender and not looks_deliverable_mailbox(sender) and not is_operator_approved_mailbox(sender):
        blocking.append("sender mailbox is not a deliverable provider mailbox")
    if recipient and not looks_deliverable_mailbox(recipient) and not is_operator_approved_mailbox(recipient):
        blocking.append("recipient mailbox is not a deliverable provider mailbox")

    sender_oauth_ok, sender_oauth_issues = _oauth_credentials_complete(role="sender")
    recipient_oauth_ok, recipient_oauth_issues = _oauth_credentials_complete(role="recipient")
    blocking.extend(sender_oauth_issues)
    blocking.extend(recipient_oauth_issues)

    sender_provider_verified = False
    recipient_deliverability_verified = False

    if not blocking and _env_truthy("LIVE_GMAIL_EVAL_ALLOWED"):
        sender_provider_verified, sender_issues = _verify_mailbox_provider_read_only(
            role="sender",
            expected_email=sender,
            build_client=build_sender_client,
        )
        recipient_deliverability_verified, recipient_issues = _verify_mailbox_provider_read_only(
            role="recipient",
            expected_email=recipient,
            build_client=build_recipient_client,
        )
        blocking.extend(sender_issues)
        blocking.extend(recipient_issues)
    elif not blocking and _env_truthy("PROFILE_TESTBOT_OFFLINE_MAILBOX_CONTRACT"):
        sender_provider_verified = sender_oauth_ok
        recipient_deliverability_verified = recipient_oauth_ok
    elif not blocking:
        blocking.append(
            "LIVE_GMAIL_EVAL_ALLOWED=yes or PROFILE_TESTBOT_OFFLINE_MAILBOX_CONTRACT=yes "
            "required for mailbox provider verification"
        )

    return {
        "sender_mailbox_hash": mailbox_hash(sender) if sender else None,
        "recipient_mailbox_hash": mailbox_hash(recipient) if recipient else None,
        "sender_provider_verified": sender_provider_verified,
        "recipient_deliverability_verified": recipient_deliverability_verified,
        "blocking_failures": blocking,
        "mailbox_addresses_redacted": True,
    }
