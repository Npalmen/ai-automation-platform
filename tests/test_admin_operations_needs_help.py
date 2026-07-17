"""
Tests for GET /admin/operations/needs-help (Kapitel 4 — Behöver hjälp).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.admin.operations_needs_help import get_needs_help_item, list_needs_help_queue
from app.admin.operations_needs_help_schemas import NeedsHelpItemDetail, NeedsHelpQueueResponse
from app.admin.operations_triage import _row


def _settings(**kwargs):
    defaults = {"ADMIN_API_KEY": "test-admin-key", "APP_NAME": "Test"}
    defaults.update(kwargs)
    return SimpleNamespace(**kwargs)


def _mock_db():
    from unittest.mock import MagicMock
    db = MagicMock()
    return db


def _sample_rows():
    return [
        _row(
            tenant_id="T_A",
            tenant_name="Acme",
            severity="critical",
            area="integration_reconciliation",
            title="Reconcile visma",
            detail="Needs reconcile",
            source_id="integration_event:1",
            source_type="integration_event",
            created_at="2026-01-01T00:00:00+00:00",
            retryable="no",
            external_impact="yes",
            runbook_ref="visma_write_safety",
        ),
        _row(
            tenant_id="T_B",
            tenant_name="Beta",
            severity="high",
            area="pipeline",
            title="Failed job",
            detail="Error",
            job_id="job-b",
            source_id="job:job-b",
            source_type="job",
            created_at="2026-01-02T00:00:00+00:00",
            retryable="unknown",
            external_impact="unknown",
            runbook_ref="pilot_support",
        ),
        _row(
            tenant_id="T_A",
            tenant_name="Acme",
            severity="medium",
            area="tenant_config",
            title="Missing config",
            detail="Empty",
            source_id="tenant_config:T_A",
            source_type="tenant_config",
            created_at="2026-01-03T00:00:00+00:00",
            retryable="not_applicable",
            external_impact="no",
            runbook_ref="tenant_configuration",
        ),
    ]


class TestListNeedsHelpQueue:
    def test_response_shape(self):
        db = _mock_db()
        with patch(
            "app.admin.operations_needs_help.collect_all_triage_rows",
            return_value=_sample_rows(),
        ):
            result = list_needs_help_queue(db=db, app_settings=_settings())
        NeedsHelpQueueResponse.model_validate(result)
        assert result["summary"]["critical"] == 1
        assert result["summary"]["failed"] == 1
        assert result["summary"]["warning"] == 1
        assert result["summary"]["affected_tenants"] == 2

    def test_summary_reflects_filtered_set(self):
        db = _mock_db()
        with patch(
            "app.admin.operations_needs_help.collect_all_triage_rows",
            return_value=_sample_rows(),
        ):
            all_result = list_needs_help_queue(db=db, app_settings=_settings())
            filtered = list_needs_help_queue(
                db=db,
                app_settings=_settings(),
                tenant_id="T_B",
            )
        assert filtered["total"] == 1
        assert filtered["summary"]["failed"] == 1
        assert filtered["summary"]["critical"] == 0
        assert all_result["total"] == 3

    def test_search_matches_title(self):
        db = _mock_db()
        with patch(
            "app.admin.operations_needs_help.collect_all_triage_rows",
            return_value=_sample_rows(),
        ):
            result = list_needs_help_queue(
                db=db, app_settings=_settings(), search="Failed job",
            )
        assert result["total"] == 1
        assert result["items"][0]["tenant_id"] == "T_B"

    def test_category_filter(self):
        db = _mock_db()
        with patch(
            "app.admin.operations_needs_help.collect_all_triage_rows",
            return_value=_sample_rows(),
        ):
            result = list_needs_help_queue(
                db=db, app_settings=_settings(), category="tenant_config",
            )
        assert result["total"] == 1
        assert result["items"][0]["severity"] == "warning"

    def test_pagination(self):
        db = _mock_db()
        with patch(
            "app.admin.operations_needs_help.collect_all_triage_rows",
            return_value=_sample_rows(),
        ):
            result = list_needs_help_queue(
                db=db, app_settings=_settings(), limit=1, offset=1,
            )
        assert result["total"] == 3
        assert len(result["items"]) == 1
        assert result["offset"] == 1


class TestGetNeedsHelpItem:
    def test_found_with_tenant_scope(self):
        db = _mock_db()
        rows = _sample_rows()
        with patch(
            "app.admin.operations_needs_help._build_tenant_triage",
            return_value=rows,
        ), patch(
            "app.admin.operations_needs_help.TenantConfigRepository.get",
            return_value=SimpleNamespace(tenant_id="T_A", name="Acme"),
        ), patch(
            "app.admin.operations_triage.dedupe_and_normalize_signals",
            side_effect=lambda r: r,
        ):
            result = get_needs_help_item(
                db,
                "integration_event:1",
                app_settings=_settings(),
                tenant_id="T_A",
            )
        assert result is not None
        NeedsHelpItemDetail.model_validate(result)
        assert result["runbook"]["id"] == "visma_write_safety"

    def test_not_found_returns_none(self):
        db = _mock_db()
        with patch(
            "app.admin.operations_needs_help.collect_all_triage_rows",
            return_value=_sample_rows(),
        ):
            result = get_needs_help_item(
                db, "missing-id", app_settings=_settings(),
            )
        assert result is None


class TestNeedsHelpIncidentLinking:
    def test_detail_includes_recommended_incident_action(self):
        db = _mock_db()
        rows = _sample_rows()
        with patch(
            "app.admin.operations_needs_help._build_tenant_triage",
            return_value=rows,
        ), patch(
            "app.admin.operations_needs_help.TenantConfigRepository.get",
            return_value=SimpleNamespace(tenant_id="T_A", name="Acme"),
        ), patch(
            "app.admin.operations_triage.dedupe_and_normalize_signals",
            side_effect=lambda r: r,
        ), patch(
            "app.admin.operations_needs_help.find_linked_incidents",
            return_value=SimpleNamespace(
                model_dump=lambda: {"open": [], "closed": []},
            ),
        ):
            result = get_needs_help_item(
                db,
                "integration_event:1",
                app_settings=_settings(),
                tenant_id="T_A",
            )
        assert result is not None
        detail = NeedsHelpItemDetail.model_validate(result)
        assert detail.recommended_incident_action is not None
        assert detail.recommended_incident_action.signal_id == "integration_event:1"
        assert detail.linked_incidents.open == []


class TestNeedsHelpEndpoint:
    def test_missing_admin_key_returns_401(self):
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/admin/operations/needs-help")
        assert r.status_code == 401

    def test_valid_admin_key_returns_200(self):
        from fastapi.testclient import TestClient
        from app.main import app

        key = "test-admin-key-needs-help"
        s = _settings(ADMIN_API_KEY=key)
        client = TestClient(app, raise_server_exceptions=False)
        with patch("app.core.admin_auth.get_settings", return_value=s):
            with patch(
                "app.admin.operations_needs_help.collect_all_triage_rows",
                return_value=[],
            ):
                r = client.get(
                    "/admin/operations/needs-help",
                    headers={"X-Admin-API-Key": key},
                )
        assert r.status_code == 200
        body = r.json()
        assert "summary" in body
        assert "items" in body

    def test_detail_not_found_returns_404(self):
        from fastapi.testclient import TestClient
        from app.main import app

        key = "test-admin-key-needs-help"
        s = _settings(ADMIN_API_KEY=key)
        client = TestClient(app, raise_server_exceptions=False)
        with patch("app.core.admin_auth.get_settings", return_value=s):
            with patch(
                "app.admin.operations_needs_help.collect_all_triage_rows",
                return_value=[],
            ):
                r = client.get(
                    "/admin/operations/needs-help/missing-id",
                    headers={"X-Admin-API-Key": key},
                )
        assert r.status_code == 404
