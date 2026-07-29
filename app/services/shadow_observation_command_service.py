"""Shadow observation command service — intake to shadow ledger."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.domain.customer.enums import SourceType
from app.domain.customer.normalization import normalize_email, normalize_phone
from app.domain.customer.shadow_enums import (
    ShadowFactProposalState,
    ShadowObservationState,
    ShadowSignalType,
    ShadowTrustLevel,
)
from app.domain.customer.shadow_state import assert_shadow_observation_transition
from app.repositories.postgres.end_customer_shadow_repository import (
    EndCustomerShadowRepository,
    ShadowDuplicateObservationError,
)
from app.services.shadow_gate import assert_shadow_intake_allowed

_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
_MIN_FACT_CONFIDENCE = 0.35


@dataclass
class ShadowIntakeEvent:
    tenant_id: str
    source_provider: str
    source_message_id: str
    source_thread_id: str | None
    source_event_id: str | None
    extraction_version: str
    observation_type: str
    sender_email: str | None
    sender_name: str | None
    sender_phone: str | None
    reply_to_email: str | None
    company_name: str | None
    organisation_number: str | None
    address: str | None
    message_text: str | None
    confidence: float
    model_name: str | None = None
    model_prompt_version: str | None = None
    campaign_run_id: str | None = None
    scenario_execution_id: str | None = None


def _hash_payload(payload: dict[str, Any]) -> str:
    normalized = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _redact(value: str | None, *, keep: int = 4) -> str:
    if not value:
        return ""
    cleaned = _CONTROL_CHAR_RE.sub("", value.strip())
    if len(cleaned) <= keep:
        return "*" * len(cleaned)
    return f"{cleaned[:keep]}…"


class ShadowObservationCommandService:
    @staticmethod
    def process_intake_event(db: Session, event: ShadowIntakeEvent) -> dict[str, Any]:
        assert_shadow_intake_allowed(event.tenant_id)

        raw_payload = {
            "sender_email": event.sender_email,
            "sender_name": event.sender_name,
            "sender_phone": event.sender_phone,
            "reply_to_email": event.reply_to_email,
            "company_name": event.company_name,
            "organisation_number": event.organisation_number,
            "address": event.address,
            "message_text_len": len(event.message_text or ""),
        }
        normalized_payload = {
            "email": normalize_email(event.sender_email) if event.sender_email else None,
            "phone": normalize_phone(event.sender_phone) if event.sender_phone else None,
            "reply_to": normalize_email(event.reply_to_email) if event.reply_to_email else None,
            "company_name": (event.company_name or "").strip().lower() or None,
            "thread_id": event.source_thread_id,
        }

        try:
            observation = EndCustomerShadowRepository.create_observation(
                db,
                tenant_id=event.tenant_id,
                source_provider=event.source_provider,
                source_message_id=event.source_message_id,
                source_thread_id=event.source_thread_id,
                source_event_id=event.source_event_id,
                extraction_version=event.extraction_version,
                observation_type=event.observation_type,
                state=ShadowObservationState.OBSERVED.value,
                raw_payload_hash=_hash_payload(raw_payload),
                normalized_payload_hash=_hash_payload(normalized_payload),
                confidence=event.confidence,
                model_name=event.model_name,
                model_prompt_version=event.model_prompt_version,
                campaign_run_id=event.campaign_run_id,
                scenario_execution_id=event.scenario_execution_id,
            )
            created = True
        except ShadowDuplicateObservationError:
            observation = EndCustomerShadowRepository.find_observation_by_idempotency(
                db,
                event.tenant_id,
                source_provider=event.source_provider,
                source_message_id=event.source_message_id,
                extraction_version=event.extraction_version,
                observation_type=event.observation_type,
            )
            if observation is None:
                raise
            created = False
            return {
                "observation_id": observation.observation_id,
                "state": observation.state,
                "created": False,
                "identity_signals": [],
                "fact_proposals": [],
            }

        assert_shadow_observation_transition(
            ShadowObservationState(observation.state),
            ShadowObservationState.NORMALIZED,
        )
        observation = EndCustomerShadowRepository.update_observation_state(
            db, event.tenant_id, observation.observation_id, ShadowObservationState.NORMALIZED.value
        )

        signals = ShadowObservationCommandService._persist_signals(db, event, observation.observation_id)
        fact_proposals = ShadowObservationCommandService._persist_fact_proposals(
            db, event, observation.observation_id
        )

        assert_shadow_observation_transition(
            ShadowObservationState.NORMALIZED,
            ShadowObservationState.EXTRACTED,
        )
        observation = EndCustomerShadowRepository.update_observation_state(
            db, event.tenant_id, observation.observation_id, ShadowObservationState.EXTRACTED.value
        )

        target_state = (
            ShadowObservationState.AWAITING_OPERATOR
            if event.confidence < _MIN_FACT_CONFIDENCE
            else ShadowObservationState.MATCH_ASSESSED
        )
        assert_shadow_observation_transition(
            ShadowObservationState.EXTRACTED,
            target_state,
        )
        observation = EndCustomerShadowRepository.update_observation_state(
            db, event.tenant_id, observation.observation_id, target_state.value
        )

        return {
            "observation_id": observation.observation_id,
            "state": observation.state,
            "created": created,
            "identity_signals": [s.signal_id for s in signals if s],
            "fact_proposals": [p.proposal_id for p in fact_proposals if p],
        }

    @staticmethod
    def _persist_signals(
        db: Session,
        event: ShadowIntakeEvent,
        observation_id: str,
    ) -> list[Any]:
        signals: list[Any] = []
        if event.sender_email:
            norm = normalize_email(event.sender_email)
            signals.append(
                EndCustomerShadowRepository.create_identity_signal(
                    db,
                    tenant_id=event.tenant_id,
                    observation_id=observation_id,
                    signal_type=ShadowSignalType.EMAIL.value,
                    raw_value_redacted=_redact(event.sender_email),
                    normalized_value=norm,
                    confidence=event.confidence,
                    source_path="sender.email",
                    trust_level=ShadowTrustLevel.PROPOSED.value,
                )
            )
        if event.sender_phone:
            norm = normalize_phone(event.sender_phone)
            signals.append(
                EndCustomerShadowRepository.create_identity_signal(
                    db,
                    tenant_id=event.tenant_id,
                    observation_id=observation_id,
                    signal_type=ShadowSignalType.PHONE.value,
                    raw_value_redacted=_redact(event.sender_phone),
                    normalized_value=norm,
                    confidence=event.confidence,
                    source_path="sender.phone",
                    trust_level=ShadowTrustLevel.PROPOSED.value,
                )
            )
        if event.sender_name:
            signals.append(
                EndCustomerShadowRepository.create_identity_signal(
                    db,
                    tenant_id=event.tenant_id,
                    observation_id=observation_id,
                    signal_type=ShadowSignalType.PERSON_NAME.value,
                    raw_value_redacted=_redact(event.sender_name),
                    normalized_value=event.sender_name.strip().lower(),
                    confidence=event.confidence,
                    source_path="sender.name",
                    trust_level=ShadowTrustLevel.UNTRUSTED.value,
                )
            )
        if event.company_name:
            signals.append(
                EndCustomerShadowRepository.create_identity_signal(
                    db,
                    tenant_id=event.tenant_id,
                    observation_id=observation_id,
                    signal_type=ShadowSignalType.COMPANY_NAME.value,
                    raw_value_redacted=_redact(event.company_name),
                    normalized_value=event.company_name.strip().lower(),
                    confidence=event.confidence,
                    source_path="entities.company_name",
                    trust_level=ShadowTrustLevel.PROPOSED.value,
                )
            )
        if event.source_thread_id:
            signals.append(
                EndCustomerShadowRepository.create_identity_signal(
                    db,
                    tenant_id=event.tenant_id,
                    observation_id=observation_id,
                    signal_type=ShadowSignalType.THREAD_ID.value,
                    raw_value_redacted=_redact(event.source_thread_id, keep=8),
                    normalized_value=event.source_thread_id,
                    confidence=1.0,
                    source_path="transport.thread_id",
                    trust_level=ShadowTrustLevel.OBSERVED.value,
                )
            )
        if event.reply_to_email and event.reply_to_email != event.sender_email:
            signals.append(
                EndCustomerShadowRepository.create_identity_signal(
                    db,
                    tenant_id=event.tenant_id,
                    observation_id=observation_id,
                    signal_type=ShadowSignalType.REPLY_TO.value,
                    raw_value_redacted=_redact(event.reply_to_email),
                    normalized_value=normalize_email(event.reply_to_email),
                    confidence=event.confidence,
                    source_path="sender.reply_to",
                    trust_level=ShadowTrustLevel.UNTRUSTED.value,
                )
            )
        return signals

    @staticmethod
    def _persist_fact_proposals(
        db: Session,
        event: ShadowIntakeEvent,
        observation_id: str,
    ) -> list[Any]:
        if event.confidence < _MIN_FACT_CONFIDENCE:
            return []
        proposals: list[Any] = []
        field_map = {
            "email": event.sender_email,
            "phone": event.sender_phone,
            "customer_name": event.sender_name,
            "company_name": event.company_name,
            "address": event.address,
        }
        for field_name, raw in field_map.items():
            if not raw:
                continue
            normalized = raw.strip().lower() if field_name in {"customer_name", "company_name", "address"} else raw
            if field_name == "email":
                normalized = normalize_email(raw) or raw
            if field_name == "phone":
                normalized = normalize_phone(raw) or raw
            proposals.append(
                EndCustomerShadowRepository.create_fact_proposal(
                    db,
                    tenant_id=event.tenant_id,
                    observation_id=observation_id,
                    field_name=field_name,
                    proposed_value=raw,
                    normalized_value=normalized,
                    confidence=event.confidence,
                    source_type=SourceType.AI_EXTRACTION.value,
                    state=ShadowFactProposalState.SHADOW.value,
                )
            )
        return proposals

    @staticmethod
    def advance_to_awaiting_operator(db: Session, tenant_id: str, observation_id: str) -> None:
        row = EndCustomerShadowRepository.get_observation(db, tenant_id, observation_id)
        if row is None:
            return
        current = ShadowObservationState(row.state)
        if current == ShadowObservationState.AWAITING_OPERATOR:
            return
        assert_shadow_observation_transition(current, ShadowObservationState.AWAITING_OPERATOR)
        EndCustomerShadowRepository.update_observation_state(
            db, tenant_id, observation_id, ShadowObservationState.AWAITING_OPERATOR.value
        )
