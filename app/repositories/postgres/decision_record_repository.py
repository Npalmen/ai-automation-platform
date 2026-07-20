"""Append-only persistence for decision_records."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.repositories.postgres.decision_record_models import DecisionRecordRow


class DecisionRecordRepository:
    @staticmethod
    def append_if_absent(db: Session, record: dict[str, Any]) -> DecisionRecordRow:
        row = DecisionRecordRow(
            decision_id=record["decision_id"],
            tenant_id=record["tenant_id"],
            job_id=record["job_id"],
            pipeline_run_id=record["pipeline_run_id"],
            parent_pipeline_run_id=record.get("parent_pipeline_run_id"),
            stage_sequence=record["stage_sequence"],
            record_type=record["record_type"],
            source=record["source"],
            processor_name=record.get("processor_name"),
            recommendation=record.get("recommendation"),
            policy_authorization=record.get("policy_authorization"),
            policy_decision=record.get("policy_decision"),
            action_type=record.get("action_type"),
            action_operation_id=record.get("action_operation_id"),
            action_fingerprint=record.get("action_fingerprint"),
            fingerprint_key_version=record.get("fingerprint_key_version"),
            action_authorization=record.get("action_authorization"),
            execution_phase=record.get("execution_phase"),
            execution_status=record.get("execution_status"),
            confidence=record.get("confidence"),
            reason_codes=record.get("reason_codes") or [],
            tenant_config_version=record.get("tenant_config_version"),
            code_version=record["code_version"],
            service_profile_type=record.get("service_profile_type"),
            prompt_name=record.get("prompt_name"),
            prompt_version=record.get("prompt_version"),
            prompt_hash=record.get("prompt_hash"),
            model_provider=record.get("model_provider"),
            model_name=record.get("model_name"),
            idempotency_key=record["idempotency_key"],
            supersedes_decision_id=record.get("supersedes_decision_id"),
            job_status_at_record=record["job_status_at_record"],
            metadata_json=record.get("metadata") or {},
            created_at=record.get("created_at") or datetime.now(timezone.utc),
        )
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
            return row
        except IntegrityError:
            existing = DecisionRecordRepository.get_by_idempotency_key(
                db,
                tenant_id=record["tenant_id"],
                idempotency_key=record["idempotency_key"],
            )
            if existing is None:
                raise
            return existing

    @staticmethod
    def get_by_idempotency_key(
        db: Session,
        *,
        tenant_id: str,
        idempotency_key: str,
    ) -> DecisionRecordRow | None:
        stmt = select(DecisionRecordRow).where(
            DecisionRecordRow.tenant_id == tenant_id,
            DecisionRecordRow.idempotency_key == idempotency_key,
        )
        return db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def list_for_job(
        db: Session,
        *,
        tenant_id: str,
        job_id: str,
    ) -> list[DecisionRecordRow]:
        stmt = (
            select(DecisionRecordRow)
            .where(
                DecisionRecordRow.tenant_id == tenant_id,
                DecisionRecordRow.job_id == job_id,
            )
            .order_by(DecisionRecordRow.event_sequence.asc())
        )
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def list_for_operation(
        db: Session,
        *,
        tenant_id: str,
        action_operation_id: str,
    ) -> list[DecisionRecordRow]:
        stmt = (
            select(DecisionRecordRow)
            .where(
                DecisionRecordRow.tenant_id == tenant_id,
                DecisionRecordRow.action_operation_id == action_operation_id,
            )
            .order_by(DecisionRecordRow.event_sequence.asc())
        )
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def latest_operation_state(
        db: Session,
        *,
        tenant_id: str,
        action_operation_id: str,
    ) -> str | None:
        rows = DecisionRecordRepository.list_for_operation(
            db,
            tenant_id=tenant_id,
            action_operation_id=action_operation_id,
        )
        for row in reversed(rows):
            if row.record_type in ("execution_intent", "execution_outcome"):
                return row.execution_status
        return None

    @staticmethod
    def new_decision_id() -> str:
        return str(uuid.uuid4())
