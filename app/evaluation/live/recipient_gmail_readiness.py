"""Read-only recipient Gmail readiness for live eval delivery observation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.evaluation.live.config import LiveEvalConfig, get_live_eval_config
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.gmail_transport import RecipientCredentials, load_recipient_credentials
from app.integrations.google.mail_client import GmailMessageListResult, refresh_access_token_with_metadata

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_MODIFY_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
RECIPIENT_READ_ONLY_SCOPES = frozenset({GMAIL_READONLY_SCOPE, GMAIL_MODIFY_SCOPE})


@dataclass
class RecipientGmailReadinessResult:
    recipient_oauth_configured: bool = False
    recipient_token_refresh_passed: bool = False
    recipient_gmail_api_passed: bool = False
    recipient_mailbox_identity_match: bool = False
    recipient_required_scopes_present: bool = False
    recipient_list_labels_passed: bool = False
    recipient_read_query_passed: bool = False
    recipient_delivery_observation_ready: bool = False
    blockers: list[str] = field(default_factory=list)
    granted_scopes: list[str] = field(default_factory=list)
    profile_email_redacted: str | None = None

    @property
    def ready(self) -> bool:
        return self.recipient_delivery_observation_ready and not self.blockers

    def to_dict(self) -> dict[str, Any]:
        return {
            "recipient_oauth_configured": self.recipient_oauth_configured,
            "recipient_token_refresh_passed": self.recipient_token_refresh_passed,
            "recipient_gmail_api_passed": self.recipient_gmail_api_passed,
            "recipient_mailbox_identity_match": self.recipient_mailbox_identity_match,
            "recipient_required_scopes_present": self.recipient_required_scopes_present,
            "recipient_list_labels_passed": self.recipient_list_labels_passed,
            "recipient_read_query_passed": self.recipient_read_query_passed,
            "recipient_delivery_observation_ready": self.recipient_delivery_observation_ready,
            "blockers": list(self.blockers),
            "granted_scopes": list(self.granted_scopes),
            "profile_email_redacted": self.profile_email_redacted,
        }


def _redact_email(value: str | None) -> str | None:
    if not value or "@" not in value:
        return value
    local, _, domain = value.partition("@")
    return f"{local[:2]}…@{domain}"


def _scope_names(scopes: frozenset[str]) -> list[str]:
    return sorted(scope for scope in scopes if scope in RECIPIENT_READ_ONLY_SCOPES)


def _has_required_read_scopes(scopes: frozenset[str]) -> bool:
    return GMAIL_READONLY_SCOPE in scopes or GMAIL_MODIFY_SCOPE in scopes


def run_recipient_gmail_readiness(
    *,
    expected_recipient: str,
    config: LiveEvalConfig | None = None,
    credentials: RecipientCredentials | None = None,
) -> RecipientGmailReadinessResult:
    """Verify recipient Gmail OAuth and read-only API access without writes."""
    from app.evaluation.live.safety import require_gmail_eval_enabled

    config = config or get_live_eval_config()
    result = RecipientGmailReadinessResult()
    recipient = expected_recipient.strip().lower()
    if not recipient:
        result.blockers.append("expected recipient email is empty")
        return result
    if recipient not in config.recipient_emails:
        result.blockers.append("expected_recipient is not allowlisted")

    try:
        require_gmail_eval_enabled(config)
    except LiveEvalSafetyError as exc:
        result.blockers.append(str(exc))
        return result

    try:
        credentials = credentials or load_recipient_credentials()
        result.recipient_oauth_configured = True
    except LiveEvalSafetyError as exc:
        result.blockers.append(str(exc))
        return result

    access_token: str | None = None
    try:
        refresh = refresh_access_token_with_metadata(
            refresh_token=credentials.refresh_token,
            client_id=credentials.client_id,
            client_secret=credentials.client_secret,
        )
        access_token = refresh.access_token
        result.recipient_token_refresh_passed = True
        granted = _scope_names(refresh.granted_scopes)
        result.granted_scopes = granted
        if refresh.granted_scopes:
            result.recipient_required_scopes_present = _has_required_read_scopes(
                refresh.granted_scopes
            )
            if not result.recipient_required_scopes_present:
                result.blockers.append(
                    "recipient OAuth token missing gmail.readonly or gmail.modify scope"
                )
        else:
            result.blockers.append(
                "recipient OAuth refresh returned no granted scope metadata"
            )
    except Exception as exc:
        result.blockers.append(f"recipient token refresh failed: {type(exc).__name__}")
        return result

    from app.integrations.google.mail_client import GoogleMailClient

    client = GoogleMailClient(
        api_url=credentials.api_url,
        access_token=access_token or "",
        user_id=credentials.user_id,
        refresh_token=credentials.refresh_token,
        client_id=credentials.client_id,
        client_secret=credentials.client_secret,
    )

    try:
        profile_email = client.get_profile_email().strip().lower()
        result.profile_email_redacted = _redact_email(profile_email)
        result.recipient_gmail_api_passed = True
        if profile_email != recipient:
            result.blockers.append("recipient Gmail profile email does not match allowlist")
        else:
            result.recipient_mailbox_identity_match = True
    except Exception as exc:
        result.blockers.append(f"recipient Gmail profile check failed: {type(exc).__name__}")
        return result

    try:
        labels = client.list_labels()
        if not isinstance(labels, list):
            result.blockers.append("recipient list_labels returned unexpected payload")
        else:
            result.recipient_list_labels_passed = True
    except Exception as exc:
        result.blockers.append(f"recipient list_labels failed: {type(exc).__name__}")
        return result

    intake_label = (config.intake_label or "").strip()
    query = f"label:{intake_label} is:unread" if intake_label else "in:inbox"
    try:
        page: GmailMessageListResult = client.list_messages_page(max_results=1, query=query)
        if page.message_ids is None:
            result.blockers.append("recipient read query returned invalid payload")
        else:
            result.recipient_read_query_passed = True
    except Exception as exc:
        result.blockers.append(f"recipient read query failed: {type(exc).__name__}")
        return result

    result.recipient_delivery_observation_ready = (
        result.recipient_oauth_configured
        and result.recipient_token_refresh_passed
        and result.recipient_gmail_api_passed
        and result.recipient_mailbox_identity_match
        and result.recipient_required_scopes_present
        and result.recipient_list_labels_passed
        and result.recipient_read_query_passed
        and not result.blockers
    )
    return result
