"""Tenant-scoped persistence for shadow observation ledger."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.repositories.postgres.end_customer_shadow_models import (
    EndCustomerShadowFactProposalRecord,
    EndCustomerShadowIdentitySignalRecord,
    EndCustomerShadowMatchProposalRecord,
    EndCustomerShadowObservationRecord,
)


class ShadowTenantScopeError(Exception):
    pass


class ShadowDuplicateObservationError(Exception):
    """Idempotent replay — observation already exists."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


class EndCustomerShadowRepository:
    @staticmethod
    def get_observation(
        db: Session,
        tenant_id: str,
        observation_id: str,
    ) -> EndCustomerShadowObservationRecord | None:
        row = (
            db.query(EndCustomerShadowObservationRecord)
            .filter(
                EndCustomerShadowObservationRecord.tenant_id == tenant_id,
                EndCustomerShadowObservationRecord.observation_id == observation_id,
            )
            .first()
        )
        return row

    @staticmethod
    def find_observation_by_idempotency(
        db: Session,
        tenant_id: str,
        *,
        source_provider: str,
        source_message_id: str,
        extraction_version: str,
        observation_type: str,
    ) -> EndCustomerShadowObservationRecord | None:
        return (
            db.query(EndCustomerShadowObservationRecord)
            .filter(
                EndCustomerShadowObservationRecord.tenant_id == tenant_id,
                EndCustomerShadowObservationRecord.source_provider == source_provider,
                EndCustomerShadowObservationRecord.source_message_id == source_message_id,
                EndCustomerShadowObservationRecord.extraction_version == extraction_version,
                EndCustomerShadowObservationRecord.observation_type == observation_type,
            )
            .first()
        )

    @staticmethod
    def create_observation(
        db: Session,
        *,
        tenant_id: str,
        source_provider: str,
        source_message_id: str,
        source_thread_id: str | None,
        source_event_id: str | None,
        extraction_version: str,
        observation_type: str,
        state: str,
        raw_payload_hash: str,
        normalized_payload_hash: str,
        confidence: float,
        model_name: str | None = None,
        model_prompt_version: str | None = None,
        campaign_run_id: str | None = None,
        scenario_execution_id: str | None = None,
    ) -> EndCustomerShadowObservationRecord:
        now = _utcnow()
        row = EndCustomerShadowObservationRecord(
            observation_id=_new_id(),
            tenant_id=tenant_id,
            campaign_run_id=campaign_run_id,
            scenario_execution_id=scenario_execution_id,
            source_provider=source_provider,
            source_message_id=source_message_id,
            source_thread_id=source_thread_id,
            source_event_id=source_event_id,
            extraction_version=extraction_version,
            observation_type=observation_type,
            state=state,
            raw_payload_hash=raw_payload_hash,
            normalized_payload_hash=normalized_payload_hash,
            confidence=confidence,
            model_name=model_name,
            model_prompt_version=model_prompt_version,
            cleanup_eligible=True,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            existing = EndCustomerShadowRepository.find_observation_by_idempotency(
                db,
                tenant_id,
                source_provider=source_provider,
                source_message_id=source_message_id,
                extraction_version=extraction_version,
                observation_type=observation_type,
            )
            if existing is not None:
                raise ShadowDuplicateObservationError("observation exists") from exc
            raise
        return row

    @staticmethod
    def update_observation_state(
        db: Session,
        tenant_id: str,
        observation_id: str,
        state: str,
    ) -> EndCustomerShadowObservationRecord:
        row = EndCustomerShadowRepository.get_observation(db, tenant_id, observation_id)
        if row is None:
            raise ShadowTenantScopeError("observation not found")
        row.state = state
        row.updated_at = _utcnow()
        db.flush()
        return row

    @staticmethod
    def create_identity_signal(
        db: Session,
        *,
        tenant_id: str,
        observation_id: str,
        signal_type: str,
        raw_value_redacted: str,
        normalized_value: str | None,
        confidence: float,
        source_path: str | None,
        trust_level: str,
    ) -> EndCustomerShadowIdentitySignalRecord | None:
        existing = (
            db.query(EndCustomerShadowIdentitySignalRecord)
            .filter(
                EndCustomerShadowIdentitySignalRecord.tenant_id == tenant_id,
                EndCustomerShadowIdentitySignalRecord.observation_id == observation_id,
                EndCustomerShadowIdentitySignalRecord.signal_type == signal_type,
                EndCustomerShadowIdentitySignalRecord.normalized_value == normalized_value,
            )
            .first()
        )
        if existing is not None:
            return existing
        row = EndCustomerShadowIdentitySignalRecord(
            signal_id=_new_id(),
            tenant_id=tenant_id,
            observation_id=observation_id,
            signal_type=signal_type,
            raw_value_redacted=raw_value_redacted,
            normalized_value=normalized_value,
            confidence=confidence,
            source_path=source_path,
            trust_level=trust_level,
            created_at=_utcnow(),
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return (
                db.query(EndCustomerShadowIdentitySignalRecord)
                .filter(
                    EndCustomerShadowIdentitySignalRecord.tenant_id == tenant_id,
                    EndCustomerShadowIdentitySignalRecord.observation_id == observation_id,
                    EndCustomerShadowIdentitySignalRecord.signal_type == signal_type,
                    EndCustomerShadowIdentitySignalRecord.normalized_value == normalized_value,
                )
                .first()
            )
        return row

    @staticmethod
    def create_fact_proposal(
        db: Session,
        *,
        tenant_id: str,
        observation_id: str,
        field_name: str,
        proposed_value: str | None,
        normalized_value: str | None,
        confidence: float,
        source_type: str,
        state: str,
        target_end_customer_id: str | None = None,
    ) -> EndCustomerShadowFactProposalRecord | None:
        existing = (
            db.query(EndCustomerShadowFactProposalRecord)
            .filter(
                EndCustomerShadowFactProposalRecord.tenant_id == tenant_id,
                EndCustomerShadowFactProposalRecord.observation_id == observation_id,
                EndCustomerShadowFactProposalRecord.field_name == field_name,
                EndCustomerShadowFactProposalRecord.normalized_value == normalized_value,
            )
            .first()
        )
        if existing is not None:
            return existing
        row = EndCustomerShadowFactProposalRecord(
            proposal_id=_new_id(),
            tenant_id=tenant_id,
            observation_id=observation_id,
            field_name=field_name,
            proposed_value=proposed_value,
            normalized_value=normalized_value,
            confidence=confidence,
            source_type=source_type,
            state=state,
            target_end_customer_id=target_end_customer_id,
            promotion_status="shadow",
            created_at=_utcnow(),
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return (
                db.query(EndCustomerShadowFactProposalRecord)
                .filter(
                    EndCustomerShadowFactProposalRecord.tenant_id == tenant_id,
                    EndCustomerShadowFactProposalRecord.observation_id == observation_id,
                    EndCustomerShadowFactProposalRecord.field_name == field_name,
                    EndCustomerShadowFactProposalRecord.normalized_value == normalized_value,
                )
                .first()
            )
        return row

    @staticmethod
    def create_match_proposal(
        db: Session,
        *,
        tenant_id: str,
        observation_id: str,
        candidate_end_customer_id: str,
        match_score: float,
        match_reasons: list[str],
        deterministic_signals: list[str],
        ambiguous_signals: list[str],
        matcher_version: str,
        state: str,
    ) -> EndCustomerShadowMatchProposalRecord | None:
        existing = (
            db.query(EndCustomerShadowMatchProposalRecord)
            .filter(
                EndCustomerShadowMatchProposalRecord.tenant_id == tenant_id,
                EndCustomerShadowMatchProposalRecord.observation_id == observation_id,
                EndCustomerShadowMatchProposalRecord.candidate_end_customer_id == candidate_end_customer_id,
                EndCustomerShadowMatchProposalRecord.matcher_version == matcher_version,
            )
            .first()
        )
        if existing is not None:
            return existing
        row = EndCustomerShadowMatchProposalRecord(
            match_proposal_id=_new_id(),
            tenant_id=tenant_id,
            observation_id=observation_id,
            candidate_end_customer_id=candidate_end_customer_id,
            match_score=match_score,
            match_reasons=match_reasons,
            deterministic_signals=deterministic_signals,
            ambiguous_signals=ambiguous_signals,
            matcher_version=matcher_version,
            state=state,
            created_at=_utcnow(),
        )
        db.add(row)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            return (
                db.query(EndCustomerShadowMatchProposalRecord)
                .filter(
                    EndCustomerShadowMatchProposalRecord.tenant_id == tenant_id,
                    EndCustomerShadowMatchProposalRecord.observation_id == observation_id,
                    EndCustomerShadowMatchProposalRecord.candidate_end_customer_id == candidate_end_customer_id,
                    EndCustomerShadowMatchProposalRecord.matcher_version == matcher_version,
                )
                .first()
            )
        return row

    @staticmethod
    def count_observations(db: Session, tenant_id: str) -> int:
        return int(
            db.execute(
                text("SELECT COUNT(*) FROM end_customer_shadow_observations WHERE tenant_id = :tenant_id"),
                {"tenant_id": tenant_id},
            ).scalar()
            or 0
        )

    @staticmethod
    def list_observations(db: Session, tenant_id: str) -> list[EndCustomerShadowObservationRecord]:
        return (
            db.query(EndCustomerShadowObservationRecord)
            .filter(EndCustomerShadowObservationRecord.tenant_id == tenant_id)
            .order_by(EndCustomerShadowObservationRecord.created_at)
            .all()
        )

    @staticmethod
    def list_signals(db: Session, tenant_id: str, observation_id: str) -> list[EndCustomerShadowIdentitySignalRecord]:
        return (
            db.query(EndCustomerShadowIdentitySignalRecord)
            .filter(
                EndCustomerShadowIdentitySignalRecord.tenant_id == tenant_id,
                EndCustomerShadowIdentitySignalRecord.observation_id == observation_id,
            )
            .all()
        )

    @staticmethod
    def list_fact_proposals(
        db: Session, tenant_id: str, observation_id: str | None = None
    ) -> list[EndCustomerShadowFactProposalRecord]:
        query = db.query(EndCustomerShadowFactProposalRecord).filter(
            EndCustomerShadowFactProposalRecord.tenant_id == tenant_id
        )
        if observation_id is not None:
            query = query.filter(EndCustomerShadowFactProposalRecord.observation_id == observation_id)
        return query.all()

    @staticmethod
    def list_match_proposals(
        db: Session, tenant_id: str, observation_id: str | None = None
    ) -> list[EndCustomerShadowMatchProposalRecord]:
        query = db.query(EndCustomerShadowMatchProposalRecord).filter(
            EndCustomerShadowMatchProposalRecord.tenant_id == tenant_id
        )
        if observation_id is not None:
            query = query.filter(EndCustomerShadowMatchProposalRecord.observation_id == observation_id)
        return query.all()

    @staticmethod
    def snapshot_counts(db: Session, tenant_id: str) -> dict[str, int]:
        tables = (
            "end_customer_shadow_observations",
            "end_customer_shadow_identity_signals",
            "end_customer_shadow_fact_proposals",
            "end_customer_shadow_match_proposals",
        )
        counts: dict[str, int] = {}
        for table in tables:
            counts[table] = int(
                db.execute(
                    text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id = :tenant_id"),
                    {"tenant_id": tenant_id},
                ).scalar()
                or 0
            )
        return counts

    @staticmethod
    def delete_tenant_shadow_data(db: Session, tenant_id: str) -> None:
        for table in (
            "end_customer_shadow_match_proposals",
            "end_customer_shadow_fact_proposals",
            "end_customer_shadow_identity_signals",
            "end_customer_shadow_observations",
        ):
            db.execute(
                text(f"DELETE FROM {table} WHERE tenant_id = :tenant_id"),
                {"tenant_id": tenant_id},
            )
