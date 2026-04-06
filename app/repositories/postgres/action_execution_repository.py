from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.repositories.postgres.action_execution_models import ActionExecutionRecord


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized)
        except ValueError:
            return None

    return None


class ActionExecutionRepository:
    @staticmethod
    def create_execution(
        db: Session,
        *,
        tenant_id: str,
        job_id: str,
        action_type: str,
        status: str,
        target: str | None,
        provider: str | None,
        request_payload: dict[str, Any],
        result_payload: dict[str, Any] | None = None,
        external_id: str | None = None,
        error_message: str | None = None,
        executed_at: datetime | None = None,
        attempt_no: int = 1,
    ) -> ActionExecutionRecord:
        now = _utcnow()

        record = ActionExecutionRecord(
            execution_id=str(uuid4()),
            tenant_id=tenant_id,
            job_id=job_id,
            action_type=action_type,
            status=status,
            target=target,
            provider=provider,
            external_id=external_id,
            attempt_no=attempt_no,
            request_payload=request_payload,
            result_payload=result_payload,
            error_message=error_message,
            executed_at=executed_at or now,
            created_at=now,
            updated_at=now,
        )

        db.add(record)
        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def list_for_job(
        db: Session,
        tenant_id: str,
        job_id: str,
    ) -> list[ActionExecutionRecord]:
        return (
            db.query(ActionExecutionRecord)
            .filter(
                ActionExecutionRecord.tenant_id == tenant_id,
                ActionExecutionRecord.job_id == job_id,
            )
            .order_by(ActionExecutionRecord.executed_at.asc(), ActionExecutionRecord.created_at.asc())
            .all()
        )

    @staticmethod
    def count_for_job(
        db: Session,
        tenant_id: str,
        job_id: str,
    ) -> int:
        return (
            db.query(ActionExecutionRecord)
            .filter(
                ActionExecutionRecord.tenant_id == tenant_id,
                ActionExecutionRecord.job_id == job_id,
            )
            .count()
        )

    @staticmethod
    def create_from_executed_action(
        db: Session,
        *,
        tenant_id: str,
        job_id: str,
        request_action: dict[str, Any],
        executed_action: dict[str, Any],
        attempt_no: int = 1,
    ) -> ActionExecutionRecord:
        integration_result = executed_action.get("integration_result") or {}
        executed_at = _parse_datetime(executed_action.get("executed_at")) or _utcnow()

        return ActionExecutionRepository.create_execution(
            db=db,
            tenant_id=tenant_id,
            job_id=job_id,
            action_type=str(executed_action.get("type") or request_action.get("type") or "unknown"),
            status=str(executed_action.get("status") or "executed"),
            target=executed_action.get("target"),
            provider=executed_action.get("provider"),
            request_payload=request_action,
            result_payload=executed_action,
            external_id=integration_result.get("external_id"),
            error_message=integration_result.get("error") or executed_action.get("error"),
            executed_at=executed_at,
            attempt_no=attempt_no,
        )

    @staticmethod
    def create_from_failed_action(
        db: Session,
        *,
        tenant_id: str,
        job_id: str,
        request_action: dict[str, Any],
        failure_payload: dict[str, Any],
        attempt_no: int = 1,
    ) -> ActionExecutionRecord:
        executed_at = _parse_datetime(failure_payload.get("executed_at")) or _utcnow()

        return ActionExecutionRepository.create_execution(
            db=db,
            tenant_id=tenant_id,
            job_id=job_id,
            action_type=str(failure_payload.get("type") or request_action.get("type") or "unknown"),
            status=str(failure_payload.get("status") or "failed"),
            target=failure_payload.get("target"),
            provider=failure_payload.get("provider"),
            request_payload=request_action,
            result_payload=failure_payload,
            external_id=None,
            error_message=failure_payload.get("error"),
            executed_at=executed_at,
            attempt_no=attempt_no,
        )

    @staticmethod
    def to_dict(record: ActionExecutionRecord) -> dict[str, Any]:
        return {
            "execution_id": record.execution_id,
            "tenant_id": record.tenant_id,
            "job_id": record.job_id,
            "action_type": record.action_type,
            "status": record.status,
            "target": record.target,
            "provider": record.provider,
            "external_id": record.external_id,
            "attempt_no": record.attempt_no,
            "request_payload": record.request_payload,
            "result_payload": record.result_payload,
            "error_message": record.error_message,
            "executed_at": record.executed_at.isoformat(),
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }