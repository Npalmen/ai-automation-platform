"""Persistence for production pilot ground-truth reviews."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.production_pilot.observability.models import ProductionPilotMessageReviewRecord


class PilotReviewTenantScopeError(Exception):
    pass


class ProductionPilotReviewRepository:
    @staticmethod
    def get_by_ref(
        db: Session,
        *,
        tenant_id: str,
        provider_message_ref_hash: str,
        review_version: int = 1,
    ) -> ProductionPilotMessageReviewRecord | None:
        return (
            db.query(ProductionPilotMessageReviewRecord)
            .filter(
                ProductionPilotMessageReviewRecord.tenant_id == tenant_id,
                ProductionPilotMessageReviewRecord.provider_message_ref_hash == provider_message_ref_hash,
                ProductionPilotMessageReviewRecord.review_version == review_version,
            )
            .first()
        )

    @staticmethod
    def list_for_tenant(
        db: Session,
        *,
        tenant_id: str,
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[ProductionPilotMessageReviewRecord]:
        query = db.query(ProductionPilotMessageReviewRecord).filter(
            ProductionPilotMessageReviewRecord.tenant_id == tenant_id
        )
        if start is not None:
            query = query.filter(ProductionPilotMessageReviewRecord.reviewed_at >= start)
        if end is not None:
            query = query.filter(ProductionPilotMessageReviewRecord.reviewed_at <= end)
        return query.order_by(ProductionPilotMessageReviewRecord.reviewed_at.asc()).all()

    @staticmethod
    def upsert_review(db: Session, payload: dict[str, Any]) -> ProductionPilotMessageReviewRecord:
        tenant_id = payload["tenant_id"]
        ref_hash = payload["provider_message_ref_hash"]
        version = int(payload.get("review_version") or 1)
        existing = ProductionPilotReviewRepository.get_by_ref(
            db,
            tenant_id=tenant_id,
            provider_message_ref_hash=ref_hash,
            review_version=version,
        )
        now = datetime.now(timezone.utc)
        if existing:
            for key, value in payload.items():
                if key in {"id", "created_at"}:
                    continue
                setattr(existing, key, value)
            existing.updated_at = now
            db.flush()
            return existing
        row = ProductionPilotMessageReviewRecord(
            id=payload.get("id") or str(uuid4()),
            created_at=now,
            updated_at=now,
            **payload,
        )
        try:
            with db.begin_nested():
                db.add(row)
                db.flush()
            return row
        except IntegrityError:
            existing = ProductionPilotReviewRepository.get_by_ref(
                db,
                tenant_id=tenant_id,
                provider_message_ref_hash=ref_hash,
                review_version=version,
            )
            if existing is None:
                raise
            for key, value in payload.items():
                if key in {"id", "created_at"}:
                    continue
                setattr(existing, key, value)
            existing.updated_at = now
            db.flush()
            return existing

    @staticmethod
    def to_dict(row: ProductionPilotMessageReviewRecord) -> dict[str, Any]:
        return {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "pilot_phase": row.pilot_phase,
            "provider_message_ref_hash": row.provider_message_ref_hash,
            "intake_event_id": row.intake_event_id,
            "job_id": row.job_id,
            "reviewed_by": row.reviewed_by,
            "reviewed_at": row.reviewed_at.isoformat(),
            "classification_verdict": row.classification_verdict,
            "extraction_verdict": row.extraction_verdict,
            "routing_verdict": row.routing_verdict,
            "manual_review_verdict": row.manual_review_verdict,
            "shadow_observation_verdict": row.shadow_observation_verdict,
            "match_proposal_verdict": row.match_proposal_verdict,
            "incident_severity": row.incident_severity,
            "error_category": row.error_category,
            "business_risk": row.business_risk,
            "blocks_next_phase": row.blocks_next_phase,
            "review_version": row.review_version,
        }
