"""Ground-truth review service for production pilot messages."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.production_pilot.constants import PILOT_TENANT_ID
from app.production_pilot.observability.constants import (
    BUSINESS_RISKS,
    CLASSIFICATION_VERDICTS,
    EXTRACTION_VERDICTS,
    INCIDENT_SEVERITIES,
    MANUAL_REVIEW_VERDICTS,
    MATCH_PROPOSAL_VERDICTS,
    ROUTING_VERDICTS,
    SHADOW_OBSERVATION_VERDICTS,
)
from app.production_pilot.observability.repository import (
    PilotReviewTenantScopeError,
    ProductionPilotReviewRepository,
)
from app.repositories.postgres.job_repository import JobRepository


def _validate_enum(value: str, allowed: frozenset[str], field: str) -> None:
    if value not in allowed:
        raise ValueError(f"{field} must be one of {sorted(allowed)}")


def validate_review_payload(payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    required = (
        "tenant_id",
        "provider_message_ref_hash",
        "job_id",
        "reviewed_by",
        "classification_verdict",
        "extraction_verdict",
        "routing_verdict",
        "manual_review_verdict",
        "shadow_observation_verdict",
        "match_proposal_verdict",
    )
    for key in required:
        if not payload.get(key):
            failures.append(f"{key} is required")
    try:
        _validate_enum(payload.get("classification_verdict", ""), CLASSIFICATION_VERDICTS, "classification_verdict")
        _validate_enum(payload.get("extraction_verdict", ""), EXTRACTION_VERDICTS, "extraction_verdict")
        _validate_enum(payload.get("routing_verdict", ""), ROUTING_VERDICTS, "routing_verdict")
        _validate_enum(payload.get("manual_review_verdict", ""), MANUAL_REVIEW_VERDICTS, "manual_review_verdict")
        _validate_enum(payload.get("shadow_observation_verdict", ""), SHADOW_OBSERVATION_VERDICTS, "shadow_observation_verdict")
        _validate_enum(payload.get("match_proposal_verdict", ""), MATCH_PROPOSAL_VERDICTS, "match_proposal_verdict")
        _validate_enum(payload.get("incident_severity", "none"), INCIDENT_SEVERITIES, "incident_severity")
        if payload.get("business_risk"):
            _validate_enum(payload["business_risk"], BUSINESS_RISKS, "business_risk")
    except ValueError as exc:
        failures.append(str(exc))
    if payload.get("tenant_id") and payload["tenant_id"] != PILOT_TENANT_ID:
        failures.append("reviews are pilot-tenant scoped only")
    if not payload.get("reviewed_by"):
        failures.append("reviewed_by operator identity is required")
    return failures


def submit_message_review(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    failures = validate_review_payload(payload)
    if failures:
        raise ValueError("; ".join(failures))
    tenant_id = payload["tenant_id"]
    job = JobRepository.get_job_by_id(db, tenant_id, payload["job_id"])
    if job is None:
        raise ValueError("job not found for tenant")
    if tenant_id != job.tenant_id:
        raise PilotReviewTenantScopeError("cross-tenant review blocked")
    record_payload = {
        **payload,
        "pilot_phase": payload.get("pilot_phase") or "P1",
        "review_version": int(payload.get("review_version") or 1),
        "reviewed_at": payload.get("reviewed_at") or datetime.now(timezone.utc),
        "incident_severity": payload.get("incident_severity") or "none",
        "blocks_next_phase": bool(payload.get("blocks_next_phase", False)),
    }
    row = ProductionPilotReviewRepository.upsert_review(db, record_payload)
    db.commit()
    return ProductionPilotReviewRepository.to_dict(row)
