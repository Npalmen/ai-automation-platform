"""Deduplicated intake enforcement alerts (Onboarding 2.0, DEC-032)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.admin.alerts.models import OperatorAlertRecord
from app.admin.alerts.repository import AlertRepository
from app.workflows.intake_enforcement import DEDUPE_KEY_BEFORE_CUTOFF, DEDUPE_KEY_MISSING_CUTOFF

logger = logging.getLogger(__name__)

_ALERT_TYPES = {
    DEDUPE_KEY_BEFORE_CUTOFF: "intake.before_cutoff",
    DEDUPE_KEY_MISSING_CUTOFF: "intake.missing_cutoff",
}


def maybe_emit_intake_skip_alert(
    db: Session,
    *,
    tenant_id: str,
    dedupe_key: str | None,
    reason: str | None,
) -> None:
    """Create or bump a deduplicated tenant alert when intake gate blocks a message."""
    if not dedupe_key or dedupe_key not in _ALERT_TYPES:
        return
    now = datetime.now(timezone.utc)
    alert_type = _ALERT_TYPES[dedupe_key]
    deduplication_key = f"{tenant_id}:{dedupe_key}"
    title = (
        "Intag blockerat före cutoff"
        if dedupe_key == DEDUPE_KEY_BEFORE_CUTOFF
        else "Intag saknar cutoff"
    )
    summary = (
        "Minst ett Gmail-meddelande hoppades över eftersom det ligger före intake-cutoff."
        if dedupe_key == DEDUPE_KEY_BEFORE_CUTOFF
        else "Aktiv tenant saknar intake-cutoff — meddelanden blockeras fail-closed."
    )
    safe_details = {"reason": reason, "dedupe_key": dedupe_key}
    try:
        existing = AlertRepository.get_active_by_dedup_key(db, deduplication_key)
        if existing is not None:
            existing.last_detected_at = now
            existing.last_evaluated_at = now
            existing.occurrence_count += 1
            existing.summary = summary
            existing.safe_details = safe_details
            existing.updated_at = now
        else:
            AlertRepository.add_alert(
                db,
                OperatorAlertRecord(
                    id=str(uuid4()),
                    alert_type=alert_type,
                    deduplication_key=deduplication_key,
                    scope_type="tenant",
                    tenant_id=tenant_id,
                    severity="warning",
                    status="open",
                    title=title,
                    summary=summary,
                    safe_details=safe_details,
                    source_class="intern_metadata_detected",
                    source_version="1",
                    first_detected_at=now,
                    last_detected_at=now,
                    occurrence_count=1,
                    last_evaluated_at=now,
                    current_fingerprint=dedupe_key,
                    created_at=now,
                    updated_at=now,
                    version=1,
                ),
            )
        db.commit()
    except Exception:
        logger.exception("intake_alert_emit_failed", extra={"tenant_id": tenant_id})
        db.rollback()
