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
# Must match coworker_r4_registry.R4_EXECUTE_AI_MODE / live.constants.REVIEWED_LIVE_LLM_BODY.
_R4_REVIEWED_LIVE_AI_MODE = "reviewed_live_llm_body"


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


def is_r4_reviewed_live_eval_run(row: LiveEvalRunRow) -> bool:
    return (
        row.tenant_id == LIVE_EVAL_TENANT_ID
        and row.transport_mode == "live_gmail"
        and row.ai_mode == _R4_REVIEWED_LIVE_AI_MODE
        and getattr(row, "campaign_type", None) == "coworker_r4_live_quality_campaign"
        and getattr(row, "execution_mode", None) == "r4_reviewed_live_candidate"
    )


def is_reviewed_live_eval_run(row: LiveEvalRunRow) -> bool:
    """R3 frozen reviewed run or R4 reviewed-live run."""
    return is_r3_frozen_live_eval_run(row) or is_r4_reviewed_live_eval_run(row)


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
    if is_reviewed_live_eval_run(row):
        resolution = resolve_r3_recipient_delivery_reader(
            config=config,
            credentials=credentials,
            expected_recipient=row.expected_recipient,
        )
        if resolution.credential_source != CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV:
            label = "R4" if is_r4_reviewed_live_eval_run(row) else "R3"
            resolution.blockers.append(
                f"{label} run requires live_eval_recipient_env credential source"
            )
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


@dataclass
class OrphanIntakeProbeResult:
    classification: str
    verified: bool
    credential_source: str | None = None
    evaluation_run_id: str | None = None
    scenario_id: str | None = None
    mutation_contract_valid: bool = False
    process_delivery_operation_allowed: bool = False
    intake_credential_source: str | None = None
    intake_credential_source_match: bool = False
    exact_message_read_ready: bool = False
    recipient_message_binding_valid: bool = False
    process_delivery_path_ready: bool = False
    classification_computed: bool = False
    sender_match: bool = False
    recipient_match: bool = False
    subject_token_match: bool = False
    body_marker_match: bool = False
    scenario_match: bool = False
    mailbox_identity_match: bool = False
    recipient_message_id_redacted: str | None = None
    job_created: bool = False
    run_status_changed: bool = False
    gmail_mutations_performed: bool = False
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "verified": self.verified,
            "credential_source": self.credential_source,
            "evaluation_run_id": self.evaluation_run_id,
            "scenario_id": self.scenario_id,
            "mutation_contract_valid": self.mutation_contract_valid,
            "process_delivery_operation_allowed": self.process_delivery_operation_allowed,
            "intake_credential_source": self.intake_credential_source,
            "intake_credential_source_match": self.intake_credential_source_match,
            "exact_message_read_ready": self.exact_message_read_ready,
            "recipient_message_binding_valid": self.recipient_message_binding_valid,
            "process_delivery_path_ready": self.process_delivery_path_ready,
            "classification_computed": self.classification_computed,
            "sender_match": self.sender_match,
            "recipient_match": self.recipient_match,
            "subject_token_match": self.subject_token_match,
            "body_marker_match": self.body_marker_match,
            "scenario_match": self.scenario_match,
            "mailbox_identity_match": self.mailbox_identity_match,
            "recipient_message_id_redacted": self.recipient_message_id_redacted,
            "job_created": self.job_created,
            "run_status_changed": self.run_status_changed,
            "gmail_mutations_performed": self.gmail_mutations_performed,
            "blockers": list(self.blockers),
        }


def probe_orphan_intake_observation(
    db: Session,
    *,
    row: LiveEvalRunRow,
    classification: str = "orphaned_attempt_4_intake_probe_verified",
    config: LiveEvalConfig | None = None,
) -> OrphanIntakeProbeResult:
    """Read-only exact-message intake probe — no job, no run mutation, no Gmail writes."""
    from email.utils import parseaddr

    from app.evaluation.live.subject_parser import parse_body_marker, parse_subject_token
    from app.evaluation.profile_testbot.qualification.coworker_r3_mutation_contract import (
        resolve_verified_delivery_message_id,
        validate_r3_process_delivery_readiness,
    )
    from app.workflows.processors.classification_processor import classify_email_type

    config = config or get_live_eval_config()
    initial_status = row.status
    result = OrphanIntakeProbeResult(
        classification=classification,
        verified=False,
        evaluation_run_id=row.evaluation_run_id,
        scenario_id=row.scenario_id,
    )

    verified_message_id = resolve_verified_delivery_message_id(db, row=row, config=config)
    if not verified_message_id:
        result.blockers.append("no verified delivery candidate for orphan intake probe")
        return result

    readiness = validate_r3_process_delivery_readiness(
        db,
        row=row,
        tenant_id=row.tenant_id,
        recipient_message_id=verified_message_id,
        config=config,
        probe_exact_message=True,
        allow_orphan_probe=True,
    )
    result.mutation_contract_valid = readiness.mutation_contract_valid
    result.process_delivery_operation_allowed = readiness.process_delivery_operation_allowed
    result.intake_credential_source = readiness.intake_credential_source
    result.intake_credential_source_match = readiness.intake_credential_source_match
    result.exact_message_read_ready = readiness.exact_message_read_ready
    result.recipient_message_binding_valid = readiness.recipient_message_binding_valid
    result.process_delivery_path_ready = readiness.process_delivery_path_ready
    result.credential_source = readiness.intake_credential_source
    result.recipient_message_id_redacted = _redact_provider_id(verified_message_id)
    if readiness.blockers:
        result.blockers.extend(readiness.blockers)

    resolution = resolve_delivery_mailbox_reader(db=db, row=row, config=config)
    if resolution.ready and resolution.reader is not None:
        try:
            profile_email = resolution.reader.get_profile_email().strip().lower()
            expected = (row.expected_recipient or "").strip().lower()
            result.mailbox_identity_match = not expected or profile_email == expected
            if not result.mailbox_identity_match:
                result.blockers.append("mailbox identity mismatch")
        except Exception as exc:
            result.blockers.append(f"mailbox identity probe failed: {type(exc).__name__}")

        try:
            msg = resolution.reader.get_message(verified_message_id)
            subject = str(msg.get("subject") or "")
            body_text = str(msg.get("body_text") or "")
            token = parse_subject_token(subject)
            result.subject_token_match = token is not None and token.evaluation_run_id == row.evaluation_run_id
            result.scenario_match = token is not None and token.scenario_id == row.scenario_id
            marker = parse_body_marker(body_text)
            result.body_marker_match = marker is not None
            sender_email = str(msg.get("from") or "")
            _, sender = parseaddr(sender_email)
            result.sender_match = sender.strip().lower() == (row.expected_sender or "").strip().lower()
            recipient = str(msg.get("to") or msg.get("delivered_to") or "")
            _, recipient_parsed = parseaddr(recipient)
            result.recipient_match = (
                recipient_parsed.strip().lower() == (row.expected_recipient or "").strip().lower()
            )
            try:
                classify_email_type(subject, body_text)
                result.classification_computed = True
            except Exception:
                result.blockers.append("classification could not be computed")
        except Exception as exc:
            result.blockers.append(f"intake message probe failed: {type(exc).__name__}")

    db.refresh(row)
    result.run_status_changed = row.status != initial_status
    if result.run_status_changed:
        result.blockers.append("run status changed during read-only probe")
    result.job_created = bool(row.root_job_id)
    if result.job_created:
        result.blockers.append("job exists on orphan run — probe must not create jobs")

    result.verified = (
        result.mutation_contract_valid
        and result.process_delivery_operation_allowed
        and result.intake_credential_source_match
        and result.exact_message_read_ready
        and result.recipient_message_binding_valid
        and result.process_delivery_path_ready
        and result.classification_computed
        and result.sender_match
        and result.recipient_match
        and result.subject_token_match
        and result.body_marker_match
        and result.scenario_match
        and result.mailbox_identity_match
        and not result.job_created
        and not result.run_status_changed
        and not result.gmail_mutations_performed
        and not result.blockers
    )
    return result
