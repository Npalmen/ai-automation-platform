"""Alert status parity between summary, indicator counts, and list filters."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.admin.alerts.models  # noqa: F401
from app.admin.alerts.models import OperatorAlertRecord
from app.admin.alerts.repository import AlertRepository
from app.admin.alerts.schemas import ACTIVE_ALERT_STATUSES
from app.admin.alerts.service import get_alert_summary, list_alerts
from app.repositories.postgres.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _alert(
    *,
    alert_id: str,
    status: str,
    severity: str,
    dedup: str,
) -> OperatorAlertRecord:
    now = _utcnow()
    return OperatorAlertRecord(
        id=alert_id,
        alert_type="job.stuck_processing",
        deduplication_key=dedup,
        scope_type="job",
        tenant_id="T_ALERT",
        related_job_id="j1",
        integration_key=None,
        severity=severity,
        status=status,
        title=f"Alert {alert_id}",
        summary="summary",
        safe_details={},
        source_class="intern_db_detected",
        source_version="1",
        first_detected_at=now,
        last_detected_at=now,
        occurrence_count=1,
        last_evaluated_at=now,
        current_fingerprint="fp",
        created_at=now,
        updated_at=now,
        version=1,
    )


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


class TestAlertStatusParity:
    def test_summary_matches_active_status_definition(self, db):
        db.add_all(
            [
                _alert(alert_id=str(uuid4()), status="open", severity="critical", dedup="d1"),
                _alert(alert_id=str(uuid4()), status="acknowledged", severity="high", dedup="d2"),
                _alert(alert_id=str(uuid4()), status="suppressed", severity="high", dedup="d3"),
                _alert(alert_id=str(uuid4()), status="resolved", severity="warning", dedup="d4"),
            ]
        )
        db.commit()

        summary = get_alert_summary(db)
        active = AlertRepository.list_active_alerts(db)
        counts = AlertRepository.count_open_by_severity(db)

        assert summary.total_open == sum(counts.values()) == len(active) == 2
        assert summary.open_critical == 1
        assert summary.open_high == 1
        assert summary.open_warning == 0

    def test_suppressed_and_resolved_excluded_from_open_filter(self, db):
        db.add_all(
            [
                _alert(alert_id=str(uuid4()), status="open", severity="warning", dedup="d5"),
                _alert(alert_id=str(uuid4()), status="suppressed", severity="warning", dedup="d6"),
                _alert(alert_id=str(uuid4()), status="resolved", severity="warning", dedup="d7"),
            ]
        )
        db.commit()

        open_items, open_total = AlertRepository.list_alerts(db, status=list(ACTIVE_ALERT_STATUSES))
        assert open_total == 1
        assert open_items[0].status == "open"

        summary = get_alert_summary(db)
        assert summary.total_open == 1
        assert summary.open_warning == 1
