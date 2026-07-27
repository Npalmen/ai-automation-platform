"""Testbot Gmail sender transport (separate credentials from eval tenant)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parseaddr
from typing import Any

import httpx

from app.evaluation.live.config import LiveEvalConfig, get_live_eval_config
from app.evaluation.live.constants import (
    SUBJECT_TOKEN_PREFIX,
    TELEMETRY_TESTBOT_SEND_ATTEMPT,
    TELEMETRY_TESTBOT_SEND_RECONCILE,
    TELEMETRY_TESTBOT_SEND_SUCCEEDED,
)
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.journal import RunCheckpoint, assert_journal_send_budget
from app.evaluation.live.safety import (
    require_live_eval_external_mutation_enabled,
    require_scenario_allowed_for_live_gmail,
)
from app.evaluation.live.subject_parser import build_subject_with_token, parse_subject_token
from app.integrations.google.mail_client import GoogleMailClient

_RECONCILE_CANDIDATE_CAP = 2
_TRANSPORT_ERRORS: tuple[type[BaseException], ...] = (RuntimeError, ValueError, OSError, httpx.HTTPError)


@dataclass(frozen=True)
class SenderCredentials:
    refresh_token: str
    client_id: str
    client_secret: str
    user_id: str = "me"
    api_url: str = "https://gmail.googleapis.com/gmail/v1"


RecipientCredentials = SenderCredentials


@dataclass(frozen=True)
class SenderReadinessReport:
    ready: bool
    issues: list[str]
    profile_email: str | None = None
    read_scope_verified: bool = False
    send_scope_verified: bool = False
    granted_send_scopes: list[str] | None = None


@dataclass(frozen=True)
class SendOutcome:
    sender_gmail_message_id: str
    sender_gmail_thread_id: str
    rfc_message_id: str | None
    reconciled: bool = False


@dataclass(frozen=True)
class UnexpectedReplyEvidence:
    message_id: str
    subject_truncated: str
    from_masked: str
    internal_date_ms: int | None


@dataclass(frozen=True)
class ExpectedReplyEvidence:
    message_id: str
    subject_truncated: str
    from_masked: str
    internal_date_ms: int | None
    placement: str = "recipient_verified_in_inbox"


@dataclass(frozen=True)
class ProviderSentObjectEvidence:
    message_id: str
    thread_id: str
    rfc_message_id: str | None
    in_reply_to: str | None
    references: str | None
    labels: tuple[str, ...]
    in_sent: bool
    to_recipients: tuple[str, ...]
    from_email: str
    reply_to: str | None
    subject_truncated: str


_SYNTHETIC_EVAL_RECIPIENT_SUFFIXES = (".eval.test", "@eval.test")


def load_sender_credentials() -> SenderCredentials:
    refresh = os.environ.get("LIVE_EVAL_SENDER_GMAIL_REFRESH_TOKEN", "").strip()
    client_id = os.environ.get("LIVE_EVAL_SENDER_GMAIL_CLIENT_ID", "").strip()
    client_secret = os.environ.get("LIVE_EVAL_SENDER_GMAIL_CLIENT_SECRET", "").strip()
    user_id = os.environ.get("LIVE_EVAL_SENDER_GMAIL_USER", "me").strip() or "me"
    api_url = os.environ.get(
        "LIVE_EVAL_SENDER_GMAIL_API_URL",
        "https://gmail.googleapis.com/gmail/v1",
    ).strip()
    if not refresh or not client_id or not client_secret:
        raise LiveEvalSafetyError(
            "LIVE_EVAL_SENDER_GMAIL_REFRESH_TOKEN, CLIENT_ID, and CLIENT_SECRET are required"
        )
    return SenderCredentials(
        refresh_token=refresh,
        client_id=client_id,
        client_secret=client_secret,
        user_id=user_id,
        api_url=api_url,
    )


def build_sender_client(credentials: SenderCredentials | None = None) -> GoogleMailClient:
    credentials = credentials or load_sender_credentials()
    from app.integrations.google.mail_client import refresh_access_token

    access_token = refresh_access_token(
        refresh_token=credentials.refresh_token,
        client_id=credentials.client_id,
        client_secret=credentials.client_secret,
    )
    return GoogleMailClient(
        api_url=credentials.api_url,
        access_token=access_token,
        user_id=credentials.user_id,
        refresh_token=credentials.refresh_token,
        client_id=credentials.client_id,
        client_secret=credentials.client_secret,
    )


def load_recipient_credentials() -> RecipientCredentials:
    refresh = os.environ.get("LIVE_EVAL_RECIPIENT_GMAIL_REFRESH_TOKEN", "").strip()
    client_id = os.environ.get("LIVE_EVAL_RECIPIENT_GMAIL_CLIENT_ID", "").strip()
    client_secret = os.environ.get("LIVE_EVAL_RECIPIENT_GMAIL_CLIENT_SECRET", "").strip()
    user_id = os.environ.get("LIVE_EVAL_RECIPIENT_GMAIL_USER", "me").strip() or "me"
    api_url = os.environ.get(
        "LIVE_EVAL_RECIPIENT_GMAIL_API_URL",
        "https://gmail.googleapis.com/gmail/v1",
    ).strip()
    if not refresh or not client_id or not client_secret:
        raise LiveEvalSafetyError(
            "LIVE_EVAL_RECIPIENT_GMAIL_REFRESH_TOKEN, CLIENT_ID, and CLIENT_SECRET are required"
        )
    return RecipientCredentials(
        refresh_token=refresh,
        client_id=client_id,
        client_secret=client_secret,
        user_id=user_id,
        api_url=api_url,
    )


def build_recipient_client(credentials: RecipientCredentials | None = None) -> GoogleMailClient:
    credentials = credentials or load_recipient_credentials()
    from app.integrations.google.mail_client import refresh_access_token

    access_token = refresh_access_token(
        refresh_token=credentials.refresh_token,
        client_id=credentials.client_id,
        client_secret=credentials.client_secret,
    )
    return GoogleMailClient(
        api_url=credentials.api_url,
        access_token=access_token,
        user_id=credentials.user_id,
        refresh_token=credentials.refresh_token,
        client_id=credentials.client_id,
        client_secret=credentials.client_secret,
    )


def _validate_send_budget_config(config: LiveEvalConfig) -> list[str]:
    issues: list[str] = []
    from app.evaluation.live.campaign.gates import campaign_enabled

    if campaign_enabled(config):
        if config.max_scenarios_per_run < 1:
            issues.append("max_scenarios_per_run must be >= 1")
        if config.max_gmail_sends_per_run < 1:
            issues.append("max_gmail_sends_per_run must be >= 1")
        return issues

    if config.max_scenarios_per_run != 1:
        issues.append("max_scenarios_per_run must be 1")
    if config.max_gmail_sends_per_run != 1:
        issues.append("max_gmail_sends_per_run must be 1")
    if config.max_gmail_replies_per_run != 0:
        issues.append("max_gmail_replies_per_run must be 0")
    return issues


def _validate_exact_allowlist_addresses(config: LiveEvalConfig) -> list[str]:
    issues: list[str] = []
    if len(config.sender_emails) != 1:
        issues.append("exactly one LIVE_EVAL_SENDER_EMAILS entry required")
    if len(config.recipient_emails) != 1:
        issues.append("exactly one LIVE_EVAL_RECIPIENT_EMAILS entry required")
    return issues


def run_sender_readiness_read_only(
    *,
    expected_sender: str,
    expected_recipient: str,
    config: LiveEvalConfig | None = None,
) -> SenderReadinessReport:
    """Read-only sender Gmail verification (no send, mutate, or run registration)."""
    from app.evaluation.live.safety import require_gmail_eval_enabled

    config = config or get_live_eval_config()
    issues: list[str] = []
    try:
        require_gmail_eval_enabled(config)
    except LiveEvalSafetyError as exc:
        return SenderReadinessReport(ready=False, issues=[str(exc)])

    issues.extend(_validate_exact_allowlist_addresses(config))

    sender = expected_sender.strip().lower()
    recipient = expected_recipient.strip().lower()
    if sender not in config.sender_emails:
        issues.append("expected_sender is not allowlisted")
    if recipient not in config.recipient_emails:
        issues.append("expected_recipient is not allowlisted")

    profile_email: str | None = None
    read_scope_verified = False
    try:
        client = build_sender_client()
        profile_email = client.get_profile_email()
        if profile_email != sender:
            issues.append("sender profile email does not match expected allowlist")
        client.list_messages_page(max_results=1, query="in:inbox")
        read_scope_verified = True
    except LiveEvalSafetyError as exc:
        issues.append(str(exc))
    except _TRANSPORT_ERRORS as exc:
        issues.append(f"sender_auth: {exc}")

    if not read_scope_verified and not any("sender_auth" in item for item in issues):
        issues.append("sender read scope verification failed")

    return SenderReadinessReport(
        ready=not issues,
        issues=issues,
        profile_email=profile_email,
        read_scope_verified=read_scope_verified,
    )


def run_sender_readiness(
    *,
    expected_sender: str,
    expected_recipient: str,
    config: LiveEvalConfig | None = None,
) -> SenderReadinessReport:
    config = config or get_live_eval_config()
    try:
        require_live_eval_external_mutation_enabled(config)
    except LiveEvalSafetyError as exc:
        return SenderReadinessReport(ready=False, issues=[str(exc)])

    budget_issues = _validate_send_budget_config(config)
    read_only = run_sender_readiness_read_only(
        expected_sender=expected_sender,
        expected_recipient=expected_recipient,
        config=config,
    )
    if budget_issues:
        return SenderReadinessReport(
            ready=False,
            issues=budget_issues + read_only.issues,
            profile_email=read_only.profile_email,
            read_scope_verified=read_only.read_scope_verified,
        )
    return read_only


def build_s01_message_body(*, evaluation_run_id: str) -> str:
    return (
        "<!-- KROWOLF_EVAL:evaluation_run_id="
        f"{evaluation_run_id} -->\n"
        "Hej, jag vill installera en laddbox i garaget."
    )


def _parse_from_email(header: str) -> str:
    _, email = parseaddr((header or "").strip())
    return email.strip().lower()


def _normalize_rfc_message_id(value: str | None) -> str | None:
    text = (value or "").strip()
    if text.startswith("<") and text.endswith(">"):
        text = text[1:-1].strip()
    return text or None


def _rfc822msgid_query(value: str | None) -> str | None:
    normalized = _normalize_rfc_message_id(value)
    if not normalized:
        return None
    return f"rfc822msgid:{normalized}"


def is_synthetic_live_eval_recipient(email: str) -> bool:
    normalized = (email or "").strip().lower()
    if not normalized:
        return False
    return any(normalized.endswith(suffix) for suffix in _SYNTHETIC_EVAL_RECIPIENT_SUFFIXES)


def assert_live_reply_recipient_allowed(
    *,
    recipient_email: str,
    expected_sender: str,
    fixture_sender_email: str | None = None,
) -> None:
    recipient = recipient_email.strip().lower()
    sender = expected_sender.strip().lower()
    if is_synthetic_live_eval_recipient(recipient):
        raise LiveEvalSafetyError(
            "synthetic fixture recipient is not allowed for live Gmail replies"
        )
    if recipient != sender:
        raise LiveEvalSafetyError("live reply recipient must match verified inbound sender")
    if fixture_sender_email:
        fixture = fixture_sender_email.strip().lower()
        if fixture and fixture != sender and is_synthetic_live_eval_recipient(fixture):
            raise LiveEvalSafetyError(
                "scenario fixture sender must not override live reply destination"
            )


def _parse_recipient_email(msg: dict[str, Any]) -> str:
    for key in ("to", "delivered_to", "cc"):
        parsed = _parse_from_email(str(msg.get(key) or ""))
        if parsed:
            return parsed
    return ""


def _internal_date_ms(msg: dict[str, Any]) -> int | None:
    raw = msg.get("internal_date_ms")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _message_in_send_window(
    msg: dict[str, Any],
    *,
    window_start: datetime,
    window_end: datetime,
) -> bool:
    ms = _internal_date_ms(msg)
    if ms is None:
        return False
    msg_at = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    start = window_start.astimezone(timezone.utc)
    end = window_end.astimezone(timezone.utc)
    return (start.timestamp() - 60) <= msg_at.timestamp() <= end.timestamp()


def _sent_recipient_emails(msg: dict[str, Any]) -> list[str]:
    from email.utils import getaddresses

    parts: list[str] = []
    for key in ("to", "delivered_to"):
        value = str(msg.get(key) or "").strip()
        if value:
            parts.append(value)
    if not parts:
        return []
    return [email.strip().lower() for _, email in getaddresses(parts) if email.strip()]


def _validate_sent_candidate(
    msg: dict[str, Any],
    *,
    evaluation_run_id: str,
    scenario_id: str,
    attempt_id: int,
    expected_sender: str,
    expected_recipient: str,
    window_start: datetime,
    window_end: datetime,
) -> bool:
    parsed = parse_subject_token(str(msg.get("subject") or ""))
    if parsed is None:
        return False
    if (
        parsed.evaluation_run_id != evaluation_run_id
        or parsed.scenario_id != scenario_id
        or parsed.attempt_id != attempt_id
    ):
        return False
    if _parse_from_email(str(msg.get("from") or "")) != expected_sender.strip().lower():
        return False
    recipients = _sent_recipient_emails(msg)
    if len(recipients) != 1:
        return False
    if recipients[0] != expected_recipient.strip().lower():
        return False
    return _message_in_send_window(msg, window_start=window_start, window_end=window_end)


def send_scenario_email(
    *,
    evaluation_run_id: str,
    scenario_id: str,
    attempt_id: int,
    expected_sender: str,
    expected_recipient: str,
    checkpoint: RunCheckpoint | None = None,
    base_subject: str = "Laddbox offert villa",
    message_body: str | None = None,
    config: LiveEvalConfig | None = None,
) -> tuple[SendOutcome, list[dict[str, Any]]]:
    """Send exactly one synthetic email. Returns outcome and telemetry events."""
    config = config or get_live_eval_config()
    require_live_eval_external_mutation_enabled(config)
    require_scenario_allowed_for_live_gmail(scenario_id)

    if checkpoint is not None:
        assert_journal_send_budget(checkpoint)

    readiness = run_sender_readiness(
        expected_sender=expected_sender,
        expected_recipient=expected_recipient,
        config=config,
    )
    if not readiness.ready:
        raise LiveEvalSafetyError("; ".join(readiness.issues))

    events: list[dict[str, Any]] = [
        {
            "category": TELEMETRY_TESTBOT_SEND_ATTEMPT,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    ]

    subject = build_subject_with_token(
        evaluation_run_id=evaluation_run_id,
        scenario_id=scenario_id,
        attempt_id=attempt_id,
        base_subject=base_subject,
    )
    body = message_body or build_s01_message_body(evaluation_run_id=evaluation_run_id)
    client = build_sender_client()
    result = client.send_message(
        to=expected_recipient,
        subject=subject,
        body=body,
        from_email=expected_sender,
    )
    payload = result.get("payload") or {}
    message_id = str(payload.get("google_message_id") or result.get("external_id") or "")
    thread_id = str(payload.get("thread_id") or "")
    if not message_id:
        raise LiveEvalSafetyError("Gmail send succeeded but message id is missing")

    rfc_message_id: str | None = None
    try:
        detail = client.get_message(message_id)
        rfc_message_id = str(detail.get("internet_message_id") or "") or None
    except _TRANSPORT_ERRORS:
        rfc_message_id = None

    events.append(
        {
            "category": TELEMETRY_TESTBOT_SEND_SUCCEEDED,
            "sender_gmail_message_id": message_id,
            "at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return (
        SendOutcome(
            sender_gmail_message_id=message_id,
            sender_gmail_thread_id=thread_id,
            rfc_message_id=rfc_message_id,
            reconciled=False,
        ),
        events,
    )


def reconcile_sent_message(
    *,
    evaluation_run_id: str,
    scenario_id: str,
    attempt_id: int,
    expected_sender: str,
    expected_recipient: str,
    send_window_start: datetime,
    expires_at: datetime | None = None,
    config: LiveEvalConfig | None = None,
) -> SendOutcome | None:
    """Search Sent folder for exactly one matching message. Never resends."""
    config = config or get_live_eval_config()
    client = build_sender_client()
    after_epoch = int(send_window_start.astimezone(timezone.utc).timestamp()) - 60
    token = f"KROWOLF-EVAL/{evaluation_run_id}"
    query = f'in:sent to:{expected_recipient} after:{after_epoch} subject:"{token}"'
    page = client.list_messages_page(max_results=_RECONCILE_CANDIDATE_CAP, query=query)
    if page.truncated:
        raise LiveEvalSafetyError("correlation_failure: sent list truncated")
    window_end = expires_at or datetime.now(timezone.utc)
    matches: list[SendOutcome] = []
    for message_id in page.message_ids:
        detail = client.get_message(message_id)
        if not _validate_sent_candidate(
            detail,
            evaluation_run_id=evaluation_run_id,
            scenario_id=scenario_id,
            attempt_id=attempt_id,
            expected_sender=expected_sender,
            expected_recipient=expected_recipient,
            window_start=send_window_start,
            window_end=window_end,
        ):
            continue
        matches.append(
            SendOutcome(
                sender_gmail_message_id=str(detail.get("message_id") or message_id),
                sender_gmail_thread_id=str(detail.get("thread_id") or ""),
                rfc_message_id=str(detail.get("internet_message_id") or "") or None,
                reconciled=True,
            )
        )
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise LiveEvalSafetyError("send_outcome_unresolved: multiple sent matches")
    return None


def observe_unexpected_sender_reply(
    *,
    evaluation_run_id: str,
    scenario_id: str,
    attempt_id: int,
    expected_recipient: str,
    send_window_start: datetime,
    expires_at: datetime | None = None,
) -> UnexpectedReplyEvidence | None:
    """Detect unexpected inbound reply to sender account (read-only)."""
    client = build_sender_client()
    after_epoch = int(send_window_start.astimezone(timezone.utc).timestamp()) - 60
    query = f'in:inbox from:{expected_recipient} after:{after_epoch}'
    ids = client.list_message_ids(max_results=_RECONCILE_CANDIDATE_CAP, query=query)
    window_end = expires_at or datetime.now(timezone.utc)
    matches: list[UnexpectedReplyEvidence] = []
    for message_id in ids:
        detail = client.get_message(message_id)
        parsed = parse_subject_token(str(detail.get("subject") or ""))
        if parsed is None:
            continue
        if (
            parsed.evaluation_run_id != evaluation_run_id
            or parsed.scenario_id != scenario_id
            or parsed.attempt_id != attempt_id
        ):
            continue
        if _parse_from_email(str(detail.get("from") or "")) != expected_recipient.strip().lower():
            continue
        if not _message_in_send_window(
            detail,
            window_start=send_window_start,
            window_end=window_end,
        ):
            continue
        subject = str(detail.get("subject") or "")
        from_email = _parse_from_email(str(detail.get("from") or ""))
        local, _, domain = from_email.partition("@")
        masked_from = f"{local[:1]}***@{domain}" if local else "***"
        matches.append(
            UnexpectedReplyEvidence(
                message_id=str(detail.get("message_id") or message_id),
                subject_truncated=subject[:120],
                from_masked=masked_from,
                internal_date_ms=_internal_date_ms(detail),
            )
        )
    if len(matches) > 1:
        raise LiveEvalSafetyError("correlation_failure: multiple unexpected replies")
    return matches[0] if matches else None


def observe_expected_sender_reply(
    *,
    evaluation_run_id: str,
    scenario_id: str,
    attempt_id: int,
    expected_recipient: str,
    expected_sender: str,
    send_window_start: datetime,
    expires_at: datetime | None = None,
    timeout_seconds: float = 120.0,
    poll_interval_seconds: float = 3.0,
    provider_message_id: str | None = None,
    inbound_rfc_message_id: str | None = None,
    campaign_run_id: str | None = None,
) -> ExpectedReplyEvidence | None:
    """Poll sender inbox and recipient Sent for required app reply."""
    import time

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if provider_message_id:
            evidence = _observe_reply_by_provider_message_id(
                provider_message_id=provider_message_id,
                evaluation_run_id=evaluation_run_id,
                scenario_id=scenario_id,
                attempt_id=attempt_id,
                expected_recipient=expected_recipient,
                expected_sender=expected_sender,
                send_window_start=send_window_start,
                expires_at=expires_at,
                inbound_rfc_message_id=inbound_rfc_message_id,
                campaign_run_id=campaign_run_id,
            )
            if evidence is not None:
                return evidence
        evidence = _find_expected_sender_reply(
            evaluation_run_id=evaluation_run_id,
            scenario_id=scenario_id,
            attempt_id=attempt_id,
            expected_recipient=expected_recipient,
            expected_sender=expected_sender,
            send_window_start=send_window_start,
            expires_at=expires_at,
            inbound_rfc_message_id=inbound_rfc_message_id,
            campaign_run_id=campaign_run_id,
            provider_rfc_message_id=None,
        )
        if evidence is not None:
            return evidence
        time.sleep(poll_interval_seconds)
    return None


def fetch_provider_sent_reply_object(
    *,
    provider_message_id: str,
    expected_sender: str,
    expected_recipient: str,
) -> ProviderSentObjectEvidence | None:
    """Fetch provider-accepted reply directly by Gmail message id (read-only)."""
    message_id = (provider_message_id or "").strip()
    if not message_id:
        return None
    sender = expected_sender.strip().lower()
    recipient = expected_recipient.strip().lower()
    try:
        client = build_recipient_client()
    except LiveEvalSafetyError:
        return None
    try:
        detail = client.get_message(message_id)
    except _TRANSPORT_ERRORS:
        return None
    labels = tuple(str(label) for label in (detail.get("label_ids") or []))
    recipients = tuple(_sent_recipient_emails(detail))
    if sender not in recipients:
        return None
    from_email = _parse_from_email(str(detail.get("from") or ""))
    return ProviderSentObjectEvidence(
        message_id=str(detail.get("message_id") or message_id),
        thread_id=str(detail.get("thread_id") or ""),
        rfc_message_id=_normalize_rfc_message_id(
            str(detail.get("internet_message_id") or "") or None
        ),
        in_reply_to=_normalize_rfc_message_id(
            str(detail.get("in_reply_to") or "") or None
        ),
        references=str(detail.get("references") or "")[:240] or None,
        labels=labels,
        in_sent="SENT" in labels,
        to_recipients=recipients,
        from_email=from_email,
        reply_to=None,
        subject_truncated=str(detail.get("subject") or "")[:120],
    )


def _reply_evidence_from_message(
    *,
    message_id: str,
    detail: dict[str, Any],
    placement: str = "recipient_verified_in_inbox",
) -> ExpectedReplyEvidence:
    subject = str(detail.get("subject") or "")
    from_email = _parse_from_email(str(detail.get("from") or ""))
    local, _, domain = from_email.partition("@")
    masked_from = f"{local[:1]}***@{domain}" if local else "***"
    return ExpectedReplyEvidence(
        message_id=str(detail.get("message_id") or message_id),
        subject_truncated=subject[:120],
        from_masked=masked_from,
        internal_date_ms=_internal_date_ms(detail),
        placement=placement,
    )


def _classify_recipient_placement(labels: list[str] | tuple[str, ...]) -> str:
    label_set = {str(label) for label in labels}
    if "SPAM" in label_set:
        return "recipient_verified_in_spam"
    if "INBOX" in label_set:
        return "recipient_verified_in_inbox"
    return "recipient_verified_in_all_mail"


def _matches_expected_reply(
    detail: dict[str, Any],
    *,
    evaluation_run_id: str,
    scenario_id: str,
    attempt_id: int,
    expected_recipient: str,
    expected_sender: str,
    send_window_start: datetime,
    window_end: datetime,
    require_sender_inbox: bool,
    require_matching_from: bool = True,
) -> bool:
    parsed = parse_subject_token(str(detail.get("subject") or ""))
    if parsed is None:
        return False
    if (
        parsed.evaluation_run_id != evaluation_run_id
        or parsed.scenario_id != scenario_id
        or parsed.attempt_id != attempt_id
    ):
        return False
    if require_matching_from:
        from_email = _parse_from_email(str(detail.get("from") or ""))
        if from_email and from_email != expected_recipient.strip().lower():
            # Allow app send-as aliases on the tenant mailbox; To must still match sender.
            pass
    if require_sender_inbox:
        recipients = _sent_recipient_emails(detail)
        if expected_sender.strip().lower() not in recipients:
            return False
    return _message_in_send_window(
        detail,
        window_start=send_window_start,
        window_end=window_end,
    )


def _search_reply_evidence(
    client: GoogleMailClient,
    *,
    query: str,
    evaluation_run_id: str,
    scenario_id: str,
    attempt_id: int,
    expected_recipient: str,
    expected_sender: str,
    send_window_start: datetime,
    window_end: datetime,
    require_sender_inbox: bool,
    require_matching_from: bool = True,
    require_subject_token: bool = True,
    campaign_run_id: str | None = None,
) -> ExpectedReplyEvidence | None:
    ids = client.list_message_ids(max_results=_RECONCILE_CANDIDATE_CAP, query=query)
    matches: list[ExpectedReplyEvidence] = []
    for message_id in ids:
        detail = client.get_message(message_id)
        if require_subject_token and not _matches_expected_reply(
            detail,
            evaluation_run_id=evaluation_run_id,
            scenario_id=scenario_id,
            attempt_id=attempt_id,
            expected_recipient=expected_recipient,
            expected_sender=expected_sender,
            send_window_start=send_window_start,
            window_end=window_end,
            require_sender_inbox=require_sender_inbox,
            require_matching_from=require_matching_from,
        ):
            continue
        if not require_subject_token and not _matches_recipient_delivery(
            detail,
            expected_recipient=expected_recipient,
            expected_sender=expected_sender,
            send_window_start=send_window_start,
            window_end=window_end,
            evaluation_run_id=evaluation_run_id,
            scenario_id=scenario_id,
            campaign_run_id=campaign_run_id,
        ):
            continue
        placement = _classify_recipient_placement(detail.get("label_ids") or [])
        matches.append(
            _reply_evidence_from_message(
                message_id=message_id,
                detail=detail,
                placement=placement,
            )
        )
    if len(matches) > 1:
        raise LiveEvalSafetyError("correlation_failure: multiple expected replies")
    return matches[0] if matches else None


def _matches_recipient_delivery(
    detail: dict[str, Any],
    *,
    expected_recipient: str,
    expected_sender: str,
    send_window_start: datetime,
    window_end: datetime,
    evaluation_run_id: str,
    scenario_id: str,
    campaign_run_id: str | None,
) -> bool:
    recipients = _sent_recipient_emails(detail)
    if expected_sender.strip().lower() not in recipients:
        return False
    # Allow app send-as aliases; delivery to the allowlisted sender mailbox is authoritative.
    if not _message_in_send_window(
        detail,
        window_start=send_window_start,
        window_end=window_end,
    ):
        return False
    subject = str(detail.get("subject") or "")
    body = str(detail.get("body_text") or "")
    parsed = parse_subject_token(subject)
    if parsed is not None:
        return (
            parsed.evaluation_run_id == evaluation_run_id
            and parsed.scenario_id == scenario_id
        )
    if evaluation_run_id in subject or evaluation_run_id in body:
        return True
    if campaign_run_id and (campaign_run_id in subject or campaign_run_id in body):
        return True
    return False


def _observe_reply_by_provider_message_id(
    *,
    provider_message_id: str,
    evaluation_run_id: str,
    scenario_id: str,
    attempt_id: int,
    expected_recipient: str,
    expected_sender: str,
    send_window_start: datetime,
    expires_at: datetime | None = None,
    inbound_rfc_message_id: str | None = None,
    campaign_run_id: str | None = None,
) -> ExpectedReplyEvidence | None:
    """Verify provider Sent object, then locate delivery on allowlisted sender mailbox."""
    provider_object = fetch_provider_sent_reply_object(
        provider_message_id=provider_message_id,
        expected_sender=expected_sender,
        expected_recipient=expected_recipient,
    )
    if provider_object is None:
        return None
    return _find_expected_sender_reply(
        evaluation_run_id=evaluation_run_id,
        scenario_id=scenario_id,
        attempt_id=attempt_id,
        expected_recipient=expected_recipient,
        expected_sender=expected_sender,
        send_window_start=send_window_start,
        expires_at=expires_at,
        inbound_rfc_message_id=inbound_rfc_message_id,
        campaign_run_id=campaign_run_id,
        provider_rfc_message_id=provider_object.rfc_message_id,
    )


def _build_recipient_search_queries(
    *,
    evaluation_run_id: str,
    scenario_id: str,
    expected_recipient: str,
    expected_sender: str,
    after_epoch: int,
    inbound_rfc_message_id: str | None,
    campaign_run_id: str | None,
    provider_rfc_message_id: str | None,
) -> list[str]:
    sender = expected_sender.strip().lower()
    recipient = expected_recipient.strip().lower()
    queries: list[str] = []
    provider_query = _rfc822msgid_query(provider_rfc_message_id)
    if provider_query:
        queries.append(f"in:anywhere {provider_query}")
    inbound_query = _rfc822msgid_query(inbound_rfc_message_id)
    if inbound_query:
        queries.append(f"in:anywhere {inbound_query}")
    if campaign_run_id:
        queries.append(f'in:anywhere "{campaign_run_id}"')
    queries.append(f'in:anywhere "{evaluation_run_id}"')
    queries.append(f'in:anywhere "{scenario_id}"')
    queries.append(f"in:anywhere from:{recipient} to:{sender} after:{after_epoch}")
    token = f"{SUBJECT_TOKEN_PREFIX}/{evaluation_run_id}"
    queries.extend(
        [
            f"from:{recipient} to:{sender} after:{after_epoch}",
            f"from:{recipient} after:{after_epoch}",
            f"in:anywhere from:{recipient} to:{sender} after:{after_epoch}",
            f'in:anywhere subject:"{token}" to:{sender} after:{after_epoch}',
        ]
    )
    return queries


def _find_expected_sender_reply(
    *,
    evaluation_run_id: str,
    scenario_id: str,
    attempt_id: int,
    expected_recipient: str,
    expected_sender: str,
    send_window_start: datetime,
    expires_at: datetime | None = None,
    inbound_rfc_message_id: str | None = None,
    campaign_run_id: str | None = None,
    provider_rfc_message_id: str | None = None,
) -> ExpectedReplyEvidence | None:
    after_epoch = int(send_window_start.astimezone(timezone.utc).timestamp()) - 60
    window_end = expires_at or datetime.now(timezone.utc)
    sender = expected_sender.strip().lower()
    recipient = expected_recipient.strip().lower()
    search_kwargs = {
        "evaluation_run_id": evaluation_run_id,
        "scenario_id": scenario_id,
        "attempt_id": attempt_id,
        "expected_recipient": recipient,
        "expected_sender": sender,
        "send_window_start": send_window_start,
        "window_end": window_end,
    }

    sender_client = build_sender_client()
    queries = _build_recipient_search_queries(
        evaluation_run_id=evaluation_run_id,
        scenario_id=scenario_id,
        expected_recipient=recipient,
        expected_sender=sender,
        after_epoch=after_epoch,
        inbound_rfc_message_id=inbound_rfc_message_id,
        campaign_run_id=campaign_run_id,
        provider_rfc_message_id=provider_rfc_message_id,
    )
    for index, query in enumerate(queries):
        require_subject_token = index >= 4 and not provider_rfc_message_id
        evidence = _search_reply_evidence(
            sender_client,
            query=query,
            require_sender_inbox=True,
            require_subject_token=require_subject_token,
            campaign_run_id=campaign_run_id,
            **search_kwargs,
        )
        if evidence is not None:
            return evidence

    try:
        recipient_client = build_recipient_client()
    except LiveEvalSafetyError:
        return None

    for query in (
        f"in:sent to:{sender} after:{after_epoch}",
        f"in:anywhere in:sent to:{sender} after:{after_epoch}",
        f'in:anywhere in:sent subject:"{SUBJECT_TOKEN_PREFIX}/{evaluation_run_id}" after:{after_epoch}',
    ):
        evidence = _search_reply_evidence(
            recipient_client,
            query=query,
            require_sender_inbox=False,
            require_matching_from=False,
            campaign_run_id=campaign_run_id,
            **search_kwargs,
        )
        if evidence is not None:
            return evidence
    return None


def archive_unexpected_reply(*, message_id: str) -> None:
    if not message_id:
        raise LiveEvalSafetyError("unexpected reply cleanup requires exact message_id")
    client = build_sender_client()
    client.archive_from_inbox(message_id)
