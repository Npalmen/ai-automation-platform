"""
Tests for Kapitel 7 usage/cost/capacity endpoints.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.admin.usage import get_usage_overview, get_usage_tenants
from app.admin.usage_repository import (
    compute_peak_jobs_per_hour,
    compute_period_bounds,
    sum_jobs_received_global,
)
from app.admin.usage_schemas import (
    AUTOMATION_RATE_NOT_MEASURED_REASON,
    MANUAL_REVIEWS_NOT_MEASURED_REASON,
)
from app.admin.incident_models import IncidentRecord, IncidentTenantRecord
from app.domain.integrations.models import IntegrationEvent
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.database import Base
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord


def _utc(dt: str) -> datetime:
    return datetime.fromisoformat(dt)


def _settings(**kwargs):
    defaults = {"ADMIN_API_KEY": "test-admin-key", "APP_NAME": "Test"}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


@pytest.fixture()
def usage_db():
    engine = create_engine("sqlite:///:memory:")
    tables = [
        TenantConfigRecord.__table__,
        JobRecord.__table__,
        AuditEventRecord.__table__,
        ApprovalRequestRecord.__table__,
        IntegrationEvent.__table__,
        IncidentRecord.__table__,
        IncidentTenantRecord.__table__,
    ]
    Base.metadata.create_all(bind=engine, tables=tables)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _seed_tenant(db, tenant_id: str, name: str = "Acme") -> None:
    db.add(
        TenantConfigRecord(
            tenant_id=tenant_id,
            name=name,
            status="active",
            settings={},
            created_at=_utc("2026-01-01T00:00:00+00:00"),
            updated_at=_utc("2026-01-01T00:00:00+00:00"),
        )
    )
    db.commit()


class TestPeriodBounds:
    def test_half_open_comparison_contiguous(self):
        now = _utc("2026-07-17T12:00:00+00:00")
        bounds = compute_period_bounds(30, now=now)
        assert bounds["comparison_ended_at"] == bounds["started_at"]
        assert bounds["started_at"] == now - timedelta(days=30)
        assert bounds["comparison_started_at"] == now - timedelta(days=60)

    def test_boundary_inclusion_exclusion(self, usage_db):
        now = _utc("2026-07-17T12:00:00+00:00")
        bounds = compute_period_bounds(7, now=now)
        start = bounds["started_at"]
        end = bounds["ended_at"]

        usage_db.add(
            JobRecord(
                job_id="J_AT_START",
                tenant_id="T_A",
                job_type="lead",
                status="received",
                input_data={},
                created_at=start,
                updated_at=start,
            )
        )
        usage_db.add(
            JobRecord(
                job_id="J_AT_END",
                tenant_id="T_A",
                job_type="lead",
                status="received",
                input_data={},
                created_at=end,
                updated_at=end,
            )
        )
        usage_db.commit()

        assert sum_jobs_received_global(usage_db, start=start, end=end) == 1


class TestPeakJobsPerHour:
    def test_python_bucketing_sqlite(self, usage_db):
        base = _utc("2026-07-10T10:15:00+00:00")
        for idx in range(3):
            usage_db.add(
                JobRecord(
                    job_id=f"J_{idx}",
                    tenant_id="T_A",
                    job_type="lead",
                    status="received",
                    input_data={},
                    created_at=base + timedelta(minutes=idx * 10),
                    updated_at=base,
                )
            )
        usage_db.add(
            JobRecord(
                job_id="J_OTHER_HOUR",
                tenant_id="T_A",
                job_type="lead",
                status="received",
                input_data={},
                created_at=base + timedelta(hours=1),
                updated_at=base,
            )
        )
        usage_db.commit()

        start = base - timedelta(hours=1)
        end = base + timedelta(hours=3)
        assert compute_peak_jobs_per_hour(usage_db, start=start, end=end) == 3


class TestUsageMetrics:
    @patch("app.admin.usage.collect_all_triage_rows", return_value=[])
    def test_jobs_completed_proxy_and_automation_not_measured(self, _triage, usage_db):
        _seed_tenant(usage_db, "T_A")
        now = _utc("2026-07-17T12:00:00+00:00")
        bounds = compute_period_bounds(30, now=now)

        usage_db.add(
            JobRecord(
                job_id="J_DONE",
                tenant_id="T_A",
                job_type="lead",
                status="completed",
                input_data={},
                created_at=bounds["started_at"] + timedelta(days=1),
                updated_at=bounds["started_at"] + timedelta(days=2),
            )
        )
        usage_db.add(
            AuditEventRecord(
                event_id="E_OP",
                tenant_id="T_A",
                category="operator_action",
                action="tenant.pause_automation",
                status="completed",
                details={},
                created_at=bounds["started_at"] + timedelta(days=3),
            )
        )
        usage_db.add(
            AuditEventRecord(
                event_id="E_GMAIL",
                tenant_id="T_A",
                category="manual_review",
                action="gmail_handoff_applied",
                status="success",
                details={},
                created_at=bounds["started_at"] + timedelta(days=4),
            )
        )
        usage_db.commit()

        overview = get_usage_overview(usage_db, days=30, app_settings=_settings())
        assert overview.summary.jobs_completed.current.value == 1
        assert overview.summary.jobs_completed.current.timestamp_basis == "updated_at_proxy"
        assert overview.summary.automation_rate.status == "not_measured"
        assert overview.summary.automation_rate.reason == AUTOMATION_RATE_NOT_MEASURED_REASON
        assert overview.summary.manual_reviews_created.status == "not_measured"
        assert overview.summary.manual_reviews_created.reason == MANUAL_REVIEWS_NOT_MEASURED_REASON
        assert overview.summary.gmail_manual_review_handoffs.current == 1
        assert overview.summary.operator_actions.current == 1
        assert overview.ai_usage.status == "not_measured"
        assert overview.ai_cost.status == "unknown"
        assert overview.ai_cost.amount is None
        assert overview.capacity.status == "baseline_missing"

    @patch("app.admin.usage.collect_all_triage_rows", return_value=[])
    def test_percentage_change_null_when_previous_zero(self, _triage, usage_db):
        _seed_tenant(usage_db, "T_A")
        now = _utc("2026-07-17T12:00:00+00:00")
        bounds = compute_period_bounds(7, now=now)
        usage_db.add(
            JobRecord(
                job_id="J1",
                tenant_id="T_A",
                job_type="lead",
                status="received",
                input_data={},
                created_at=bounds["started_at"] + timedelta(hours=1),
                updated_at=bounds["started_at"] + timedelta(hours=1),
            )
        )
        usage_db.commit()

        with patch("app.admin.usage.compute_period_bounds", return_value=bounds):
            overview = get_usage_overview(usage_db, days=7, app_settings=_settings())
        assert overview.summary.jobs_received.current == 1
        assert overview.summary.jobs_received.previous == 0
        assert overview.summary.jobs_received.percentage_change is None

    @patch("app.admin.usage.collect_all_triage_rows", return_value=[])
    def test_integration_errors_counted(self, _triage, usage_db):
        _seed_tenant(usage_db, "T_A")
        now = _utc("2026-07-17T12:00:00+00:00")
        bounds = compute_period_bounds(30, now=now)
        usage_db.add(
            IntegrationEvent(
                job_id="J1",
                tenant_id="T_A",
                integration_type="visma",
                payload={},
                status="failed",
                attempts=1,
                idempotency_key="idem-1",
                created_at=bounds["started_at"] + timedelta(days=1),
            )
        )
        usage_db.commit()

        with patch("app.admin.usage.compute_period_bounds", return_value=bounds):
            overview = get_usage_overview(usage_db, days=30, app_settings=_settings())
        assert overview.summary.integration_errors.current == 1


class TestUsageTenantList:
    @patch("app.admin.usage.collect_all_triage_rows", return_value=[])
    def test_filter_sort_pagination(self, _triage, usage_db):
        for idx in range(3):
            _seed_tenant(usage_db, f"T_{idx}", name=f"Tenant {idx}")
            usage_db.add(
                JobRecord(
                    job_id=f"J_{idx}",
                    tenant_id=f"T_{idx}",
                    job_type="lead",
                    status="received",
                    input_data={},
                    created_at=_utc("2026-07-10T10:00:00+00:00"),
                    updated_at=_utc("2026-07-10T10:00:00+00:00"),
                )
            )
        usage_db.commit()

        with patch("app.admin.usage._utcnow", return_value=_utc("2026-07-17T12:00:00+00:00")):
            result = get_usage_tenants(
                usage_db,
                days=30,
                app_settings=_settings(),
                minimum_jobs=1,
                sort="customer",
                order="asc",
                limit=2,
                offset=0,
            )
        assert result.total == 3
        assert len(result.items) == 2
        assert result.items[0].customer_name == "Tenant 0"

    @patch("app.admin.usage.collect_all_triage_rows", return_value=[])
    def test_batch_functions_called_once_per_request(self, _triage, usage_db):
        for idx in range(5):
            _seed_tenant(usage_db, f"T_{idx}")
            usage_db.add(
                JobRecord(
                    job_id=f"J_{idx}",
                    tenant_id=f"T_{idx}",
                    job_type="lead",
                    status="received",
                    input_data={},
                    created_at=_utc("2026-07-10T10:00:00+00:00"),
                    updated_at=_utc("2026-07-10T10:00:00+00:00"),
                )
            )
        usage_db.commit()

        patches = {
            "batch_jobs_received_by_tenant": MagicMock(return_value={}),
            "batch_jobs_terminal_by_tenant": MagicMock(return_value={}),
            "batch_audit_by_tenant": MagicMock(return_value={}),
            "batch_incidents_created_by_tenant": MagicMock(return_value={}),
            "batch_integration_errors_by_tenant": MagicMock(return_value={}),
            "batch_pending_approvals_by_tenant": MagicMock(return_value={}),
            "batch_open_manual_reviews_by_tenant": MagicMock(return_value={}),
            "batch_latest_activity_by_tenant": MagicMock(return_value={}),
        }
        with patch.multiple("app.admin.usage", **patches):
            with patch("app.admin.usage._utcnow", return_value=_utc("2026-07-17T12:00:00+00:00")):
                get_usage_tenants(usage_db, days=30, app_settings=_settings())

        for name, mock in patches.items():
            if name == "batch_jobs_terminal_by_tenant":
                assert mock.call_count == 2, "completed + failed terminal counts"
                continue
            if name == "batch_audit_by_tenant":
                assert mock.call_count == 2, "operator_action + gmail handoff counts"
                continue
            assert mock.call_count == 1, f"{name} should be called once, got {mock.call_count}"
        # attention_status still uses collect_all_triage_rows once (pre-existing O(tenants) cost)
        assert _triage.call_count == 1


class TestUsageRoutes:
    def test_overview_requires_auth(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)
        assert client.get("/admin/usage/overview").status_code == 401

    def test_invalid_days_rejected(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)
        with patch("app.core.admin_auth.resolve_authenticated_operator") as resolve:
            resolve.return_value = {
                "id": "op",
                "display_name": "Op",
                "role": "read_only",
            }
            response = client.get(
                "/admin/usage/overview?days=14",
                headers={"X-Admin-API-Key": "test-admin-key"},
            )
        assert response.status_code == 422

    def test_read_only_allowed(self):
        from fastapi.testclient import TestClient
        from app.admin.usage_schemas import (
            AiCostBlock,
            AiUsageBlock,
            CapacityBlock,
            ComparisonInt,
            ComparisonProxyMetric,
            NotMeasuredValue,
            ProxyTimestampMetric,
            UsageOverviewResponse,
            UsagePeriod,
            UsageSummary,
        )
        from app.main import app

        now = _utc("2026-07-17T12:00:00+00:00")
        started = now - timedelta(days=30)
        comparison_started = now - timedelta(days=60)
        zero_proxy = ComparisonProxyMetric(
            current=ProxyTimestampMetric(value=0),
            previous=ProxyTimestampMetric(value=0),
            absolute_change=0,
            percentage_change=None,
        )
        not_measured = NotMeasuredValue(reason="test")
        summary = UsageSummary(
            active_tenants=0,
            tenants_with_activity=0,
            jobs_received=ComparisonInt(
                current=0, previous=0, absolute_change=0, percentage_change=None
            ),
            jobs_completed=zero_proxy,
            jobs_failed=zero_proxy,
            automation_rate=not_measured,
            operator_actions=ComparisonInt(
                current=0, previous=0, absolute_change=0, percentage_change=None
            ),
            gmail_manual_review_handoffs=ComparisonInt(
                current=0, previous=0, absolute_change=0, percentage_change=None
            ),
            manual_reviews_created=not_measured,
            open_manual_reviews_current=0,
            pending_approvals_current=0,
            incidents_created=ComparisonInt(
                current=0, previous=0, absolute_change=0, percentage_change=None
            ),
            incidents_resolved=ComparisonInt(
                current=0, previous=0, absolute_change=0, percentage_change=None
            ),
            open_incidents_current=0,
            critical_incidents_created=ComparisonInt(
                current=0, previous=0, absolute_change=0, percentage_change=None
            ),
            integration_errors=ComparisonInt(
                current=0, previous=0, absolute_change=0, percentage_change=None
            ),
            needs_help_open_current=0,
            tenants_with_open_signals_current=0,
        )
        payload = UsageOverviewResponse(
            generated_at=now,
            period=UsagePeriod(
                days=30,
                started_at=started,
                ended_at=now,
                comparison_started_at=comparison_started,
                comparison_ended_at=started,
            ),
            summary=summary,
            ai_usage=AiUsageBlock(status="not_measured"),
            ai_cost=AiCostBlock(status="unknown", amount=None),
            capacity=CapacityBlock(status="baseline_missing"),
        )

        client = TestClient(app, raise_server_exceptions=False)
        with patch("app.admin.usage.get_usage_overview", return_value=payload):
            with patch("app.core.admin_auth.resolve_authenticated_operator") as resolve:
                resolve.return_value = {
                    "id": "op",
                    "display_name": "Op",
                    "role": "read_only",
                }
                response = client.get(
                    "/admin/usage/overview",
                    headers={"X-Admin-API-Key": "test-admin-key"},
                )
        assert response.status_code == 200

    def test_tenant_key_rejected(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(
            "/admin/usage/overview",
            headers={"X-API-Key": "tenant-key"},
        )
        assert response.status_code == 401
