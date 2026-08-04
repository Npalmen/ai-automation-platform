"""Fail-closed R3 frozen live-canary mutation contract (registration parity)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.evaluation.live.config import LiveEvalConfig, get_live_eval_config
from app.evaluation.live.constants import (
    RUN_STATUS_ACTIVE,
    RUN_STATUS_REGISTERED,
    TERMINAL_RUN_STATUSES,
    TELEMETRY_APP_DELIVERY_OBSERVED,
)
from app.evaluation.live.delivery import observe_delivery_candidates, validate_delivery_candidate
from app.evaluation.live.delivery_mailbox_reader import (
    CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV,
    DeliveryMailboxReader,
    DeliveryMailboxReaderResolution,
    is_r3_frozen_live_eval_run,
    resolve_delivery_mailbox_reader,
    resolve_intake_label_id_from_reader,
)
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.tenant_intake_readiness import run_r3_tenant_intake_readiness
from app.evaluation.live.pipeline_runtime import resolve_api_build_git_sha
from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.evaluation.profile_testbot.qualification.coworker_live_canary_manifest import (
    COWORKER_LIVE_CANARY_MANIFEST_HASH,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_registration_contract import (
    R3_FROZEN_AI_MODE,
    R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE,
    R3_ALL_SCENARIO_IDS,
    recipient_matches_r3_approval,
    validate_r3_registration_contract,
    R3RegistrationContractRequest,
)
from app.repositories.postgres.live_eval_models import LiveEvalExternalEventRow, LiveEvalRunRow

R3_MUTATION_PROCESS_DELIVERY = "process_delivery_exact_message"
R3_MUTATION_CLAIM_ROOT_JOB = "claim_root_job"
R3_MUTATION_BIND_FROZEN_BODY = "bind_frozen_approval_body"
R3_MUTATION_APPROVE_FROZEN_REPLY = "approve_frozen_reply"
R3_MUTATION_OBSERVE_APPROVED_REPLY = "observe_approved_reply"

R3_FROZEN_MUTATION_OPERATIONS: frozenset[str] = frozenset(
    {
        R3_MUTATION_PROCESS_DELIVERY,
        R3_MUTATION_CLAIM_ROOT_JOB,
        R3_MUTATION_BIND_FROZEN_BODY,
        R3_MUTATION_APPROVE_FROZEN_REPLY,
        R3_MUTATION_OBSERVE_APPROVED_REPLY,
    }
)

# Orphan attempt evaluation_run_ids — must not be reused for new campaign mutations.
R3_ORPHAN_ATTEMPT_EVALUATION_RUN_IDS: frozenset[str] = frozenset(
    {
        "0a307286-41d7-4b98-8d8b-32b120618210",  # attempt 2
        "05839824-1fb1-4e98-b8e1-b8025df5db3d",  # attempt 3
        "ccd9916f-c4b7-4b1c-aabc-fb2da09f89cf",  # attempt 4
        "b5bbe7ab-7148-4366-8fba-bd92921481f4",  # attempt 5
        "afaf7ec3-69d7-433a-9ba7-8338a0a508c0",  # attempt 6
    }
)

ORPHANED_ATTEMPT_6_EVALUATION_RUN_ID = "afaf7ec3-69d7-433a-9ba7-8338a0a508c0"

# Redacted provider message IDs from prior orphan inbound triggers (attempts 2–4).
R3_ORPHAN_RECIPIENT_MESSAGE_ID_SUFFIXES: frozenset[str] = frozenset(
    {
        "2713",  # attempt 2
        "be91",  # attempt 3 sender (recipient unknown at registration)
        "cdb3",  # attempt 4
    }
)


@dataclass
class R3ProcessDeliveryReadinessResult:
    mutation_contract_valid: bool = False
    process_delivery_operation_allowed: bool = False
    intake_credential_source: str | None = None
    intake_credential_source_match: bool = False
    exact_message_read_ready: bool = False
    recipient_message_binding_valid: bool = False
    process_delivery_path_ready: bool = False
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mutation_contract_valid": self.mutation_contract_valid,
            "process_delivery_operation_allowed": self.process_delivery_operation_allowed,
            "intake_credential_source": self.intake_credential_source,
            "intake_credential_source_match": self.intake_credential_source_match,
            "exact_message_read_ready": self.exact_message_read_ready,
            "recipient_message_binding_valid": self.recipient_message_binding_valid,
            "process_delivery_path_ready": self.process_delivery_path_ready,
            "blockers": list(self.blockers),
        }


def _run_expired(row: LiveEvalRunRow) -> bool:
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at < datetime.now(timezone.utc)


def _runtime_sha_allowed() -> bool:
    sha = resolve_api_build_git_sha()
    if not sha:
        return False
    return len(sha) == 40


def _recipient_message_id_reused_from_orphan_attempt(
    *,
    evaluation_run_id: str,
    recipient_message_id: str | None,
) -> bool:
    if evaluation_run_id in R3_ORPHAN_ATTEMPT_EVALUATION_RUN_IDS:
        return False
    if not recipient_message_id:
        return False
    suffix = recipient_message_id[-4:]
    return suffix in R3_ORPHAN_RECIPIENT_MESSAGE_ID_SUFFIXES


def _delivery_event_matches(
    db: Session,
    *,
    row: LiveEvalRunRow,
    recipient_message_id: str,
) -> bool:
    events = (
        db.query(LiveEvalExternalEventRow)
        .filter(
            LiveEvalExternalEventRow.evaluation_run_id == row.evaluation_run_id,
            LiveEvalExternalEventRow.tenant_id == row.tenant_id,
            LiveEvalExternalEventRow.category == TELEMETRY_APP_DELIVERY_OBSERVED,
        )
        .all()
    )
    for event in events:
        if event.operation == recipient_message_id:
            return True
        metadata = event.redacted_metadata or {}
        if metadata.get("recipient_gmail_message_id") == recipient_message_id:
            return True
    return False


def resolve_verified_delivery_message_id(
    db: Session,
    *,
    row: LiveEvalRunRow,
    config: LiveEvalConfig | None = None,
    reader_resolution: DeliveryMailboxReaderResolution | None = None,
) -> str | None:
    config = config or get_live_eval_config()
    resolution = reader_resolution or resolve_delivery_mailbox_reader(
        db=db, row=row, config=config
    )
    if not resolution.ready:
        return None
    try:
        observation = observe_delivery_candidates(
            db,
            row,
            config=config,
            reader_resolution=resolution,
        )
    except Exception:
        return None
    confirmed = observation.confirmed
    return confirmed.message_id if confirmed else None


def validate_r3_frozen_live_run_contract(
    row: LiveEvalRunRow,
    *,
    tenant_id: str,
    operation: str | None,
    recipient_message_id: str | None = None,
    db: Session | None = None,
    campaign_type: str | None = R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE,
    manifest_hash: str | None = COWORKER_LIVE_CANARY_MANIFEST_HASH,
    allow_orphan_probe: bool = False,
) -> None:
    """Shared R3 frozen live-canary contract for registration, mutation, and intake gates."""
    if not is_r3_frozen_live_eval_run(row):
        raise LiveEvalSafetyError("not an R3 frozen live eval run")

    registration = validate_r3_registration_contract(
        R3RegistrationContractRequest(
            tenant_id=tenant_id,
            scenario_id=row.scenario_id,
            transport_mode=row.transport_mode,
            ai_mode=row.ai_mode,
            campaign_type=campaign_type,
            execution_mode=R3_FROZEN_AI_MODE,
            expected_sender=row.expected_sender,
            expected_recipient=row.expected_recipient,
            manifest_hash=manifest_hash,
            require_runtime_sha=False,
        )
    )
    if not registration.registration_contract_valid:
        raise LiveEvalSafetyError("; ".join(registration.registration_blockers))

    if row.tenant_id != LIVE_EVAL_TENANT_ID or tenant_id != LIVE_EVAL_TENANT_ID:
        raise LiveEvalSafetyError("R3 frozen run requires TENANT_LIVE_EVAL")

    if row.scenario_id not in R3_ALL_SCENARIO_IDS:
        raise LiveEvalSafetyError(f"scenario {row.scenario_id!r} not in R3 registry")

    if manifest_hash and manifest_hash != COWORKER_LIVE_CANARY_MANIFEST_HASH:
        raise LiveEvalSafetyError("manifest hash mismatch")

    if row.expected_recipient and not recipient_matches_r3_approval(row.expected_recipient):
        raise LiveEvalSafetyError("expected recipient does not match R3 approval allowlist")

    config = get_live_eval_config()
    sender = (row.expected_sender or "").strip().lower()
    recipient = (row.expected_recipient or "").strip().lower()
    if sender and sender not in config.sender_emails:
        raise LiveEvalSafetyError("expected_sender is not allowlisted")
    if recipient and recipient not in config.recipient_emails:
        raise LiveEvalSafetyError("expected_recipient is not allowlisted")

    if not _runtime_sha_allowed():
        raise LiveEvalSafetyError("runtime/runner SHA missing or invalid for R3 mutation")

    if _run_expired(row):
        raise LiveEvalSafetyError("run has expired")

    if operation is None:
        return

    if operation not in R3_FROZEN_MUTATION_OPERATIONS:
        raise LiveEvalSafetyError(f"unknown R3 mutation operation: {operation!r}")

    if row.status in TERMINAL_RUN_STATUSES:
        raise LiveEvalSafetyError(f"run status is terminal: {row.status}")

    if operation == R3_MUTATION_PROCESS_DELIVERY:
        if row.status not in {RUN_STATUS_REGISTERED, RUN_STATUS_ACTIVE}:
            raise LiveEvalSafetyError(
                f"run status {row.status!r} does not allow process_delivery"
            )
        if not recipient_message_id:
            raise LiveEvalSafetyError("process_delivery requires recipient_message_id")
        if _recipient_message_id_reused_from_orphan_attempt(
            evaluation_run_id=row.evaluation_run_id,
            recipient_message_id=recipient_message_id,
        ):
            raise LiveEvalSafetyError(
                "recipient_message_id matches prior orphan attempt — reuse blocked"
            )
        if db is not None and not allow_orphan_probe:
            if not _delivery_event_matches(
                db,
                row=row,
                recipient_message_id=recipient_message_id,
            ):
                verified_id = resolve_verified_delivery_message_id(db, row=row)
                if not verified_id or verified_id != recipient_message_id:
                    raise LiveEvalSafetyError(
                        "recipient_message_id does not match verified delivery candidate"
                    )
        return

    if row.status == RUN_STATUS_REGISTERED:
        if operation == R3_MUTATION_CLAIM_ROOT_JOB:
            return
        raise LiveEvalSafetyError(
            f"run status registered does not allow mutation {operation!r}"
        )

    if row.status == RUN_STATUS_ACTIVE:
        if not row.root_gmail_message_id or not row.root_job_id:
            raise LiveEvalSafetyError("active run missing root binding")
        if recipient_message_id and recipient_message_id != row.root_gmail_message_id:
            raise LiveEvalSafetyError("recipient message id does not match registry root")
        return

    raise LiveEvalSafetyError(f"run status {row.status!r} does not allow mutation")


def validate_r3_process_delivery_readiness(
    db: Session,
    *,
    row: LiveEvalRunRow,
    tenant_id: str,
    recipient_message_id: str | None = None,
    config: LiveEvalConfig | None = None,
    probe_exact_message: bool = False,
    allow_orphan_probe: bool = False,
) -> R3ProcessDeliveryReadinessResult:
    """Write-free process-delivery readiness for R3 frozen runs."""
    config = config or get_live_eval_config()
    result = R3ProcessDeliveryReadinessResult()

    tenant_intake = run_r3_tenant_intake_readiness(db, tenant_id=tenant_id)
    if not tenant_intake.tenant_intake_ready:
        result.blockers.extend(tenant_intake.blockers)
        return result

    try:
        validate_r3_frozen_live_run_contract(
            row,
            tenant_id=tenant_id,
            operation=None,
        )
        result.mutation_contract_valid = True
        result.process_delivery_operation_allowed = True
        if recipient_message_id:
            validate_r3_frozen_live_run_contract(
                row,
                tenant_id=tenant_id,
                operation=R3_MUTATION_PROCESS_DELIVERY,
                recipient_message_id=recipient_message_id,
                db=db,
                allow_orphan_probe=allow_orphan_probe,
            )
    except LiveEvalSafetyError as exc:
        result.blockers.append(str(exc))
        return result

    resolution = resolve_delivery_mailbox_reader(db=db, row=row, config=config)
    result.intake_credential_source = resolution.credential_source
    result.intake_credential_source_match = (
        resolution.credential_source == CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV
        and resolution.source_matches_readiness
    )
    if resolution.credential_source != CREDENTIAL_SOURCE_LIVE_EVAL_RECIPIENT_ENV:
        result.blockers.append("R3 intake requires live_eval_recipient_env credential source")
    if not resolution.ready:
        result.blockers.extend(resolution.blockers)

    if recipient_message_id and db is not None:
        if allow_orphan_probe or _delivery_event_matches(
            db, row=row, recipient_message_id=recipient_message_id
        ):
            result.recipient_message_binding_valid = True
        else:
            verified_id = resolve_verified_delivery_message_id(
                db, row=row, config=config, reader_resolution=resolution
            )
            result.recipient_message_binding_valid = verified_id == recipient_message_id
            if not result.recipient_message_binding_valid:
                result.blockers.append("recipient_message_id binding invalid")

    if probe_exact_message and recipient_message_id and resolution.ready:
        try:
            msg = resolution.reader.get_message(recipient_message_id)  # type: ignore[union-attr]
            intake_label_id = resolve_intake_label_id_from_reader(
                resolution.reader,  # type: ignore[arg-type]
                config.intake_label,
            )
            ok, reason = validate_delivery_candidate(
                msg,
                row=row,
                config=config,
                intake_label_id=intake_label_id,
            )
            result.exact_message_read_ready = ok
            if not ok:
                result.blockers.append(f"exact message validation failed: {reason}")
        except Exception as exc:
            result.blockers.append(f"exact message read failed: {type(exc).__name__}")

    result.process_delivery_path_ready = (
        result.mutation_contract_valid
        and result.process_delivery_operation_allowed
        and result.intake_credential_source_match
        and result.exact_message_read_ready
        if probe_exact_message and recipient_message_id
        else result.mutation_contract_valid
        and result.process_delivery_operation_allowed
        and result.intake_credential_source_match
        and (not recipient_message_id or result.recipient_message_binding_valid)
        and resolution.ready
    )
    if result.blockers:
        result.process_delivery_path_ready = False
    return result


class ReaderMailboxAdapter:
    """Minimal adapter surface for intake paths backed by DeliveryMailboxReader."""

    def __init__(self, reader: DeliveryMailboxReader):
        self._reader = reader
        self.client = reader

    def execute_action(self, *, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "get_message":
            message_id = str(payload.get("message_id") or "")
            message = self._reader.get_message(message_id)
            return {"message": message}
        if action == "list_labels":
            return {"labels": self._reader.list_labels()}
        if action == "get_profile":
            return {"email_address": self._reader.get_profile_email()}
        if action == "mark_as_read":
            raise LiveEvalSafetyError("R3 intake path does not allow mark_as_read")
        raise LiveEvalSafetyError(f"unsupported mailbox action for R3 reader: {action!r}")
