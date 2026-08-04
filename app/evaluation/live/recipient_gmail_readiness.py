"""Read-only recipient Gmail readiness for live eval delivery observation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.evaluation.live.config import LiveEvalConfig, get_live_eval_config
from app.evaluation.live.delivery_mailbox_reader import (
    CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV,
    CREDENTIAL_SOURCE_TENANT_GOOGLE_MAIL,
    probe_delivery_reader_read_only,
    resolve_delivery_mailbox_reader,
    resolve_r3_recipient_delivery_reader,
)
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.gmail_transport import RecipientCredentials, load_recipient_credentials
from app.integrations.google.mail_client import refresh_access_token_with_metadata
from app.repositories.postgres.live_eval_models import LiveEvalRunRow

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
    recipient_credential_source: str | None = None
    delivery_observation_credential_source: str | None = None
    credential_source_match: bool = False
    delivery_mailbox_identity_match: bool = False
    delivery_observation_path_ready: bool = False
    blockers: list[str] = field(default_factory=list)
    granted_scopes: list[str] = field(default_factory=list)
    profile_email_redacted: str | None = None

    @property
    def ready(self) -> bool:
        return (
            self.recipient_delivery_observation_ready
            and self.delivery_observation_path_ready
            and self.credential_source_match
            and not self.blockers
        )

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
            "recipient_credential_source": self.recipient_credential_source,
            "delivery_observation_credential_source": self.delivery_observation_credential_source,
            "credential_source_match": self.credential_source_match,
            "delivery_mailbox_identity_match": self.delivery_mailbox_identity_match,
            "delivery_observation_path_ready": self.delivery_observation_path_ready,
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
    db: Session | None = None,
    row: LiveEvalRunRow | None = None,
) -> RecipientGmailReadinessResult:
    """Verify recipient Gmail OAuth and the actual delivery observation reader path."""
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

    try:
        refresh = refresh_access_token_with_metadata(
            refresh_token=credentials.refresh_token,
            client_id=credentials.client_id,
            client_secret=credentials.client_secret,
        )
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

    r3_resolution = resolve_r3_recipient_delivery_reader(
        config=config,
        credentials=credentials,
        expected_recipient=recipient,
    )
    result.recipient_credential_source = r3_resolution.credential_source
    result.delivery_observation_credential_source = r3_resolution.credential_source
    result.credential_source_match = (
        r3_resolution.credential_source == CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV
    )
    result.profile_email_redacted = r3_resolution.mailbox_identity_redacted
    if r3_resolution.credential_source != CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV:
        result.blockers.append("R3 requires live_eval_recipient_env credential source")
        result.credential_source_match = False
    if not r3_resolution.ready:
        result.blockers.extend(r3_resolution.blockers)
        return result

    assert r3_resolution.reader is not None
    try:
        profile_email = r3_resolution.reader.get_profile_email().strip().lower()
        result.recipient_gmail_api_passed = True
        if profile_email != recipient:
            result.blockers.append("recipient Gmail profile email does not match allowlist")
        else:
            result.recipient_mailbox_identity_match = True
            result.delivery_mailbox_identity_match = True
    except Exception as exc:
        result.blockers.append(f"recipient Gmail profile check failed: {type(exc).__name__}")
        return result

    probe_ok, probe_blockers = probe_delivery_reader_read_only(
        r3_resolution.reader,
        config=config,
    )
    result.recipient_list_labels_passed = probe_ok
    result.recipient_read_query_passed = probe_ok
    if not probe_ok:
        result.blockers.extend(probe_blockers)

    if db is not None and row is not None:
        run_resolution = resolve_delivery_mailbox_reader(
            db=db,
            row=row,
            config=config,
            credentials=credentials,
        )
        result.delivery_observation_credential_source = run_resolution.credential_source
        result.credential_source_match = (
            result.recipient_credential_source == run_resolution.credential_source
            and run_resolution.credential_source == CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV
        )
        if not result.credential_source_match:
            result.blockers.append("recipient and delivery observation credential sources differ")
        if run_resolution.reader is not None and run_resolution.reader is not r3_resolution.reader:
            run_probe_ok, run_probe_blockers = probe_delivery_reader_read_only(
                run_resolution.reader,
                config=config,
            )
            if not run_probe_ok:
                result.blockers.extend(run_probe_blockers)
        elif not run_resolution.ready:
            result.blockers.extend(run_resolution.blockers)

    result.delivery_observation_path_ready = probe_ok and result.credential_source_match
    result.recipient_delivery_observation_ready = (
        result.recipient_oauth_configured
        and result.recipient_token_refresh_passed
        and result.recipient_gmail_api_passed
        and result.recipient_mailbox_identity_match
        and result.recipient_required_scopes_present
        and result.recipient_list_labels_passed
        and result.recipient_read_query_passed
        and result.delivery_observation_path_ready
        and result.credential_source_match
        and not result.blockers
    )
    return result


def run_r3_delivery_observation_readiness(
    *,
    expected_recipient: str,
    config: LiveEvalConfig | None = None,
    credentials: RecipientCredentials | None = None,
    db: Session | None = None,
    row: LiveEvalRunRow | None = None,
) -> RecipientGmailReadinessResult:
    """Alias for R3 postdeploy / JIT gates using the shared resolver path."""
    return run_recipient_gmail_readiness(
        expected_recipient=expected_recipient,
        config=config,
        credentials=credentials,
        db=db,
        row=row,
    )
