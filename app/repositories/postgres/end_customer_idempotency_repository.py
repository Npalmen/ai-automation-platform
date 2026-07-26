"""Persistent idempotency for operator-controlled end-customer writes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.repositories.postgres.end_customer_idempotency_models import EndCustomerIdempotencyRecord


class EndCustomerIdempotencyConflictError(Exception):
    """Same idempotency key used with a different request hash."""


class EndCustomerIdempotencyInProgressError(Exception):
    """Another transaction is completing the same idempotency key."""


_IN_PROGRESS_STATUS = 0


@dataclass(frozen=True)
class EndCustomerIdempotencyReplay:
    response_status_code: int
    response_body: dict
    resource_reference: dict


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid4())


class EndCustomerIdempotencyRepository:
    @staticmethod
    def get_record(
        db: Session,
        tenant_id: str,
        operation_type: str,
        idempotency_key: str,
        *,
        for_update: bool = False,
    ) -> EndCustomerIdempotencyRecord | None:
        query = db.query(EndCustomerIdempotencyRecord).filter_by(
            tenant_id=tenant_id,
            operation_type=operation_type,
            idempotency_key=idempotency_key,
        )
        if for_update:
            query = query.with_for_update()
        return query.first()

    @staticmethod
    def acquire(
        db: Session,
        tenant_id: str,
        operation_type: str,
        idempotency_key: str,
        request_hash: str,
        *,
        record_id: str | None = None,
    ) -> EndCustomerIdempotencyReplay | str:
        """
        Return replay payload, or the claimed record_id for a new in-flight operation.

        Uses INSERT ON CONFLICT with row-level locking for concurrency-safe claim/replay.
        """
        existing = EndCustomerIdempotencyRepository.get_record(
            db,
            tenant_id,
            operation_type,
            idempotency_key,
            for_update=True,
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise EndCustomerIdempotencyConflictError(
                    "idempotency key reused with different request payload"
                )
            if existing.response_status_code != _IN_PROGRESS_STATUS:
                return EndCustomerIdempotencyReplay(
                    response_status_code=existing.response_status_code,
                    response_body=dict(existing.response_body or {}),
                    resource_reference=dict(existing.resource_reference or {}),
                )
            raise EndCustomerIdempotencyInProgressError(
                "idempotency operation already in progress"
            )

        claimed_id = record_id or _new_id()
        now = _utcnow()
        stmt = (
            insert(EndCustomerIdempotencyRecord)
            .values(
                record_id=claimed_id,
                tenant_id=tenant_id,
                operation_type=operation_type,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response_status_code=_IN_PROGRESS_STATUS,
                response_body={},
                resource_reference={},
                created_at=now,
                completed_at=now,
            )
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "operation_type", "idempotency_key"]
            )
            .returning(EndCustomerIdempotencyRecord.record_id)
        )
        inserted = db.execute(stmt).scalar_one_or_none()
        if inserted is not None:
            return inserted

        raced = EndCustomerIdempotencyRepository.get_record(
            db,
            tenant_id,
            operation_type,
            idempotency_key,
            for_update=True,
        )
        if raced is None:
            raise EndCustomerIdempotencyInProgressError("idempotency claim race unresolved")
        if raced.request_hash != request_hash:
            raise EndCustomerIdempotencyConflictError(
                "idempotency key reused with different request payload"
            )
        if raced.response_status_code != _IN_PROGRESS_STATUS:
            return EndCustomerIdempotencyReplay(
                response_status_code=raced.response_status_code,
                response_body=dict(raced.response_body or {}),
                resource_reference=dict(raced.resource_reference or {}),
            )
        raise EndCustomerIdempotencyInProgressError(
            "idempotency operation already in progress"
        )

    @staticmethod
    def complete(
        db: Session,
        record_id: str,
        response_status_code: int,
        response_body: dict,
        resource_reference: dict,
    ) -> None:
        record = db.get(EndCustomerIdempotencyRecord, record_id)
        if record is None:
            raise ValueError("idempotency record not found for completion")
        now = _utcnow()
        record.response_status_code = response_status_code
        record.response_body = dict(response_body)
        record.resource_reference = dict(resource_reference)
        record.completed_at = now
        db.flush()
