"""Credential resolver and read-only mailbox reader for delivery observation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.evaluation.live.config import LiveEvalConfig, get_live_eval_config
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.gmail_transport import (
    RecipientCredentials,
    build_recipient_client,
    load_recipient_credentials,
)
from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.integrations.enums import IntegrationType
from app.integrations.factory import get_integration_adapter
from app.integrations.google.mail_client import GmailMessageListResult, GoogleMailClient
from app.integrations.service import get_integration_connection_config
from app.repositories.postgres.live_eval_models import LiveEvalRunRow

CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV = "live_eval_recipient_env"
CREDENTIAL_SOURCE_TENANT_GOOGLE_MAIL = "tenant_google_mail_integration"
# Must match coworker_r3_registration_contract.R3_FROZEN_EXECUTION_MODE (avoid circular import).
_R3_FROZEN_EXECUTION_MODE = "r3_frozen_approved_body"


class DeliveryMailboxReader(Protocol):
    def list_labels(self) -> list[dict[str, Any]]: ...

    def list_messages_page(
        self, *, max_results: int, query: str
    ) -> GmailMessageListResult: ...

    def get_message(self, message_id: str) -> dict[str, Any]: ...

    def get_profile_email(self) -> str: ...


@dataclass
class DeliveryMailboxReaderResolution:
    reader: DeliveryMailboxReader | None = None
    credential_source: str | None = None
    mailbox_identity_redacted: str | None = None
    source_allowed: bool = False
    source_matches_readiness: bool = False
    blockers: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.source_allowed and self.reader is not None and not self.blockers


def _redact_email(value: str | None) -> str | None:
    if not value or "@" not in value:
        return value
    local, _, domain = value.partition("@")
    return f"{local[:2]}…@{domain}"


class GoogleMailClientDeliveryReader:
    """Read-only delivery reader backed by a direct GoogleMailClient."""

    def __init__(self, client: GoogleMailClient):
        self._client = client

    def list_labels(self) -> list[dict[str, Any]]:
        return self._client.list_labels()

    def list_messages_page(
        self, *, max_results: int, query: str
    ) -> GmailMessageListResult:
        return self._client.list_messages_page(max_results=max_results, query=query)

    def get_message(self, message_id: str) -> dict[str, Any]:
        return self._client.get_message(message_id)

    def get_profile_email(self) -> str:
        return self._client.get_profile_email()


class TenantIntegrationDeliveryReader:
    """Read-only delivery reader backed by tenant GOOGLE_MAIL integration."""

    def __init__(self, adapter: Any):
        self._adapter = adapter

    def list_labels(self) -> list[dict[str, Any]]:
        result = self._adapter.execute_action(action="list_labels", payload={})
        labels = result.get("labels") or []
        if not isinstance(labels, list):
            raise RuntimeError("list_labels returned unexpected payload")
        return labels

    def list_messages_page(
        self, *, max_results: int, query: str
    ) -> GmailMessageListResult:
        return self._adapter.client.list_messages_page(
            max_results=max_results,
            query=query,
        )

    def get_message(self, message_id: str) -> dict[str, Any]:
        result = self._adapter.execute_action(
            action="get_message",
            payload={"message_id": message_id},
        )
        message = result.get("message") or {}
        if not isinstance(message, dict):
            raise RuntimeError("get_message returned unexpected payload")
        return message

    def get_profile_email(self) -> str:
        result = self._adapter.execute_action(action="get_profile", payload={})
        email = str(result.get("email_address") or "").strip()
        if not email:
            raise RuntimeError("get_profile returned no email_address")
        return email


def is_r3_frozen_live_eval_run(row: LiveEvalRunRow) -> bool:
    return (
        row.tenant_id == LIVE_EVAL_TENANT_ID
        and row.transport_mode == "live_gmail"
        and row.ai_mode == _R3_FROZEN_EXECUTION_MODE
    )


def resolve_r3_recipient_delivery_reader(
    *,
    config: LiveEvalConfig | None = None,
    credentials: RecipientCredentials | None = None,
    expected_recipient: str | None = None,
) -> DeliveryMailboxReaderResolution:
    """Resolve the R3 delivery reader — always live_eval_recipient_env."""
    config = config or get_live_eval_config()
    recipient = (expected_recipient or "").strip().lower()
    if not recipient:
        recipients = sorted(config.recipient_emails)
        recipient = recipients[0] if recipients else ""
    blockers: list[str] = []
    try:
        credentials = credentials or load_recipient_credentials()
        client = build_recipient_client(credentials)
        reader = GoogleMailClientDeliveryReader(client)
        profile_email = client.get_profile_email().strip().lower()
        mailbox_identity_redacted = _redact_email(profile_email)
        if recipient and profile_email != recipient:
            blockers.append("recipient Gmail profile email does not match allowlist")
        return DeliveryMailboxReaderResolution(
            reader=reader,
            credential_source=CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV,
            mailbox_identity_redacted=mailbox_identity_redacted,
            source_allowed=not blockers,
            source_matches_readiness=True,
            blockers=blockers,
        )
    except LiveEvalSafetyError as exc:
        blockers.append(str(exc))
    except Exception as exc:
        blockers.append(f"live eval recipient reader failed: {type(exc).__name__}")
    return DeliveryMailboxReaderResolution(
        credential_source=CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV,
        source_allowed=False,
        source_matches_readiness=True,
        blockers=blockers,
    )


def resolve_delivery_mailbox_reader(
    *,
    db: Session,
    row: LiveEvalRunRow,
    config: LiveEvalConfig | None = None,
    credentials: RecipientCredentials | None = None,
) -> DeliveryMailboxReaderResolution:
    """Resolve the mailbox reader used for delivery observation on a run."""
    config = config or get_live_eval_config()
    if is_r3_frozen_live_eval_run(row):
        resolution = resolve_r3_recipient_delivery_reader(
            config=config,
            credentials=credentials,
            expected_recipient=row.expected_recipient,
        )
        if resolution.credential_source != CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV:
            resolution.blockers.append("R3 run requires live_eval_recipient_env credential source")
            resolution.source_allowed = False
        return resolution

    blockers: list[str] = []
    try:
        connection_config = get_integration_connection_config(
            tenant_id=row.tenant_id,
            integration_type=IntegrationType.GOOGLE_MAIL,
            db=db,
        )
        adapter = get_integration_adapter(
            integration_type=IntegrationType.GOOGLE_MAIL,
            connection_config=connection_config,
        )
        reader = TenantIntegrationDeliveryReader(adapter)
        profile_email = reader.get_profile_email().strip().lower()
        expected = (row.expected_recipient or "").strip().lower()
        mailbox_identity_redacted = _redact_email(profile_email)
        if expected and profile_email != expected:
            blockers.append("tenant integration mailbox identity does not match expected recipient")
        return DeliveryMailboxReaderResolution(
            reader=reader,
            credential_source=CREDENTIAL_SOURCE_TENANT_GOOGLE_MAIL,
            mailbox_identity_redacted=mailbox_identity_redacted,
            source_allowed=not blockers,
            source_matches_readiness=True,
            blockers=blockers,
        )
    except Exception as exc:
        blockers.append(f"tenant integration reader failed: {type(exc).__name__}")
    return DeliveryMailboxReaderResolution(
        credential_source=CREDENTIAL_SOURCE_TENANT_GOOGLE_MAIL,
        source_allowed=False,
        source_matches_readiness=True,
        blockers=blockers,
    )


def resolve_intake_label_id_from_reader(
    reader: DeliveryMailboxReader,
    label_name: str,
) -> str | None:
    labels = reader.list_labels()
    for item in labels:
        if item.get("name") == label_name:
            label_id = item.get("id")
            return str(label_id) if label_id else None
    return None


def probe_delivery_reader_read_only(
    reader: DeliveryMailboxReader,
    *,
    config: LiveEvalConfig | None = None,
) -> tuple[bool, list[str]]:
    """Verify list_labels and a read-only mailbox query on the actual delivery reader."""
    config = config or get_live_eval_config()
    blockers: list[str] = []
    try:
        labels = reader.list_labels()
        if not isinstance(labels, list):
            blockers.append("delivery reader list_labels returned unexpected payload")
    except Exception as exc:
        blockers.append(f"delivery reader list_labels failed: {type(exc).__name__}")
        return False, blockers

    intake_label = (config.intake_label or "").strip()
    query = f"label:{intake_label} is:unread" if intake_label else "in:inbox"
    try:
        page = reader.list_messages_page(max_results=1, query=query)
        if page.message_ids is None:
            blockers.append("delivery reader read query returned invalid payload")
    except Exception as exc:
        blockers.append(f"delivery reader read query failed: {type(exc).__name__}")
    return not blockers, blockers


@dataclass
class OrphanDeliveryProbeResult:
    classification: str
    verified: bool
    credential_source: str | None = None
    evaluation_run_id: str | None = None
    scenario_id: str | None = None
    candidate_found: bool = False
    duplicate_detected: bool = False
    scenario_id_match: bool = False
    sender_match: bool = False
    recipient_match: bool = False
    subject_token_match: bool = False
    sender_message_id_redacted: str | None = None
    recipient_message_id_redacted: str | None = None
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "verified": self.verified,
            "credential_source": self.credential_source,
            "evaluation_run_id": self.evaluation_run_id,
            "scenario_id": self.scenario_id,
            "candidate_found": self.candidate_found,
            "duplicate_detected": self.duplicate_detected,
            "scenario_id_match": self.scenario_id_match,
            "sender_match": self.sender_match,
            "recipient_match": self.recipient_match,
            "subject_token_match": self.subject_token_match,
            "sender_message_id_redacted": self.sender_message_id_redacted,
            "recipient_message_id_redacted": self.recipient_message_id_redacted,
            "blockers": list(self.blockers),
        }


def _redact_provider_id(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return f"{value[:2]}…"
    return f"{value[:4]}…{value[-4:]}"


def probe_orphan_delivery_observation(
    db: Session,
    *,
    row: LiveEvalRunRow,
    classification: str = "orphaned_attempt_3_delivery_probe_verified",
    config: LiveEvalConfig | None = None,
) -> OrphanDeliveryProbeResult:
    """Read-only delivery observation probe for an existing orphan trigger run."""
    from app.evaluation.live.delivery import observe_delivery_candidates

    config = config or get_live_eval_config()
    result = OrphanDeliveryProbeResult(
        classification=classification,
        verified=False,
        evaluation_run_id=row.evaluation_run_id,
        scenario_id=row.scenario_id,
    )
    resolution = resolve_delivery_mailbox_reader(db=db, row=row, config=config)
    result.credential_source = resolution.credential_source
    if resolution.credential_source != CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV:
        result.blockers.append("orphan probe requires live_eval_recipient_env")
        return result
    if not resolution.ready:
        result.blockers.extend(resolution.blockers)
        return result

    probe_ok, probe_blockers = probe_delivery_reader_read_only(
        resolution.reader,  # type: ignore[arg-type]
        config=config,
    )
    if not probe_ok:
        result.blockers.extend(probe_blockers)
        return result

    try:
        observation = observe_delivery_candidates(
            db,
            row,
            config=config,
            reader_resolution=resolution,
        )
    except Exception as exc:
        result.blockers.append(f"orphan delivery observation failed: {type(exc).__name__}")
        return result

    result.duplicate_detected = observation.duplicate_detected
    confirmed = observation.confirmed
    result.candidate_found = confirmed is not None
    if confirmed is None:
        if observation.rejection_reasons:
            result.blockers.extend(observation.rejection_reasons)
        else:
            result.blockers.append("no delivery candidate confirmed for orphan run")
        return result

    result.sender_message_id_redacted = _redact_provider_id(confirmed.message_id)
    result.recipient_message_id_redacted = _redact_provider_id(confirmed.message_id)
    # observe_delivery_candidates already validated subject/scenario tokens.
    result.scenario_id_match = True
    result.subject_token_match = True
    result.sender_match = (
        confirmed.sender_email.strip().lower()
        == (row.expected_sender or "").strip().lower()
    )
    result.recipient_match = (
        confirmed.recipient_email.strip().lower()
        == (row.expected_recipient or "").strip().lower()
    )
    result.verified = (
        result.candidate_found
        and not result.duplicate_detected
        and result.scenario_id_match
        and result.subject_token_match
        and result.sender_match
        and result.recipient_match
        and not result.blockers
    )
    return result
