"""Duplicate-safe delivery observation for live Gmail eval (recipient mailbox)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parseaddr
from typing import Any

from sqlalchemy.orm import Session

from app.evaluation.live.config import LiveEvalConfig, get_live_eval_config
from app.evaluation.live.constants import (
    DELIVERY_CLOCK_SKEW_SECONDS,
    DELIVERY_FUTURE_SKEW_SECONDS,
    RUN_STATUS_ACTIVE,
    RUN_STATUS_REGISTERED,
    TERMINAL_RUN_STATUSES,
)
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.subject_parser import parse_body_marker, parse_subject_token
from app.integrations.enums import IntegrationType
from app.integrations.factory import get_integration_adapter
from app.integrations.service import get_integration_connection_config
from app.repositories.postgres.live_eval_models import LiveEvalRunRow

_DELIVERY_CANDIDATE_CAP = 2


@dataclass(frozen=True)
class DeliveryCandidate:
    message_id: str
    thread_id: str
    rfc_message_id: str
    sender_email: str
    recipient_email: str


@dataclass(frozen=True)
class DeliveryObservationResult:
    candidate_count: int
    valid_count: int
    duplicate_detected: bool
    confirmed: DeliveryCandidate | None
    rejection_reasons: list[str]


def _normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def _parse_email_header(header: str) -> str:
    _, email = parseaddr((header or "").strip())
    return email.strip().lower()


def _recipient_from_message(msg: dict[str, Any]) -> str:
    for key in ("to", "delivered_to", "cc"):
        parsed = _parse_email_header(str(msg.get(key) or ""))
        if parsed:
            return parsed
    return ""


def resolve_intake_label_id(adapter, label_name: str) -> str | None:
    labels_result = adapter.execute_action(action="list_labels", payload={})
    labels = labels_result.get("labels") or []
    for item in labels:
        if item.get("name") == label_name:
            label_id = item.get("id")
            return str(label_id) if label_id else None
    return None


def _label_id_present(msg: dict[str, Any], label_id: str) -> bool:
    label_ids = msg.get("label_ids") or []
    return label_id in label_ids


def _internal_date_in_window(
    msg: dict[str, Any],
    *,
    created_at: datetime,
    expires_at: datetime,
) -> bool:
    raw = msg.get("internal_date_ms")
    if raw is None:
        return False
    try:
        ms = int(raw)
    except (TypeError, ValueError):
        return False
    msg_at = datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc)
    window_start = created_at.astimezone(timezone.utc)
    if window_start.tzinfo is None:
        window_start = window_start.replace(tzinfo=timezone.utc)
    window_end = expires_at.astimezone(timezone.utc)
    if window_end.tzinfo is None:
        window_end = window_end.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    upper = min(window_end, now + timedelta(seconds=DELIVERY_FUTURE_SKEW_SECONDS))
    lower = window_start - timedelta(seconds=DELIVERY_CLOCK_SKEW_SECONDS)
    return lower.timestamp() <= msg_at.timestamp() <= upper.timestamp()


def build_delivery_query(
    *,
    evaluation_run_id: str,
    intake_label: str,
    run_created_at: datetime,
    unread_only: bool = True,
) -> str:
    created = run_created_at.astimezone(timezone.utc)
    after_epoch = int(created.timestamp()) - DELIVERY_CLOCK_SKEW_SECONDS
    unread = " is:unread" if unread_only else ""
    token = f"KROWOLF-EVAL/{evaluation_run_id}"
    return (
        f'label:{intake_label}{unread} after:{after_epoch} '
        f'subject:"{token}"'
    )


def validate_delivery_candidate(
    msg: dict[str, Any],
    *,
    row: LiveEvalRunRow,
    config: LiveEvalConfig,
    intake_label_id: str | None = None,
) -> tuple[bool, str | None]:
    subject = str(msg.get("subject") or "")
    parsed = parse_subject_token(subject)
    if parsed is None:
        return False, "missing_subject_token"
    if parsed.evaluation_run_id != row.evaluation_run_id:
        return False, "evaluation_run_id_mismatch"
    if parsed.scenario_id != row.scenario_id:
        return False, "scenario_id_mismatch"
    if parsed.attempt_id != row.attempt_id:
        return False, "attempt_id_mismatch"

    sender_email = _parse_email_header(str(msg.get("from") or ""))
    if sender_email != _normalize_email(row.expected_sender):
        return False, "sender_mismatch"

    recipient_email = _recipient_from_message(msg)
    if recipient_email and recipient_email != _normalize_email(row.expected_recipient):
        return False, "recipient_mismatch"

    body_marker = parse_body_marker(str(msg.get("body_text") or ""))
    if body_marker is not None and body_marker != row.evaluation_run_id:
        return False, "body_marker_mismatch"

    if not _internal_date_in_window(
        msg,
        created_at=row.created_at,
        expires_at=row.expires_at,
    ):
        return False, "internal_date_out_of_window"

    if intake_label_id and not _label_id_present(msg, intake_label_id):
        return False, "missing_intake_label"

    return True, None


def assert_delivery_observation_allowed(row: LiveEvalRunRow) -> None:
    if row.status == RUN_STATUS_REGISTERED:
        return
    if row.status == RUN_STATUS_ACTIVE:
        if row.root_gmail_message_id and row.root_job_id:
            return
        raise LiveEvalSafetyError("active run missing root binding for delivery observation")
    if row.status in TERMINAL_RUN_STATUSES:
        raise LiveEvalSafetyError(f"run status is terminal: {row.status}")
    raise LiveEvalSafetyError(f"run status {row.status!r} not allowed for delivery observation")


def observe_delivery_candidates(
    db: Session,
    row: LiveEvalRunRow,
    *,
    config: LiveEvalConfig | None = None,
    unread_only: bool = True,
    bound_message_id: str | None = None,
) -> DeliveryObservationResult:
    config = config or get_live_eval_config()
    assert_delivery_observation_allowed(row)

    connection_config = get_integration_connection_config(
        tenant_id=row.tenant_id,
        integration_type=IntegrationType.GOOGLE_MAIL,
        db=db,
    )
    adapter = get_integration_adapter(
        integration_type=IntegrationType.GOOGLE_MAIL,
        connection_config=connection_config,
    )
    intake_label_id = resolve_intake_label_id(adapter, config.intake_label)
    if not intake_label_id:
        raise LiveEvalSafetyError(f"intake label {config.intake_label!r} not found")

    if bound_message_id and row.status == RUN_STATUS_ACTIVE:
        detail = adapter.execute_action(
            action="get_message",
            payload={"message_id": bound_message_id},
        )
        msg = detail.get("message") or {}
        ok, reason = validate_delivery_candidate(
            msg, row=row, config=config, intake_label_id=intake_label_id
        )
        if not ok:
            return DeliveryObservationResult(
                candidate_count=1,
                valid_count=0,
                duplicate_detected=False,
                confirmed=None,
                rejection_reasons=[f"{bound_message_id}:{reason}"],
            )
        candidate = DeliveryCandidate(
            message_id=str(msg.get("message_id") or bound_message_id),
            thread_id=str(msg.get("thread_id") or ""),
            rfc_message_id=str(msg.get("internet_message_id") or ""),
            sender_email=_parse_email_header(str(msg.get("from") or "")),
            recipient_email=_recipient_from_message(msg)
            or _normalize_email(row.expected_recipient),
        )
        return DeliveryObservationResult(
            candidate_count=1,
            valid_count=1,
            duplicate_detected=False,
            confirmed=candidate,
            rejection_reasons=[],
        )

    query = build_delivery_query(
        evaluation_run_id=row.evaluation_run_id,
        intake_label=config.intake_label,
        run_created_at=row.created_at,
        unread_only=unread_only,
    )
    stub_ids = adapter.client.list_message_ids(
        max_results=_DELIVERY_CANDIDATE_CAP,
        query=query,
    )
    rejection_reasons: list[str] = []
    valid: list[DeliveryCandidate] = []

    for message_id in stub_ids:
        detail = adapter.execute_action(
            action="get_message",
            payload={"message_id": message_id},
        )
        msg = detail.get("message") or {}
        ok, reason = validate_delivery_candidate(
            msg, row=row, config=config, intake_label_id=intake_label_id
        )
        if not ok:
            rejection_reasons.append(f"{message_id}:{reason}")
            continue
        valid.append(
            DeliveryCandidate(
                message_id=str(msg.get("message_id") or message_id),
                thread_id=str(msg.get("thread_id") or ""),
                rfc_message_id=str(msg.get("internet_message_id") or ""),
                sender_email=_parse_email_header(str(msg.get("from") or "")),
                recipient_email=_recipient_from_message(msg)
                or _normalize_email(row.expected_recipient),
            )
        )

    duplicate = len(valid) > 1
    confirmed = valid[0] if len(valid) == 1 else None
    return DeliveryObservationResult(
        candidate_count=len(stub_ids),
        valid_count=len(valid),
        duplicate_detected=duplicate,
        confirmed=confirmed,
        rejection_reasons=rejection_reasons,
    )


def mask_email(email: str) -> str:
    email = _normalize_email(email)
    if "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"
