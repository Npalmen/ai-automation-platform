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
    TELEMETRY_TESTBOT_SEND_ATTEMPT,
    TELEMETRY_TESTBOT_SEND_RECONCILE,
    TELEMETRY_TESTBOT_SEND_SUCCEEDED,
)
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.journal import RunCheckpoint, assert_journal_send_budget
from app.evaluation.live.safety import (
    require_live_eval_external_mutation_enabled,
    require_scenario_allowed_for_2f2,
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


@dataclass(frozen=True)
class SenderReadinessReport:
    ready: bool
    issues: list[str]
    profile_email: str | None = None


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


def _validate_send_budget_config(config: LiveEvalConfig) -> list[str]:
    issues: list[str] = []
    if config.max_scenarios_per_run != 1:
        issues.append("max_scenarios_per_run must be 1")
    if config.max_gmail_sends_per_run != 1:
        issues.append("max_gmail_sends_per_run must be 1")
    if config.max_gmail_replies_per_run != 0:
        issues.append("max_gmail_replies_per_run must be 0")
    return issues


def run_sender_readiness(
    *,
    expected_sender: str,
    expected_recipient: str,
    config: LiveEvalConfig | None = None,
) -> SenderReadinessReport:
    config = config or get_live_eval_config()
    issues: list[str] = []
    try:
        require_live_eval_external_mutation_enabled(config)
    except LiveEvalSafetyError as exc:
        return SenderReadinessReport(ready=False, issues=[str(exc)])

    issues.extend(_validate_send_budget_config(config))

    sender = expected_sender.strip().lower()
    recipient = expected_recipient.strip().lower()
    if sender not in config.sender_emails:
        issues.append("expected_sender is not allowlisted")
    if recipient not in config.recipient_emails:
        issues.append("expected_recipient is not allowlisted")

    profile_email: str | None = None
    try:
        client = build_sender_client()
        profile_email = client.get_profile_email()
        if profile_email != sender:
            issues.append("sender profile email does not match expected allowlist")
    except LiveEvalSafetyError as exc:
        issues.append(str(exc))
    except _TRANSPORT_ERRORS as exc:
        issues.append(f"sender_auth: {exc}")

    return SenderReadinessReport(
        ready=not issues,
        issues=issues,
        profile_email=profile_email,
    )


def build_s01_message_body(*, evaluation_run_id: str) -> str:
    return (
        "<!-- KROWOLF_EVAL:evaluation_run_id="
        f"{evaluation_run_id} -->\n"
        "Hej, jag vill installera en laddbox i garaget."
    )


def _parse_from_email(header: str) -> str:
    _, email = parseaddr((header or "").strip())
    return email.strip().lower()


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
    recipient = _parse_recipient_email(msg)
    if recipient and recipient != expected_recipient.strip().lower():
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
    config: LiveEvalConfig | None = None,
) -> tuple[SendOutcome, list[dict[str, Any]]]:
    """Send exactly one synthetic email. Returns outcome and telemetry events."""
    config = config or get_live_eval_config()
    require_live_eval_external_mutation_enabled(config)
    require_scenario_allowed_for_2f2(scenario_id)

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
    body = build_s01_message_body(evaluation_run_id=evaluation_run_id)
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
    stub_ids = client.list_message_ids(max_results=_RECONCILE_CANDIDATE_CAP, query=query)
    window_end = expires_at or datetime.now(timezone.utc)
    matches: list[SendOutcome] = []
    for message_id in stub_ids:
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


def archive_unexpected_reply(*, message_id: str) -> None:
    if not message_id:
        raise LiveEvalSafetyError("unexpected reply cleanup requires exact message_id")
    client = build_sender_client()
    client.archive_from_inbox(message_id)
