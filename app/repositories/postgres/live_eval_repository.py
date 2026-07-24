"""Persistence for live_eval_runs and external telemetry events."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.evaluation.live.constants import (
    ALLOWED_RUN_TRANSITIONS,
    EVENT_OUTCOME_SUCCEEDED,
    RUN_STATUS_ACTIVE,
    RUN_STATUS_REGISTERED,
)
from app.repositories.postgres.live_eval_models import (
    LiveEvalExternalEventRow,
    LiveEvalLlmOperationRow,
    LiveEvalRunRow,
)


class LiveEvalRunConflictError(Exception):
    pass


class LiveEvalRunNotFoundError(Exception):
    pass


class LiveEvalRunRepository:
    @staticmethod
    def register_run(db: Session, row: LiveEvalRunRow) -> LiveEvalRunRow:
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError as exc:
            raise LiveEvalRunConflictError(
                "evaluation_run_id already exists"
            ) from exc
        return row

    @staticmethod
    def get_run(
        db: Session,
        evaluation_run_id: str,
        *,
        tenant_id: str | None = None,
    ) -> LiveEvalRunRow | None:
        row = db.get(LiveEvalRunRow, evaluation_run_id)
        if row is None:
            return None
        if tenant_id is not None and row.tenant_id != tenant_id:
            return None
        return row

    @staticmethod
    def transition_status(
        db: Session,
        evaluation_run_id: str,
        *,
        tenant_id: str,
        to_status: str,
    ) -> LiveEvalRunRow:
        row = LiveEvalRunRepository.get_run(db, evaluation_run_id, tenant_id=tenant_id)
        if row is None:
            raise LiveEvalRunNotFoundError(
                f"Run {evaluation_run_id} not found for tenant {tenant_id}"
            )
        allowed = ALLOWED_RUN_TRANSITIONS.get(row.status, frozenset())
        if to_status not in allowed:
            raise LiveEvalRunNotFoundError(
                f"Transition {row.status!r} -> {to_status!r} is not allowed"
            )

        stmt = (
            update(LiveEvalRunRow)
            .where(
                LiveEvalRunRow.evaluation_run_id == evaluation_run_id,
                LiveEvalRunRow.tenant_id == tenant_id,
                LiveEvalRunRow.status == row.status,
            )
            .values(status=to_status)
        )
        result = db.execute(stmt)
        if int(result.rowcount or 0) != 1:
            raise LiveEvalRunNotFoundError(
                f"Concurrent transition conflict for run {evaluation_run_id}"
            )
        db.flush()
        refreshed = LiveEvalRunRepository.get_run(
            db, evaluation_run_id, tenant_id=tenant_id
        )
        if refreshed is None:
            raise LiveEvalRunNotFoundError(
                f"Run {evaluation_run_id} missing after transition"
            )
        return refreshed

    @staticmethod
    def claim_root_job(
        db: Session,
        *,
        evaluation_run_id: str,
        tenant_id: str,
        root_gmail_message_id: str,
        root_job_id: str,
        now: datetime | None = None,
    ) -> LiveEvalRunRow:
        now = now or datetime.now(timezone.utc)
        row = LiveEvalRunRepository.get_run(db, evaluation_run_id, tenant_id=tenant_id)
        if row is None:
            raise LiveEvalRunNotFoundError(
                f"Run {evaluation_run_id} not found for tenant {tenant_id}"
            )

        if row.status == RUN_STATUS_ACTIVE:
            if (
                row.root_gmail_message_id == root_gmail_message_id
                and row.root_job_id == root_job_id
            ):
                return row
            raise LiveEvalRunConflictError(
                f"Run {evaluation_run_id} already claimed by another root job"
            )

        if row.status != RUN_STATUS_REGISTERED:
            raise LiveEvalRunNotFoundError(
                f"Run {evaluation_run_id} is not claimable from status {row.status!r}"
            )

        stmt = (
            update(LiveEvalRunRow)
            .where(
                LiveEvalRunRow.evaluation_run_id == evaluation_run_id,
                LiveEvalRunRow.tenant_id == tenant_id,
                LiveEvalRunRow.status == RUN_STATUS_REGISTERED,
                LiveEvalRunRow.root_gmail_message_id.is_(None),
                LiveEvalRunRow.expires_at > now,
            )
            .values(
                status=RUN_STATUS_ACTIVE,
                root_gmail_message_id=root_gmail_message_id,
                root_job_id=root_job_id,
                activated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        result = db.execute(stmt)
        if int(result.rowcount or 0) != 1:
            row = LiveEvalRunRepository.get_run(
                db, evaluation_run_id, tenant_id=tenant_id
            )
            if row is None:
                raise LiveEvalRunNotFoundError(
                    f"Run {evaluation_run_id} missing after claim race"
                )
            if (
                row.status == RUN_STATUS_ACTIVE
                and row.root_gmail_message_id == root_gmail_message_id
                and row.root_job_id == root_job_id
            ):
                return row
            raise LiveEvalRunConflictError(
                f"Run {evaluation_run_id} claim lost to concurrent root job"
            )

        db.flush()
        db.expire_all()
        claimed = LiveEvalRunRepository.get_run(
            db, evaluation_run_id, tenant_id=tenant_id
        )
        if claimed is None:
            raise LiveEvalRunNotFoundError(
                f"Run {evaluation_run_id} missing after successful claim"
            )
        return claimed

    @staticmethod
    def claim_fixture_root_job(
        db: Session,
        *,
        evaluation_run_id: str,
        tenant_id: str,
        root_job_id: str,
        now: datetime | None = None,
    ) -> LiveEvalRunRow:
        now = now or datetime.now(timezone.utc)
        row = LiveEvalRunRepository.get_run(db, evaluation_run_id, tenant_id=tenant_id)
        if row is None:
            raise LiveEvalRunNotFoundError(
                f"Run {evaluation_run_id} not found for tenant {tenant_id}"
            )

        if row.status == RUN_STATUS_ACTIVE:
            if row.root_job_id == root_job_id and row.root_gmail_message_id is None:
                return row
            raise LiveEvalRunConflictError(
                f"Run {evaluation_run_id} already claimed by another root job"
            )

        if row.status != RUN_STATUS_REGISTERED:
            raise LiveEvalRunNotFoundError(
                f"Run {evaluation_run_id} is not claimable from status {row.status!r}"
            )

        stmt = (
            update(LiveEvalRunRow)
            .where(
                LiveEvalRunRow.evaluation_run_id == evaluation_run_id,
                LiveEvalRunRow.tenant_id == tenant_id,
                LiveEvalRunRow.status == RUN_STATUS_REGISTERED,
                LiveEvalRunRow.root_job_id.is_(None),
                LiveEvalRunRow.expires_at > now,
            )
            .values(
                status=RUN_STATUS_ACTIVE,
                root_job_id=root_job_id,
                activated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        result = db.execute(stmt)
        if int(result.rowcount or 0) != 1:
            row = LiveEvalRunRepository.get_run(
                db, evaluation_run_id, tenant_id=tenant_id
            )
            if row is None:
                raise LiveEvalRunNotFoundError(
                    f"Run {evaluation_run_id} missing after fixture claim race"
                )
            if row.status == RUN_STATUS_ACTIVE and row.root_job_id == root_job_id:
                return row
            raise LiveEvalRunConflictError(
                f"Run {evaluation_run_id} fixture claim lost to concurrent root job"
            )

        db.flush()
        db.expire_all()
        claimed = LiveEvalRunRepository.get_run(
            db, evaluation_run_id, tenant_id=tenant_id
        )
        if claimed is None:
            raise LiveEvalRunNotFoundError(
                f"Run {evaluation_run_id} missing after successful fixture claim"
            )
        return claimed

    @staticmethod
    def expire_stale_runs(db: Session, *, now: datetime | None = None) -> int:
        now = now or datetime.now(timezone.utc)
        stmt = (
            update(LiveEvalRunRow)
            .where(
                LiveEvalRunRow.expires_at < now,
                LiveEvalRunRow.status.in_((RUN_STATUS_REGISTERED, RUN_STATUS_ACTIVE)),
            )
            .values(status="expired")
        )
        result = db.execute(stmt)
        return int(result.rowcount or 0)


class LiveEvalExternalEventRepository:
    @staticmethod
    def record_event(db: Session, event: LiveEvalExternalEventRow) -> bool:
        """Insert idempotently. Returns True if inserted, False if duplicate event_key."""
        try:
            with db.begin_nested():
                db.add(event)
                db.flush()
            return True
        except IntegrityError:
            return False

    @staticmethod
    def has_succeeded_operation(db: Session, operation_key: str) -> bool:
        stmt = select(LiveEvalExternalEventRow.event_key).where(
            LiveEvalExternalEventRow.operation_key == operation_key,
            LiveEvalExternalEventRow.outcome == EVENT_OUTCOME_SUCCEEDED,
        )
        return db.execute(stmt).first() is not None

    @staticmethod
    def list_for_run(
        db: Session,
        evaluation_run_id: str,
        *,
        tenant_id: str,
    ) -> list[LiveEvalExternalEventRow]:
        stmt = (
            select(LiveEvalExternalEventRow)
            .where(
                LiveEvalExternalEventRow.evaluation_run_id == evaluation_run_id,
                LiveEvalExternalEventRow.tenant_id == tenant_id,
            )
            .order_by(LiveEvalExternalEventRow.started_at.asc())
        )
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def count_failed_attempts(db: Session, operation_key: str) -> int:
        stmt = select(LiveEvalExternalEventRow).where(
            LiveEvalExternalEventRow.operation_key == operation_key,
            LiveEvalExternalEventRow.outcome == "failed",
        )
        return len(list(db.execute(stmt).scalars().all()))

    @staticmethod
    def event_exists(db: Session, event_key: str) -> bool:
        stmt = select(LiveEvalExternalEventRow.event_key).where(
            LiveEvalExternalEventRow.event_key == event_key,
        )
        return db.execute(stmt).first() is not None

    @staticmethod
    def count_events_for_operation_key(db: Session, operation_key: str) -> int:
        stmt = select(LiveEvalExternalEventRow).where(
            LiveEvalExternalEventRow.operation_key == operation_key,
        )
        return len(list(db.execute(stmt).scalars().all()))

    @staticmethod
    def count_succeeded_for_run(
        db: Session,
        evaluation_run_id: str,
        *,
        category: str,
    ) -> int:
        stmt = select(LiveEvalExternalEventRow).where(
            LiveEvalExternalEventRow.evaluation_run_id == evaluation_run_id,
            LiveEvalExternalEventRow.category == category,
            LiveEvalExternalEventRow.outcome == EVENT_OUTCOME_SUCCEEDED,
        )
        return len(list(db.execute(stmt).scalars().all()))

    @staticmethod
    def count_outcomes_for_run(
        db: Session,
        evaluation_run_id: str,
        *,
        category: str,
        outcomes: frozenset[str],
    ) -> int:
        stmt = select(LiveEvalExternalEventRow).where(
            LiveEvalExternalEventRow.evaluation_run_id == evaluation_run_id,
            LiveEvalExternalEventRow.category == category,
            LiveEvalExternalEventRow.outcome.in_(tuple(outcomes)),
        )
        return len(list(db.execute(stmt).scalars().all()))

    @staticmethod
    def latest_outcome_for_operation_key(db: Session, operation_key: str) -> str | None:
        stmt = (
            select(LiveEvalExternalEventRow.outcome)
            .where(LiveEvalExternalEventRow.operation_key == operation_key)
            .order_by(LiveEvalExternalEventRow.started_at.desc())
        )
        row = db.execute(stmt).first()
        return row[0] if row else None

    @staticmethod
    def has_outcome_for_run(
        db: Session,
        evaluation_run_id: str,
        *,
        outcome: str,
        category: str,
    ) -> bool:
        stmt = select(LiveEvalExternalEventRow.event_key).where(
            LiveEvalExternalEventRow.evaluation_run_id == evaluation_run_id,
            LiveEvalExternalEventRow.category == category,
            LiveEvalExternalEventRow.outcome == outcome,
        )
        return db.execute(stmt).first() is not None


class LiveEvalLlmOperationConflictError(Exception):
    pass


class LiveEvalLlmOperationNotFoundError(Exception):
    pass


_TERMINAL_LLM_OPERATION_STATUSES = frozenset(
    {"succeeded", "failed", "outcome_unknown"}
)


class LiveEvalLlmOperationRepository:
    @staticmethod
    def reserve_operation(db: Session, row: LiveEvalLlmOperationRow) -> LiveEvalLlmOperationRow:
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
        except IntegrityError as exc:
            raise LiveEvalLlmOperationConflictError(
                "LLM operation reservation conflict"
            ) from exc
        return row

    @staticmethod
    def get_by_operation_key(
        db: Session, operation_key: str
    ) -> LiveEvalLlmOperationRow | None:
        stmt = select(LiveEvalLlmOperationRow).where(
            LiveEvalLlmOperationRow.operation_key == operation_key
        )
        return db.execute(stmt).scalars().first()

    @staticmethod
    def get_by_run_and_prompt(
        db: Session,
        *,
        evaluation_run_id: str,
        prompt_name: str,
    ) -> LiveEvalLlmOperationRow | None:
        stmt = select(LiveEvalLlmOperationRow).where(
            LiveEvalLlmOperationRow.evaluation_run_id == evaluation_run_id,
            LiveEvalLlmOperationRow.prompt_name == prompt_name,
        )
        return db.execute(stmt).scalars().first()

    @staticmethod
    def list_for_run(db: Session, evaluation_run_id: str) -> list[LiveEvalLlmOperationRow]:
        stmt = (
            select(LiveEvalLlmOperationRow)
            .where(LiveEvalLlmOperationRow.evaluation_run_id == evaluation_run_id)
            .order_by(LiveEvalLlmOperationRow.request_ordinal.asc())
        )
        return list(db.execute(stmt).scalars().all())

    @staticmethod
    def count_by_status(db: Session, evaluation_run_id: str, *, status: str) -> int:
        stmt = select(LiveEvalLlmOperationRow).where(
            LiveEvalLlmOperationRow.evaluation_run_id == evaluation_run_id,
            LiveEvalLlmOperationRow.status == status,
        )
        return len(list(db.execute(stmt).scalars().all()))

    @staticmethod
    def has_status_for_run(db: Session, evaluation_run_id: str, *, status: str) -> bool:
        stmt = select(LiveEvalLlmOperationRow.id).where(
            LiveEvalLlmOperationRow.evaluation_run_id == evaluation_run_id,
            LiveEvalLlmOperationRow.status == status,
        )
        return db.execute(stmt).first() is not None

    @staticmethod
    def count_terminal_operations(db: Session, evaluation_run_id: str) -> int:
        stmt = select(LiveEvalLlmOperationRow).where(
            LiveEvalLlmOperationRow.evaluation_run_id == evaluation_run_id,
            LiveEvalLlmOperationRow.status.in_(tuple(_TERMINAL_LLM_OPERATION_STATUSES)),
        )
        return len(list(db.execute(stmt).scalars().all()))

    @staticmethod
    def transition_status(
        db: Session,
        *,
        operation_key: str,
        from_status: str,
        to_status: str,
        updates: dict | None = None,
    ) -> bool:
        values = {"status": to_status, "updated_at": datetime.now(timezone.utc)}
        if updates:
            values.update(updates)
        stmt = (
            update(LiveEvalLlmOperationRow)
            .where(
                LiveEvalLlmOperationRow.operation_key == operation_key,
                LiveEvalLlmOperationRow.status == from_status,
            )
            .values(**values)
        )
        result = db.execute(stmt)
        return int(result.rowcount or 0) == 1
