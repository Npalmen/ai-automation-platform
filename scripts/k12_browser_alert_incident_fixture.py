"""
Synthetic operator alert + incident fixtures for K12 browser Del 7 probes.

Tenant-isolated IDs prefixed with k12-browser-. No external integration writes.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_TEST_TENANT = "T_K12_BROWSER"
OTHER_TEST_TENANT = "T_K12_BROWSER_OTHER"
ALERT_PREFIX = "k12-browser-alert-"
INCIDENT_PREFIX = "k12-browser-incident-"
JOB_PREFIX = "k12-browser-job-"
FIXTURE_ALERT_TYPE = "job.stuck_processing"
FIXTURE_SUPPRESS_ALERT_TYPE = "system.backup_stale"
FIXTURE_ALERT_SOURCE = "k12_browser_fixture"


def _engine():
    from sqlalchemy import create_engine

    from app.core.settings import get_settings

    settings = get_settings()
    url = settings.DATABASE_URL.strip()
    if not url:
        raise RuntimeError("DATABASE_URL not configured")
    return create_engine(url)


def _ensure_tenant(db, tenant_id: str, name: str, now: datetime) -> None:
    from sqlalchemy import text

    db.execute(
        text(
            """
            INSERT INTO tenant_configs (
                tenant_id, name, slug, status, settings,
                enabled_job_types, allowed_integrations, created_at, updated_at
            )
            VALUES (
                :tenant_id, :name, :slug, 'active', :settings,
                '[]', '[]', :now, :now
            )
            ON CONFLICT (tenant_id) DO UPDATE SET updated_at = :now
            """
        ),
        {
            "tenant_id": tenant_id,
            "name": name,
            "slug": tenant_id.lower(),
            "settings": json.dumps({"scheduler": {"run_mode": "manual"}}),
            "now": now,
        },
    )


def _insert_open_alert(
    db,
    *,
    alert_id: str,
    tenant_id: str | None,
    dedup_suffix: str,
    title: str,
    now: datetime,
    alert_type: str = FIXTURE_ALERT_TYPE,
    scope_type: str = "job",
) -> None:
    from sqlalchemy import text

    dedup_key = (
        f"system:backup:stale:k12-browser:{dedup_suffix}"
        if scope_type == "backup"
        else f"tenant:{tenant_id}:k12-browser:{dedup_suffix}"
    )
    db.execute(
        text(
            """
            INSERT INTO operator_alerts (
                id, alert_type, deduplication_key, scope_type, tenant_id,
                related_job_id, integration_key, severity, status, title, summary,
                safe_details, source, source_class, source_version,
                first_detected_at, last_detected_at, occurrence_count,
                last_evaluated_at, current_fingerprint, created_at, updated_at, version
            )
            VALUES (
                :id, :alert_type, :dedup_key, :scope_type, :tenant_id,
                NULL, NULL, 'warning', 'open', :title, :summary,
                CAST(:safe_details AS JSONB), :source, 'intern_db_detected', '1',
                :now, :now, 1,
                :now, :fingerprint, :now, :now, 1
            )
            ON CONFLICT (id) DO UPDATE SET
                status='open',
                acknowledged_at=NULL,
                acknowledged_by=NULL,
                snoozed_until=NULL,
                resolved_at=NULL,
                resolution_reason=NULL,
                version=1,
                updated_at=:now
            """
        ),
        {
            "id": alert_id,
            "alert_type": alert_type,
            "dedup_key": dedup_key,
            "scope_type": scope_type,
            "tenant_id": tenant_id,
            "title": title,
            "summary": "Synthetic K12 browser fixture — no external write.",
            "safe_details": json.dumps({"k12_browser_fixture": True}),
            "source": FIXTURE_ALERT_SOURCE,
            "now": now,
            "fingerprint": f"k12-browser-{dedup_suffix}",
        },
    )


def _insert_open_incident(
    db,
    *,
    incident_id: str,
    tenant_id: str,
    now: datetime,
) -> None:
    from sqlalchemy import text

    db.execute(
        text(
            """
            INSERT INTO incidents (
                incident_id, title, description, severity, status,
                owner_id, owner_display_name, created_by, created_by_display_name,
                created_at, updated_at, version
            )
            VALUES (
                :incident_id, :title, :description, 'warning', 'open',
                NULL, NULL, 'k12-browser-fixture', 'K12 Browser Fixture',
                :now, :now, 1
            )
            ON CONFLICT (incident_id) DO UPDATE SET
                status='open',
                owner_id=NULL,
                owner_display_name=NULL,
                acknowledged_at=NULL,
                resolved_at=NULL,
                closed_at=NULL,
                resolution_summary=NULL,
                version=1,
                updated_at=:now
            """
        ),
        {
            "incident_id": incident_id,
            "title": "K12 browser matrix — synthetic incident",
            "description": "Synthetic incident for operator browser verification.",
            "now": now,
        },
    )
    db.execute(
        text(
            """
            DELETE FROM incident_tenants
            WHERE incident_id = :incident_id
            """
        ),
        {"incident_id": incident_id},
    )
    db.execute(
        text(
            """
            INSERT INTO incident_tenants (
                incident_id, tenant_id, tenant_name_snapshot, created_at
            )
            VALUES (:incident_id, :tenant_id, :tenant_name, :now)
            """
        ),
        {
            "incident_id": incident_id,
            "tenant_id": tenant_id,
            "tenant_name": "K12 Browser Fixture",
            "now": now,
        },
    )
    db.execute(
        text(
            """
            DELETE FROM incident_timeline_events
            WHERE incident_id = :incident_id
            """
        ),
        {"incident_id": incident_id},
    )


def _insert_cross_tenant_job(db, *, job_id: str, tenant_id: str, now: datetime) -> None:
    from sqlalchemy import text

    db.execute(
        text(
            """
            INSERT INTO jobs (
                job_id, tenant_id, job_type, status, input_data, created_at, updated_at
            )
            VALUES (
                :job_id, :tenant_id, 'lead', 'failed', CAST(:input_data AS JSONB), :now, :now
            )
            ON CONFLICT (job_id) DO UPDATE SET
                tenant_id=:tenant_id,
                status='failed',
                updated_at=:now
            """
        ),
        {
            "job_id": job_id,
            "tenant_id": tenant_id,
            "input_data": json.dumps({"k12_browser_fixture": True}),
            "now": now,
        },
    )


def setup_synthetic_alert_incident(tenant_id: str | None = None) -> dict[str, str]:
    from sqlalchemy.orm import sessionmaker

    tenant = (tenant_id or DEFAULT_TEST_TENANT).strip()
    other_tenant = OTHER_TEST_TENANT
    now = datetime.now(timezone.utc)
    alert_ack_id = str(uuid.uuid4())
    alert_snooze_id = str(uuid.uuid4())
    alert_suppress_id = str(uuid.uuid4())
    other_alert_id = str(uuid.uuid4())
    incident_id = f"{INCIDENT_PREFIX}{uuid.uuid4()}"
    cross_job_id = f"{JOB_PREFIX}cross-{uuid.uuid4()}"

    engine = _engine()
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        cleanup_synthetic_alert_incidents(tenant, db=db)
        _ensure_tenant(db, tenant, "K12 Browser Fixture", now)
        _ensure_tenant(db, other_tenant, "K12 Browser Other Fixture", now)
        _insert_open_alert(
            db,
            alert_id=alert_ack_id,
            tenant_id=tenant,
            dedup_suffix="ack",
            title="K12 browser — alert acknowledge probe",
            now=now,
        )
        _insert_open_alert(
            db,
            alert_id=alert_snooze_id,
            tenant_id=tenant,
            dedup_suffix="snooze",
            title="K12 browser — alert snooze probe",
            now=now,
        )
        _insert_open_alert(
            db,
            alert_id=alert_suppress_id,
            tenant_id=None,
            dedup_suffix="suppress",
            title="K12 browser — alert suppress probe",
            now=now,
            alert_type=FIXTURE_SUPPRESS_ALERT_TYPE,
            scope_type="backup",
        )
        _insert_open_alert(
            db,
            alert_id=other_alert_id,
            tenant_id=other_tenant,
            dedup_suffix="other",
            title="K12 browser — other tenant alert",
            now=now,
        )
        _insert_open_incident(
            db,
            incident_id=incident_id,
            tenant_id=tenant,
            now=now,
        )
        _insert_cross_tenant_job(db, job_id=cross_job_id, tenant_id=tenant, now=now)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    return {
        "tenant_id": tenant,
        "other_tenant_id": other_tenant,
        "alert_ack_id": alert_ack_id,
        "alert_snooze_id": alert_snooze_id,
        "alert_suppress_id": alert_suppress_id,
        "other_alert_id": other_alert_id,
        "incident_id": incident_id,
        "cross_job_id": cross_job_id,
        "alert_detail_path": f"/ops/alerts/{alert_ack_id}",
        "alert_suppress_path": f"/ops/alerts/{alert_suppress_id}",
        "incident_detail_path": f"/ops/incidents/{incident_id}",
    }


def cleanup_synthetic_alert_incidents(
    tenant_id: str | None = None,
    *,
    db=None,
) -> int:
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    tenant = (tenant_id or DEFAULT_TEST_TENANT).strip()
    own_session = db is None
    if own_session:
        engine = _engine()
        Session = sessionmaker(bind=engine)
        db = Session()
    deleted = 0
    try:
        for table_action in ("alerts", "incidents", "jobs"):
            if table_action == "alerts":
                result = db.execute(
                    text(
                        """
                        DELETE FROM operator_alerts
                        WHERE source = :source
                           OR deduplication_key LIKE :dedup_prefix
                        """
                    ),
                    {"source": FIXTURE_ALERT_SOURCE, "dedup_prefix": "%:k12-browser:%"},
                )
            elif table_action == "incidents":
                db.execute(
                    text(
                        """
                        DELETE FROM incident_timeline_events
                        WHERE incident_id LIKE :prefix
                        """
                    ),
                    {"prefix": f"{INCIDENT_PREFIX}%"},
                )
                db.execute(
                    text(
                        """
                        DELETE FROM incident_tenants
                        WHERE incident_id LIKE :prefix
                        """
                    ),
                    {"prefix": f"{INCIDENT_PREFIX}%"},
                )
                result = db.execute(
                    text("DELETE FROM incidents WHERE incident_id LIKE :prefix"),
                    {"prefix": f"{INCIDENT_PREFIX}%"},
                )
            else:
                result = db.execute(
                    text(
                        """
                        DELETE FROM jobs
                        WHERE job_id LIKE :prefix
                           OR (tenant_id = :tenant_id AND job_id LIKE :job_prefix)
                        """
                    ),
                    {"prefix": f"{JOB_PREFIX}%", "tenant_id": tenant, "job_prefix": f"{JOB_PREFIX}%"},
                )
            deleted += int(result.rowcount or 0)
        if own_session:
            db.commit()
    except Exception:
        if own_session:
            db.rollback()
        raise
    finally:
        if own_session:
            db.close()
    return deleted


def count_audit_events(
    *,
    tenant_id: str,
    category: str,
    action: str,
    detail_key: str,
    detail_value: str,
) -> int:
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    engine = _engine()
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        row = db.execute(
            text(
                """
                SELECT COUNT(*) AS cnt
                FROM audit_events
                WHERE tenant_id = :tenant_id
                  AND category = :category
                  AND action = :action
                  AND details ->> :detail_key = :detail_value
                """
            ),
            {
                "tenant_id": tenant_id,
                "category": category,
                "action": action,
                "detail_key": detail_key,
                "detail_value": detail_value,
            },
        ).one()
        return int(row.cnt or 0)
    finally:
        db.close()


def count_incident_timeline_events(*, incident_id: str, event_type: str) -> int:
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    engine = _engine()
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        row = db.execute(
            text(
                """
                SELECT COUNT(*) AS cnt
                FROM incident_timeline_events
                WHERE incident_id = :incident_id
                  AND event_type = :event_type
                """
            ),
            {"incident_id": incident_id, "event_type": event_type},
        ).one()
        return int(row.cnt or 0)
    finally:
        db.close()


def count_notification_deliveries_for_alerts(alert_ids: list[str]) -> int:
    if not alert_ids:
        return 0
    from sqlalchemy import text
    from sqlalchemy.orm import sessionmaker

    engine = _engine()
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        placeholders = ", ".join(f":id{i}" for i in range(len(alert_ids)))
        params = {f"id{i}": alert_id for i, alert_id in enumerate(alert_ids)}
        row = db.execute(
            text(
                f"""
                SELECT COUNT(*) AS cnt
                FROM notification_deliveries
                WHERE alert_id IN ({placeholders})
                """
            ),
            params,
        ).one()
        return int(row.cnt or 0)
    finally:
        db.close()


def fixture_summary(artifacts: dict[str, str]) -> dict[str, Any]:
    return {
        "tenant_id": artifacts.get("tenant_id"),
        "alert_id_prefix": ALERT_PREFIX,
        "incident_id_prefix": INCIDENT_PREFIX,
        "alert_detail_path": artifacts.get("alert_detail_path"),
        "alert_suppress_path": artifacts.get("alert_suppress_path"),
        "incident_detail_path": artifacts.get("incident_detail_path"),
        "external_side_effects": 0,
    }


def list_active_key_hints(tenant_id: str) -> list[str]:
    from sqlalchemy.orm import sessionmaker

    from app.repositories.postgres.tenant_api_key_models import TenantApiKeyRecord

    engine = _engine()
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        rows = (
            db.query(TenantApiKeyRecord)
            .filter(
                TenantApiKeyRecord.tenant_id == tenant_id,
                TenantApiKeyRecord.is_active.is_(True),
            )
            .order_by(TenantApiKeyRecord.created_at.desc())
            .all()
        )
        return [row.key_hint for row in rows if row.key_hint]
    finally:
        db.close()


def lookup_tenant_for_raw_key(raw_key: str) -> str | None:
    from sqlalchemy.orm import sessionmaker

    from app.repositories.postgres.tenant_api_key_repository import TenantApiKeyRepository

    engine = _engine()
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        return TenantApiKeyRepository.lookup_tenant(db, raw_key)
    finally:
        db.close()
