from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.repositories.postgres.approval_models import ApprovalRequestRecord


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


class ApprovalRequestRepository:
    @staticmethod
    def get_by_approval_id(
        db: Session,
        tenant_id: str,
        approval_id: str,
    ) -> ApprovalRequestRecord | None:
        return (
            db.query(ApprovalRequestRecord)
            .filter(
                ApprovalRequestRecord.tenant_id == tenant_id,
                ApprovalRequestRecord.approval_id == approval_id,
            )
            .first()
        )

    @staticmethod
    def get_latest_for_job(
        db: Session,
        tenant_id: str,
        job_id: str,
    ) -> ApprovalRequestRecord | None:
        return (
            db.query(ApprovalRequestRecord)
            .filter(
                ApprovalRequestRecord.tenant_id == tenant_id,
                ApprovalRequestRecord.job_id == job_id,
            )
            .order_by(ApprovalRequestRecord.created_at.desc())
            .first()
        )

    @staticmethod
    def list_for_job(
        db: Session,
        tenant_id: str,
        job_id: str,
    ) -> list[ApprovalRequestRecord]:
        return (
            db.query(ApprovalRequestRecord)
            .filter(
                ApprovalRequestRecord.tenant_id == tenant_id,
                ApprovalRequestRecord.job_id == job_id,
            )
            .order_by(ApprovalRequestRecord.created_at.desc())
            .all()
        )

    @staticmethod
    def list_pending_for_tenant(
        db: Session,
        tenant_id: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ApprovalRequestRecord]:
        return (
            db.query(ApprovalRequestRecord)
            .filter(
                ApprovalRequestRecord.tenant_id == tenant_id,
                ApprovalRequestRecord.state == "pending",
            )
            .order_by(ApprovalRequestRecord.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    @staticmethod
    def count_pending_for_tenant(
        db: Session,
        tenant_id: str,
    ) -> int:
        return (
            db.query(ApprovalRequestRecord)
            .filter(
                ApprovalRequestRecord.tenant_id == tenant_id,
                ApprovalRequestRecord.state == "pending",
            )
            .count()
        )

    @staticmethod
    def upsert_from_payload(
        db: Session,
        *,
        tenant_id: str,
        job_id: str,
        job_type: str | None,
        approval_request: dict[str, Any],
        delivery_payload: dict[str, Any] | None = None,
    ) -> ApprovalRequestRecord:
        approval_id = approval_request.get("approval_id")
        if not approval_id:
            raise ValueError("approval_request.approval_id is required.")

        record = ApprovalRequestRepository.get_by_approval_id(
            db=db,
            tenant_id=tenant_id,
            approval_id=approval_id,
        )

        now = _utcnow()

        if record is None:
            record = ApprovalRequestRecord(
                approval_id=str(approval_id),
                tenant_id=tenant_id,
                job_id=job_id,
                job_type=job_type,
                state=str(approval_request.get("state") or "pending"),
                channel=str(approval_request.get("channel") or "dashboard"),
                title=approval_request.get("title"),
                summary=approval_request.get("summary"),
                requested_by=approval_request.get("requested_by"),
                requested_at=_parse_datetime(approval_request.get("requested_at")),
                resolved_at=_parse_datetime(approval_request.get("resolved_at")),
                resolved_by=approval_request.get("resolved_by"),
                resolved_via=approval_request.get("resolved_via"),
                resolution_note=approval_request.get("resolution_note"),
                next_on_approve=approval_request.get("next_on_approve"),
                next_on_reject=approval_request.get("next_on_reject"),
                request_payload=approval_request,
                delivery_payload=delivery_payload,
                created_at=now,
                updated_at=now,
            )
            db.add(record)
        else:
            record.job_id = job_id
            record.job_type = job_type
            record.state = str(approval_request.get("state") or record.state)
            record.channel = str(approval_request.get("channel") or record.channel)
            record.title = approval_request.get("title")
            record.summary = approval_request.get("summary")
            record.requested_by = approval_request.get("requested_by")
            record.requested_at = _parse_datetime(approval_request.get("requested_at"))
            record.resolved_at = _parse_datetime(approval_request.get("resolved_at"))
            record.resolved_by = approval_request.get("resolved_by")
            record.resolved_via = approval_request.get("resolved_via")
            record.resolution_note = approval_request.get("resolution_note")
            record.next_on_approve = approval_request.get("next_on_approve")
            record.next_on_reject = approval_request.get("next_on_reject")
            record.request_payload = approval_request
            record.delivery_payload = delivery_payload
            record.updated_at = now

        db.commit()
        db.refresh(record)
        return record

    @staticmethod
    def to_dict(record: ApprovalRequestRecord) -> dict[str, Any]:
        return {
            "approval_id": record.approval_id,
            "tenant_id": record.tenant_id,
            "job_id": record.job_id,
            "job_type": record.job_type,
            "state": record.state,
            "channel": record.channel,
            "title": record.title,
            "summary": record.summary,
            "requested_by": record.requested_by,
            "requested_at": record.requested_at.isoformat() if record.requested_at else None,
            "resolved_at": record.resolved_at.isoformat() if record.resolved_at else None,
            "resolved_by": record.resolved_by,
            "resolved_via": record.resolved_via,
            "resolution_note": record.resolution_note,
            "next_on_approve": record.next_on_approve,
            "next_on_reject": record.next_on_reject,
            "request_payload": record.request_payload,
            "delivery_payload": record.delivery_payload,
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }