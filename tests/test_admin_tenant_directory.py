"""
Tests for GET /admin/tenants and GET /admin/tenants/{tenant_id}/overview (Kapitel 3).
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.admin.tenant_directory import (
    _derive_tenant_health,
    _integrations_summary_for_tenant,
    _normalize_tenant_status,
    get_tenant_detail,
    list_admin_tenants,
)
from app.admin.tenant_directory_schemas import TenantDetailResponse, TenantListResponse
from app.main import app


def _settings(**kwargs):
    defaults = {
        "ADMIN_API_KEY": "test-admin-key",
        "APP_NAME": "Test",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _mock_db():
    db = MagicMock()
    q = MagicMock()
    q.filter.return_value = q
    q.group_by.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.count.return_value = 0
    q.first.return_value = None
    q.all.return_value = []
    db.query.return_value = q
    return db


def _tenant(
    tenant_id="T_A",
    name="Acme",
    status="active",
    settings=None,
    enabled_job_types=None,
    allowed_integrations=None,
):
    r = MagicMock()
    r.tenant_id = tenant_id
    r.name = name
    r.slug = "acme"
    r.status = status
    r.settings = settings or {}
    r.enabled_job_types = enabled_job_types or ["lead"]
    r.allowed_integrations = allowed_integrations or ["google_mail"]
    r.created_at = datetime(2025, 1, 1, tzinfo=timezone.utc)
    r.updated_at = datetime(2025, 6, 1, tzinfo=timezone.utc)
    return r


def _to_dict(record):
    return {
        "tenant_id": record.tenant_id,
        "name": record.name,
        "slug": record.slug,
        "status": record.status,
        "enabled_job_types": record.enabled_job_types or [],
        "allowed_integrations": record.allowed_integrations or [],
        "auto_actions": {},
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }


def _batch_query_side_effect(db, pending=None, manual=None, jobs_30d=None):
    pending = pending or {}
    manual = manual or {}
    jobs_30d = jobs_30d or {}

    def query_side_effect(model):
        q = MagicMock()
        q.filter.return_value = q
        q.group_by.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        q.first.return_value = None
        name = getattr(model, "__name__", str(model))

        if name == "ApprovalRequestRecord":
            q.all.return_value = [(tid, cnt) for tid, cnt in pending.items()]
        elif name == "JobRecord":
            def all_side_effect():
                if q.filter.call_args_list and any(
                    "manual_review" in str(c) for c in q.filter.call_args_list
                ):
                    return [(tid, cnt) for tid, cnt in manual.items()]
                return [(tid, cnt) for tid, cnt in jobs_30d.items()]

            q.all.side_effect = all_side_effect
            q.count.return_value = 0
        elif name == "OAuthCredentialRecord":
            q.all.return_value = []
        elif name == "IntegrationEvent":
            q.all.return_value = []
        elif name == "AuditEventRecord":
            q.all.return_value = [(tid, datetime.now(timezone.utc)) for tid in pending.keys()]
        else:
            q.all.return_value = []
        return q

    db.query.side_effect = query_side_effect


class TestNormalizeTenantStatus:
    def test_active(self):
        assert _normalize_tenant_status("active") == "active"

    def test_inactive(self):
        assert _normalize_tenant_status("inactive") == "inactive"

    def test_unknown_for_missing(self):
        assert _normalize_tenant_status(None) == "unknown"


class TestDeriveTenantHealth:
    def test_paused_only_when_demo_mode(self):
        result = _derive_tenant_health("high", automation_paused=True, scheduler_paused=False)
        assert result["level"] == "paused"

    def test_inactive_status_does_not_imply_paused(self):
        result = _derive_tenant_health("high", automation_paused=False, scheduler_paused=False)
        assert result["level"] == "failed"

    def test_healthy_when_no_issues(self):
        result = _derive_tenant_health(None, automation_paused=False, scheduler_paused=False)
        assert result["level"] == "healthy"


class TestIntegrationsSummary:
    def test_visma_unknown_without_signals(self):
        summary = _integrations_summary_for_tenant("T_A", [], set(), {})
        assert summary["visma"] == "unknown"
        assert summary["google_sheets"] == "unknown"

    def test_gmail_issue_does_not_change_visma(self):
        triage = [{
            "tenant_id": "T_A",
            "area": "integration",
            "title": "Gmail integration is error",
            "severity": "critical",
        }]
        summary = _integrations_summary_for_tenant("T_A", triage, set(), {})
        assert summary["google_mail"] == "failed"
        assert summary["visma"] == "unknown"


class TestListAdminTenants:
    def _run(self, tenants=None, triage_rows=None, **kwargs):
        tenants = tenants if tenants is not None else [_tenant()]
        triage_rows = triage_rows if triage_rows is not None else []
        db = _mock_db()
        _batch_query_side_effect(db)

        with patch(
            "app.admin.tenant_directory.TenantConfigRepository.list_all",
            return_value=tenants,
        ), patch(
            "app.admin.tenant_directory.TenantConfigRepository.to_dict",
            side_effect=_to_dict,
        ), patch(
            "app.admin.tenant_directory.collect_all_triage_rows",
            return_value=triage_rows,
        ), patch(
            "app.admin.tenant_directory._batch_count_by_tenant",
            return_value={},
        ), patch(
            "app.admin.tenant_directory._batch_max_job_activity",
            return_value={},
        ), patch(
            "app.admin.tenant_directory._batch_max_created_at",
            return_value={},
        ), patch(
            "app.admin.tenant_directory._batch_oauth_providers",
            return_value={},
        ), patch(
            "app.admin.tenant_directory._batch_integration_event_stats",
            return_value={},
        ):
            return list_admin_tenants(
                db,
                app_settings=_settings(),
                **kwargs,
            )

    def test_list_shape_and_null_fields(self):
        result = self._run()
        assert "items" in result
        assert "total" in result
        item = result["items"][0]
        assert item["package"] is None
        assert item["operator_owner"] is None
        assert item["tenant_status"] == "active"
        assert "enabled_modules" in item
        assert "integrations_summary" in item
        assert "jobs_last_30d" in item

    def test_search_filter(self):
        tenants = [
            _tenant(tenant_id="T_A", name="Alpha"),
            _tenant(tenant_id="T_B", name="Beta Corp"),
        ]
        result = self._run(tenants=tenants, search="beta")
        assert result["total"] == 1
        assert result["items"][0]["tenant_id"] == "T_B"

    def test_health_filter_paused(self):
        tenants = [_tenant(settings={"automation": {"demo_mode": True}})]
        result = self._run(tenants=tenants, health="paused")
        assert result["total"] == 1
        assert result["items"][0]["health"]["level"] == "paused"

    def test_inactive_without_pause_not_health_paused(self):
        tenants = [_tenant(status="inactive")]
        result = self._run(tenants=tenants, health="paused")
        assert result["total"] == 0

    def test_no_secrets(self):
        result = self._run()
        blob = json.dumps(result)
        for secret in ("api_key", "access_token", "refresh_token", "key_hash"):
            assert secret not in blob


class TestGetTenantDetail:
    def test_returns_none_for_missing(self):
        db = _mock_db()
        with patch(
            "app.admin.tenant_directory.TenantConfigRepository.get",
            return_value=None,
        ):
            assert get_tenant_detail(db, "MISSING", app_settings=_settings()) is None

    def test_recent_errors_exclude_integration_area(self):
        tenant = _tenant()
        db = _mock_db()
        pipeline_row = {
            "tenant_id": "T_A",
            "tenant_name": "Acme",
            "severity": "high",
            "area": "pipeline",
            "title": "Failed lead job",
            "detail": "boom",
            "job_id": "job-1",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "recommended_action": "Review",
        }
        with patch(
            "app.admin.tenant_directory.TenantConfigRepository.get",
            return_value=tenant,
        ), patch(
            "app.admin.tenant_directory.TenantConfigRepository.to_dict",
            side_effect=_to_dict,
        ), patch(
            "app.admin.tenant_directory._build_tenant_triage",
            return_value=[pipeline_row],
        ), patch(
            "app.admin.tenant_directory.get_integration_health",
            return_value={"systems": {
                "google_mail": {"status": "healthy"},
                "monday": {"status": "not_configured"},
                "fortnox": {"status": "not_configured"},
            }},
        ), patch(
            "app.admin.tenant_directory.JobRepository.list_jobs_for_tenant",
            return_value=[],
        ), patch(
            "app.admin.tenant_directory.JobRepository.count_jobs_for_tenant",
            return_value=0,
        ), patch(
            "app.admin.tenant_directory._count_jobs_last_30d",
            return_value=0,
        ), patch(
            "app.admin.tenant_directory.ApprovalRequestRepository.list_pending_for_tenant",
            return_value=[],
        ), patch(
            "app.admin.tenant_directory.ApprovalRequestRepository.count_pending_for_tenant",
            return_value=0,
        ), patch(
            "app.admin.tenant_directory.list_unresolved_manual_review_jobs",
            return_value=([], 0),
        ), patch(
            "app.admin.tenant_directory._tenant_usage_summary",
            return_value={
                "jobs_created": 0,
                "jobs_completed": 0,
                "pending_approvals": 0,
                "blocked_flows": 0,
                "dispatches_total": 0,
                "dispatches_successful": 0,
                "dispatches_failed": 0,
                "automation_rate_percent": 0,
                "time_saved_hours": 0.0,
            },
        ), patch(
            "app.admin.tenant_directory.AuditRepository.list_events_for_tenant",
            return_value=[],
        ), patch(
            "app.admin.tenant_directory.AuditRepository.count_events_for_tenant",
            return_value=0,
        ), patch(
            "app.admin.tenant_directory._failed_pipeline_signals",
            return_value=[pipeline_row],
        ), patch(
            "app.admin.tenant_directory._stale_approval_signals",
            return_value=[],
        ), patch(
            "app.admin.tenant_directory._failed_integration_event_signals",
            return_value=[],
        ), patch(
            "app.admin.tenant_directory._failed_scheduler_signals",
            return_value=[],
        ), patch(
            "app.admin.tenant_directory._tenant_visma_sheets_detail",
            side_effect=lambda db, tid, itype, prov: {
                "status": "unknown",
                "description": "none",
                "recommended_action": None,
                "data_source": "oauth_credentials_and_integration_event_log",
                "last_success_at": None,
                "last_error_at": None,
            },
        ):
            result = get_tenant_detail(db, "T_A", app_settings=_settings())
        assert result is not None
        assert all(item["category"] != "integration" for item in result["recent_errors"])
        TenantDetailResponse.model_validate(result)

    def test_manual_review_total_independent_of_recent_limit(self):
        tenant = _tenant()
        db = _mock_db()
        with patch(
            "app.admin.tenant_directory.TenantConfigRepository.get",
            return_value=tenant,
        ), patch(
            "app.admin.tenant_directory.TenantConfigRepository.to_dict",
            side_effect=_to_dict,
        ), patch(
            "app.admin.tenant_directory._build_tenant_triage",
            return_value=[],
        ), patch(
            "app.admin.tenant_directory.get_integration_health",
            return_value={"systems": {}},
        ), patch(
            "app.admin.tenant_directory.JobRepository.list_jobs_for_tenant",
            return_value=[],
        ), patch(
            "app.admin.tenant_directory.JobRepository.count_jobs_for_tenant",
            return_value=5,
        ), patch(
            "app.admin.tenant_directory._count_jobs_last_30d",
            return_value=2,
        ), patch(
            "app.admin.tenant_directory.ApprovalRequestRepository.list_pending_for_tenant",
            return_value=[],
        ), patch(
            "app.admin.tenant_directory.ApprovalRequestRepository.count_pending_for_tenant",
            return_value=3,
        ), patch(
            "app.admin.tenant_directory.list_unresolved_manual_review_jobs",
            return_value=([{"job_id": "j1", "job_type": "lead", "status": "manual_review", "unresolved": True}], 7),
        ), patch(
            "app.admin.tenant_directory._tenant_usage_summary",
            return_value={
                "jobs_created": 0, "jobs_completed": 0, "pending_approvals": 0,
                "blocked_flows": 0, "dispatches_total": 0, "dispatches_successful": 0,
                "dispatches_failed": 0, "automation_rate_percent": 0, "time_saved_hours": 0.0,
            },
        ), patch(
            "app.admin.tenant_directory.AuditRepository.list_events_for_tenant",
            return_value=[],
        ), patch(
            "app.admin.tenant_directory.AuditRepository.count_events_for_tenant",
            return_value=11,
        ), patch(
            "app.admin.tenant_directory._build_recent_errors",
            return_value=[],
        ), patch(
            "app.admin.tenant_directory._tenant_visma_sheets_detail",
            return_value={
                "status": "unknown", "description": "", "recommended_action": None,
                "data_source": "oauth", "last_success_at": None, "last_error_at": None,
            },
        ):
            result = get_tenant_detail(db, "T_A", app_settings=_settings())
        assert result["manual_review"]["total"] == 7
        assert len(result["manual_review"]["recent"]) == 1
        assert result["jobs"]["total"] == 5
        assert result["audit"]["total"] == 11


class TestTenantDirectoryHttp:
    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_list_401_without_auth(self, client):
        response = client.get("/admin/tenants")
        assert response.status_code == 401

    def test_detail_401_without_auth(self, client):
        response = client.get("/admin/tenants/T_A/overview")
        assert response.status_code == 401

    def test_list_200_with_admin_key(self, client):
        with patch("app.core.admin_auth.get_settings", return_value=_settings()), patch(
            "app.admin.tenant_directory.list_admin_tenants",
            return_value={"items": [], "total": 0},
        ):
            response = client.get(
                "/admin/tenants",
                headers={"X-Admin-API-Key": "test-admin-key"},
            )
        assert response.status_code == 200

    def test_detail_404_unknown_tenant(self, client):
        with patch("app.core.admin_auth.get_settings", return_value=_settings()), patch(
            "app.admin.tenant_directory.get_tenant_detail",
            return_value=None,
        ):
            response = client.get(
                "/admin/tenants/T_MISSING/overview",
                headers={"X-Admin-API-Key": "test-admin-key"},
            )
        assert response.status_code == 404


class TestListPerformanceSmoke:
    def test_fifty_tenants_under_two_seconds(self):
        tenants = [_tenant(tenant_id=f"T_{i}", name=f"Tenant {i}") for i in range(50)]
        db = _mock_db()
        _batch_query_side_effect(db)
        start = time.perf_counter()
        with patch(
            "app.admin.tenant_directory.TenantConfigRepository.list_all",
            return_value=tenants,
        ), patch(
            "app.admin.tenant_directory.TenantConfigRepository.to_dict",
            side_effect=_to_dict,
        ), patch(
            "app.admin.tenant_directory.collect_all_triage_rows",
            return_value=[],
        ), patch(
            "app.admin.tenant_directory._batch_count_by_tenant",
            return_value={},
        ), patch(
            "app.admin.tenant_directory._batch_max_job_activity",
            return_value={},
        ), patch(
            "app.admin.tenant_directory._batch_max_created_at",
            return_value={},
        ), patch(
            "app.admin.tenant_directory._batch_oauth_providers",
            return_value={},
        ), patch(
            "app.admin.tenant_directory._batch_integration_event_stats",
            return_value={},
        ):
            list_admin_tenants(db, app_settings=_settings())
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0
