"""Sender OAuth send-scope verification (no Gmail send, no tokeninfo)."""

from __future__ import annotations

from dataclasses import dataclass

from app.evaluation.live.gmail_transport import SenderCredentials, load_sender_credentials
from app.integrations.google.mail_client import refresh_access_token_with_metadata

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
GMAIL_MODIFY_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
GMAIL_FULL_MAILBOX_SCOPE = "https://mail.google.com/"

SEND_CAPABLE_SCOPES = frozenset(
    {
        GMAIL_SEND_SCOPE,
        GMAIL_COMPOSE_SCOPE,
        GMAIL_MODIFY_SCOPE,
        GMAIL_FULL_MAILBOX_SCOPE,
    }
)


@dataclass(frozen=True)
class SenderSendScopeReport:
    verified: bool
    unverifiable: bool
    issues: list[str]
    granted_send_scopes: list[str]
    failure_category: str | None = None


def _accepted_scope_names(scopes: frozenset[str]) -> list[str]:
    return sorted(scope for scope in scopes if scope in SEND_CAPABLE_SCOPES)


def verify_sender_send_scope(
    credentials: SenderCredentials | None = None,
) -> SenderSendScopeReport:
    """Fail-closed send-scope check using OAuth refresh metadata only."""
    try:
        credentials = credentials or load_sender_credentials()
        refresh = refresh_access_token_with_metadata(
            refresh_token=credentials.refresh_token,
            client_id=credentials.client_id,
            client_secret=credentials.client_secret,
        )
        if not refresh.granted_scopes:
            return SenderSendScopeReport(
                verified=False,
                unverifiable=True,
                issues=["sender scope metadata missing from OAuth refresh response"],
                granted_send_scopes=[],
                failure_category="sender_scope_unverifiable",
            )
        granted = _accepted_scope_names(refresh.granted_scopes)
        if not granted:
            return SenderSendScopeReport(
                verified=False,
                unverifiable=False,
                issues=["sender send scope not granted: requires a send-capable Gmail scope"],
                granted_send_scopes=[],
                failure_category="configuration",
            )
        return SenderSendScopeReport(
            verified=True,
            unverifiable=False,
            issues=[],
            granted_send_scopes=granted,
            failure_category=None,
        )
    except Exception as exc:
        return SenderSendScopeReport(
            verified=False,
            unverifiable=True,
            issues=[f"sender send scope check failed: {type(exc).__name__}"],
            granted_send_scopes=[],
            failure_category="sender_scope_unverifiable",
        )
