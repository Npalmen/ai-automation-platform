"""CLI/API parity for TenantDeletionService."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.admin.incident_models import (
    IncidentRecord,
    IncidentSignalRecord,
    IncidentTenantRecord,
    IncidentTimelineEventRecord,
)
from app.admin.tenant_lifecycle.deletion_service import TenantDeletionService
from app.domain.integrations.models import IntegrationEvent
from app.repositories.postgres.action_execution_models import ActionExecutionRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.database import Base
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from app.tools.test_environment.purge_tenants import purge_tenants
from tests.onboarding_db_tables import onboarding_sqlite_tables


def _utc(dt: str) -> datetime:
    return datetime.fromisoformat(dt)


@pytest.fixture
def db():
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


def _seed_test_tenant(db, tenant_id: str, *, is_test: bool = True) -> None:
    db.add(
        TenantConfigRecord(
            tenant_id=tenant_id,
            name=tenant_id,
            status="active",
            settings={},
            is_test_tenant=is_test,
            lifecycle_status="onboarding",
            config_version=1,
            created_at=_utc("2026-01-01T00:00:00+00:00"),
            updated_at=_utc("2026-01-01T00:00:00+00:00"),
        )
    )
    db.commit()


class TestTenantDeletionParity:
    def test_api_and_cli_dry_run_same_tables(self, db):
        _seed_test_tenant(db, "T_TEST_DEL")
        api_dry = TenantDeletionService.dry_run(db, "T_TEST_DEL", require_test_tenant=True)
        cli_report = purge_tenants(
            db,
            explicit_tenant_ids=["T_TEST_DEL"],
            profile=None,
            dry_run=True,
        )
        assert api_dry.deletable is True
        api_tables = {row["table"]: row["rows"] for row in api_dry.tables}
        cli_tables = {
            line.table: line.rows
            for line in cli_report.lines
            if line.tenant_id == "T_TEST_DEL" and line.rows
        }
        assert api_tables == cli_tables

    def test_non_test_tenant_blocked_for_api_not_cli_profile(self, db):
        _seed_test_tenant(db, "T_REAL", is_test=False)
        api_dry = TenantDeletionService.dry_run(db, "T_REAL", require_test_tenant=True)
        cli_dry = TenantDeletionService.dry_run(db, "T_REAL", require_test_tenant=False)
        assert api_dry.deletable is False
        assert api_dry.blocked_reason == "not_test_tenant"
        assert cli_dry.deletable is True

    def test_pending_dispatch_blocks_both_paths(self, db):
        _seed_test_tenant(db, "T_PENDING")
        db.add(
            ApprovalRequestRecord(
                approval_id="appr-1",
                tenant_id="T_PENDING",
                job_id="job-1",
                job_type="lead",
                state="pending",
                channel="email",
                title="wait",
                summary="wait",
                requested_at=_utc("2026-01-02T00:00:00+00:00"),
            )
        )
        db.commit()
        api_dry = TenantDeletionService.dry_run(db, "T_PENDING", require_test_tenant=True)
        cli_report = purge_tenants(
            db,
            explicit_tenant_ids=["T_PENDING"],
            profile=None,
            dry_run=True,
        )
        assert api_dry.deletable is False
        assert api_dry.blocked_reason.startswith("pending_dispatch:")
        assert any(line.note and line.note.startswith("pending_dispatch:") for line in cli_report.lines)
