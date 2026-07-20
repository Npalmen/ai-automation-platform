"""
Tests for local/test environment reset tooling (Mellankapitel 8B).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.admin.incident_models import (
    IncidentRecord,
    IncidentSignalRecord,
    IncidentTenantRecord,
    IncidentTimelineEventRecord,
)
from app.domain.integrations.models import IntegrationEvent
from app.repositories.postgres.action_execution_models import ActionExecutionRecord
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.oauth_credential_models import OAuthCredentialRecord
from app.repositories.postgres.tenant_api_key_models import TenantApiKeyRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.database import Base
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from app.tools.test_environment.baseline_service import seed_baseline
from app.tools.test_environment.guards import (
    GuardError,
    assert_execute_allowed,
    verify_database_fingerprint,
)
from app.tools.test_environment.models import StaleDataType
from app.tools.test_environment.prune_stale import prune_stale_data
from app.tools.test_environment.purge_tenants import purge_tenants
from app.tools.test_environment.reserved_tenants import (
    BASELINE_TENANT_ID,
    LOCAL_STANDARD_PURGE_ALLOWLIST,
)


from tests.onboarding_db_tables import onboarding_sqlite_tables


def _utc(dt: str) -> datetime:
    return datetime.fromisoformat(dt)


@pytest.fixture()
def reset_db():
    engine = create_engine("sqlite:///:memory:")
    tables = onboarding_sqlite_tables() + [
        JobRecord.__table__,
        ApprovalRequestRecord.__table__,
        IncidentRecord.__table__,
        IncidentTenantRecord.__table__,
        IncidentSignalRecord.__table__,
        IncidentTimelineEventRecord.__table__,
        IntegrationEvent.__table__,
        ActionExecutionRecord.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _seed_tenant(db, tenant_id: str) -> None:
    db.add(
        TenantConfigRecord(
            tenant_id=tenant_id,
            name=tenant_id,
            status="active",
            settings={},
            created_at=_utc("2026-01-01T00:00:00+00:00"),
            updated_at=_utc("2026-01-01T00:00:00+00:00"),
        )
    )
    db.commit()


class TestGuards:
    def test_unknown_database_blocked(self):
        ok, reason = verify_database_fingerprint("postgresql://user:pw@db.example.com/prod")
        assert ok is False
        assert "not allowlisted" in reason

    def test_local_postgres_allowed(self):
        ok, _ = verify_database_fingerprint("postgresql://postgres:pw@localhost:5432/ai_platform")
        assert ok is True

    def test_execute_blocked_in_production_env(self):
        with patch.dict(os.environ, {"RESET_TEST_ENVIRONMENT_ALLOWED": "yes"}, clear=False):
            with patch("app.tools.test_environment.guards.get_settings") as mock_settings:
                mock_settings.return_value.ENV = "production"
                mock_settings.return_value.DATABASE_URL = (
                    "postgresql://postgres:pw@localhost:5432/ai_platform"
                )
                with pytest.raises(GuardError):
                    assert_execute_allowed(confirm="LOCAL_TEST_RESET")

    def test_execute_requires_confirm_phrase(self):
        with patch.dict(os.environ, {"RESET_TEST_ENVIRONMENT_ALLOWED": "yes"}, clear=False):
            with patch("app.tools.test_environment.guards.get_settings") as mock_settings:
                mock_settings.return_value.ENV = "dev"
                mock_settings.return_value.DATABASE_URL = "sqlite:///:memory:"
                with pytest.raises(GuardError):
                    assert_execute_allowed(confirm="WRONG")


class TestPurgeTenants:
    def test_dry_run_does_not_delete(self, reset_db):
        _seed_tenant(reset_db, "T_LOCAL_OPS_BASELINE")
        reset_db.add(
            JobRecord(
                job_id="job-1",
                tenant_id="T_LOCAL_OPS_BASELINE",
                job_type="lead",
                status="pending",
                input_data={},
                created_at=_utc("2026-01-02T00:00:00+00:00"),
                updated_at=_utc("2026-01-02T00:00:00+00:00"),
            )
        )
        reset_db.commit()

        report = purge_tenants(
            reset_db,
            explicit_tenant_ids=["T_LOCAL_OPS_BASELINE"],
            profile=None,
            dry_run=True,
        )
        assert report.dry_run is True
        assert reset_db.query(JobRecord).count() == 1

    def test_execute_removes_explicit_tenant_only(self, reset_db):
        _seed_tenant(reset_db, "T_LOCAL_OPS_BASELINE")
        _seed_tenant(reset_db, "T_KEEP_ME")
        reset_db.add(
            JobRecord(
                job_id="job-1",
                tenant_id="T_LOCAL_OPS_BASELINE",
                job_type="lead",
                status="pending",
                input_data={},
                created_at=_utc("2026-01-02T00:00:00+00:00"),
                updated_at=_utc("2026-01-02T00:00:00+00:00"),
            )
        )
        reset_db.commit()

        purge_tenants(
            reset_db,
            explicit_tenant_ids=["T_LOCAL_OPS_BASELINE"],
            profile=None,
            dry_run=False,
        )
        assert reset_db.query(TenantConfigRecord).filter_by(tenant_id="T_KEEP_ME").count() == 1
        assert (
            reset_db.query(TenantConfigRecord).filter_by(tenant_id="T_LOCAL_OPS_BASELINE").count()
            == 0
        )

    def test_profile_expands_allowlist_only(self):
        from app.tools.test_environment.inventory import resolve_purge_tenant_ids

        targets, _ = resolve_purge_tenant_ids(
            explicit_tenant_ids=[],
            profile="local-standard",
        )
        assert set(targets) == set(LOCAL_STANDARD_PURGE_ALLOWLIST)

    def test_cross_tenant_incident_preserved(self, reset_db):
        _seed_tenant(reset_db, "T_LOCAL_OPS_BASELINE")
        _seed_tenant(reset_db, "T_OTHER")
        reset_db.add(
            IncidentRecord(
                incident_id="INC-1",
                title="Shared",
                severity="warning",
                status="open",
                created_by="op",
                created_by_display_name="Op",
                created_at=_utc("2026-01-01T00:00:00+00:00"),
                updated_at=_utc("2026-01-01T00:00:00+00:00"),
            )
        )
        reset_db.add_all(
            [
                IncidentTenantRecord(
                    incident_id="INC-1",
                    tenant_id="T_LOCAL_OPS_BASELINE",
                    created_at=_utc("2026-01-01T00:00:00+00:00"),
                ),
                IncidentTenantRecord(
                    incident_id="INC-1",
                    tenant_id="T_OTHER",
                    created_at=_utc("2026-01-01T00:00:00+00:00"),
                ),
            ]
        )
        reset_db.add(
            IncidentTimelineEventRecord(
                event_id="evt-1",
                incident_id="INC-1",
                event_type="note",
                actor_id="op",
                actor_display_name="Op",
                actor_role="admin",
                message="timeline",
                created_at=_utc("2026-01-01T00:00:00+00:00"),
            )
        )
        reset_db.commit()

        purge_tenants(
            reset_db,
            explicit_tenant_ids=["T_LOCAL_OPS_BASELINE"],
            profile=None,
            dry_run=False,
        )

        assert reset_db.query(IncidentRecord).filter_by(incident_id="INC-1").count() == 1
        assert reset_db.query(IncidentTimelineEventRecord).count() == 1
        assert (
            reset_db.query(IncidentTenantRecord)
            .filter_by(incident_id="INC-1", tenant_id="T_OTHER")
            .count()
            == 1
        )

    def test_orphan_incident_deleted_when_last_link_removed(self, reset_db):
        _seed_tenant(reset_db, "T_LOCAL_OPS_BASELINE")
        reset_db.add(
            IncidentRecord(
                incident_id="INC-ORPHAN",
                title="Solo",
                severity="warning",
                status="open",
                created_by="op",
                created_by_display_name="Op",
                created_at=_utc("2026-01-01T00:00:00+00:00"),
                updated_at=_utc("2026-01-01T00:00:00+00:00"),
            )
        )
        reset_db.add(
            IncidentTenantRecord(
                incident_id="INC-ORPHAN",
                tenant_id="T_LOCAL_OPS_BASELINE",
                created_at=_utc("2026-01-01T00:00:00+00:00"),
            )
        )
        reset_db.add(
            IncidentTimelineEventRecord(
                event_id="evt-orphan",
                incident_id="INC-ORPHAN",
                event_type="note",
                actor_id="op",
                actor_display_name="Op",
                actor_role="admin",
                message="timeline",
                created_at=_utc("2026-01-01T00:00:00+00:00"),
            )
        )
        reset_db.commit()

        purge_tenants(
            reset_db,
            explicit_tenant_ids=["T_LOCAL_OPS_BASELINE"],
            profile=None,
            dry_run=False,
        )

        assert reset_db.query(IncidentRecord).count() == 0
        assert reset_db.query(IncidentTimelineEventRecord).count() == 0


class TestPruneStale:
    def test_pending_approvals_requires_threshold(self, reset_db):
        _seed_tenant(reset_db, "T_PRUNE")
        old = datetime.now(timezone.utc) - timedelta(days=40)
        reset_db.add(
            ApprovalRequestRecord(
                approval_id="appr-old",
                tenant_id="T_PRUNE",
                job_id="job-x",
                state="pending",
                channel="internal",
                created_at=old,
                updated_at=old,
                request_payload={},
            )
        )
        reset_db.commit()

        report = prune_stale_data(
            reset_db,
            tenant_id="T_PRUNE",
            data_type=StaleDataType.PENDING_APPROVALS,
            older_than_days=30,
            dry_run=False,
        )
        assert report.lines[0].rows == 1
        assert reset_db.query(ApprovalRequestRecord).count() == 0


class TestBaselineService:
    def test_seed_baseline_creates_reserved_tenant(self, reset_db):
        report = seed_baseline(reset_db, dry_run=False)
        assert any(line.table == "tenant_configs" for line in report.lines)
        tenant = reset_db.query(TenantConfigRecord).filter_by(tenant_id=BASELINE_TENANT_ID).one()
        assert tenant.name is not None
        assert reset_db.query(JobRecord).filter_by(tenant_id=BASELINE_TENANT_ID).count() >= 2
