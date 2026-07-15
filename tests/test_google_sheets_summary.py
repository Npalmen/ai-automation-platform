"""Focused tests for Google Sheets Sammanfattning summary refresh."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_db
from app.core.auth import get_verified_tenant
from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.domain.workflows.statuses import JobStatus
from app.integrations.google.sheets_client import MockGoogleSheetsClient
from app.integrations.google.sheets_summary_mapper import (
    SUMMARY_CLEAR_RANGE,
    TAB_SUMMARY,
    build_priority_row,
    build_summary_matrix,
    build_summary_sheet_data,
    concise_operational_summary,
)
from app.main import app

_TENANT_ID = "T_TEST_SHEETS"
_OTHER_TENANT = "T_OTHER"
_SPREADSHEET_ID = "1abc_spreadsheet_xyz"
_LONG_BODY = "Rad ett.\n" + ("Detta är en mycket lång rad med detaljer. " * 40)


def _make_job(
    *,
    job_type: JobType = JobType.CUSTOMER_INQUIRY,
    status: JobStatus = JobStatus.AWAITING_APPROVAL,
    job_id: str | None = None,
    tenant_id: str = _TENANT_ID,
    input_data: dict | None = None,
    processor_history: list | None = None,
    result: dict | None = None,
) -> Job:
    now = datetime.now(timezone.utc)
    return Job(
        job_id=job_id or f"job_{uuid.uuid4().hex[:8]}",
        tenant_id=tenant_id,
        job_type=job_type,
        status=status,
        input_data=input_data
        or {
            "subject": "Kort ämnesrad",
            "message_text": "Kort meddelande.",
            "sender": {"name": "Test User", "email": "test@example.com"},
            "source": {"system": "gmail", "message_id": "msg-1"},
        },
        result=result,
        processor_history=processor_history or [],
        created_at=now,
        updated_at=now,
    )


def _manual_review_job() -> Job:
    return _make_job(
        job_type=JobType.CUSTOMER_INQUIRY,
        status=JobStatus.MANUAL_REVIEW,
        job_id="job_manual_001",
        input_data={
            "subject": "Manuell granskning krävs",
            "message_text": _LONG_BODY,
            "sender": {"name": "Erik", "email": "erik@example.com"},
            "source": {"system": "gmail", "message_id": "msg-manual"},
        },
        result={
            "manual_review_handoff": {
                "manual_review_reason": "Oklar garantifråga",
                "manual_review_reason_codes": ["warranty_unclear"],
            }
        },
        processor_history=[
            {
                "processor": "support_analyzer_processor",
                "result": {
                    "status": "completed",
                    "payload": {
                        "support_analysis": {"ticket_type": "warranty"},
                        "support_priority": {
                            "score": 80,
                            "category": "critical",
                            "reasons": ["requires_human"],
                        },
                        "support_next_action": {
                            "action": "escalate",
                            "reason": "Kontakta kunden",
                            "requires_approval": True,
                        },
                    },
                },
            }
        ],
    )


def _override_deps(tenant_id: str, db: MagicMock):
    class _CM:
        def __enter__(self):
            app.dependency_overrides[get_verified_tenant] = lambda: tenant_id
            app.dependency_overrides[get_db] = lambda: db
            return self

        def __exit__(self, *_):
            app.dependency_overrides.pop(get_verified_tenant, None)
            app.dependency_overrides.pop(get_db, None)

    return _CM()


def _make_db() -> MagicMock:
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    return db


def _make_tenant_record(allowed: list) -> MagicMock:
    record = MagicMock()
    record.allowed_integrations = allowed
    return record


def _sample_report() -> dict:
    return {
        "tenant_id": _TENANT_ID,
        "period_hours": 24,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": {
            "new_leads": 2,
            "inquiries_needing_response": 3,
            "unresolved_manual_review": 1,
            "pending_approvals": 4,
            "internal_handoffs_sent": 2,
            "risk_review_required": 1,
            "leads_ready_for_quote": 0,
            "leads_waiting_for_customer": 0,
            "invoice_items_needing_action": 0,
        },
        "top_priorities": [{"job_id": "job_manual_001", "action_type": "risk_review"}],
    }


class TestConciseOperationalSummary:
    def test_prefers_subject_over_email_body(self):
        job = _make_job(
            input_data={
                "subject": "Kort ämnesrad",
                "message_text": _LONG_BODY,
                "sender": {"name": "A"},
            }
        )
        summary = concise_operational_summary(job)
        assert summary == "Kort ämnesrad"
        assert _LONG_BODY not in summary

    def test_long_subject_is_shortened(self):
        job = _make_job(
            input_data={
                "subject": "X" * 200,
                "message_text": "ignored",
                "sender": {"name": "A"},
            }
        )
        summary = concise_operational_summary(job)
        assert len(summary) <= 120
        assert summary.endswith("…")

    def test_without_subject_uses_first_line_not_full_body(self):
        job = _make_job(
            input_data={
                "subject": "",
                "message_text": _LONG_BODY,
                "sender": {"name": "A"},
            }
        )
        summary = concise_operational_summary(job)
        assert "Rad ett." in summary
        assert len(summary) <= 120
        assert _LONG_BODY not in summary


class TestSummaryMatrix:
    def test_counts_in_matrix(self):
        matrix = build_summary_matrix(_sample_report(), [_manual_review_job()])
        flat = "\n".join(str(cell) for row in matrix for cell in row)
        assert "Totalt antal aktuella ärenden" in flat
        assert "Nya leads" in flat
        assert "Kundärenden som behöver svar" in flat
        assert "Manuell granskning" in flat
        assert "Väntande godkännanden" in flat
        assert "Interna handoffs skickade" in flat

        count_rows = {
            row[0]: row[1]
            for row in matrix
            if row and row[0] in {
                "Nya leads",
                "Manuell granskning",
                "Väntande godkännanden",
                "Interna handoffs skickade",
            }
        }
        assert count_rows["Nya leads"] == 2
        assert count_rows["Manuell granskning"] == 1
        assert count_rows["Väntande godkännanden"] == 4
        assert count_rows["Interna handoffs skickade"] == 2

    def test_priority_row_has_no_raw_dict_values(self):
        row = build_priority_row(_manual_review_job())
        assert len(row) == 7
        for cell in row:
            assert not isinstance(cell, (dict, list))
            assert "{" not in str(cell)
            assert "[" not in str(cell)

    def test_manual_review_represented_in_priority_section(self):
        job = _manual_review_job()
        matrix = build_summary_matrix(_sample_report(), [job])
        data_rows = [row for row in matrix if row and row[-1] == job.job_id]
        assert len(data_rows) == 1
        assert data_rows[0][0] == "manual_review"
        assert "critical" in str(data_rows[0][1]).lower()
        assert _LONG_BODY not in str(data_rows[0][2])


class TestBuildSummarySheetData:
    def test_uses_daily_report_counts(self):
        db = MagicMock()
        recent_job = _manual_review_job()
        report = _sample_report()

        with patch(
            "app.integrations.google.sheets_summary_mapper.generate_daily_report",
            return_value=report,
        ), patch(
            "app.integrations.google.sheets_summary_mapper.JobRepository.list_jobs",
            return_value=[recent_job],
        ):
            data = build_summary_sheet_data(db, _TENANT_ID, since_hours=24)

        assert data["tab"] == TAB_SUMMARY
        assert data["clear_range"] == SUMMARY_CLEAR_RANGE
        assert recent_job.job_id in data["priority_job_ids"]


class TestRefreshSummaryEndpoint:
    def test_blocked_when_integration_not_allowed(self):
        db = _make_db()
        with _override_deps(_TENANT_ID, db), patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=_make_tenant_record(["visma"]),
        ):
            response = TestClient(app).post(
                "/integrations/google-sheets/refresh-summary",
                json={"since_hours": 24},
                headers={"X-Tenant-ID": _TENANT_ID},
            )
        assert response.status_code == 200
        assert response.json()["status"] == "blocked"
        assert response.json()["reason"] == "integration_not_allowed"

    def test_blocked_when_spreadsheet_missing(self):
        db = _make_db()
        with _override_deps(_TENANT_ID, db), patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=_make_tenant_record(["google_sheets"]),
        ), patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value={"google_sheets": {}},
        ):
            response = TestClient(app).post(
                "/integrations/google-sheets/refresh-summary",
                json={},
                headers={"X-Tenant-ID": _TENANT_ID},
            )
        assert response.json()["reason"] == "configuration_missing"

    def test_refresh_replaces_range_not_append(self):
        db = _make_db()
        mock_client = MockGoogleSheetsClient()
        matrix = build_summary_matrix(_sample_report(), [_manual_review_job()])

        with _override_deps(_TENANT_ID, db), patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=_make_tenant_record(["google_sheets"]),
        ), patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value={"google_sheets": {"spreadsheet_id": _SPREADSHEET_ID}},
        ), patch(
            "app.integrations.google.sheets_auth.resolve_google_sheets_access_token",
            return_value="token-abc",
        ), patch(
            "app.integrations.google.sheets_client.GoogleSheetsClient",
            return_value=mock_client,
        ), patch(
            "app.integrations.google.sheets_summary_mapper.build_summary_sheet_data",
            return_value={
                "matrix": matrix,
                "write_range": f"{TAB_SUMMARY}!A1",
                "priority_job_ids": ["job_manual_001"],
                "report": _sample_report(),
                "tab": TAB_SUMMARY,
                "clear_range": SUMMARY_CLEAR_RANGE,
            },
        ):
            response = TestClient(app).post(
                "/integrations/google-sheets/refresh-summary",
                json={"since_hours": 24},
                headers={"X-Tenant-ID": _TENANT_ID},
            )

        body = response.json()
        assert body["status"] == "refreshed"
        assert body["update_mode"] == "replace_range"
        assert mock_client.clear_calls
        assert mock_client.update_calls
        assert not mock_client.calls
        assert mock_client.clear_calls[0]["range_notation"] == SUMMARY_CLEAR_RANGE
        assert mock_client.update_calls[0]["values"] == matrix
        assert mock_client.ensure_tab_calls[0]["tab_name"] == TAB_SUMMARY

    def test_refresh_does_not_touch_gmail(self):
        db = _make_db()
        with _override_deps(_TENANT_ID, db), patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
            return_value=_make_tenant_record(["google_sheets"]),
        ), patch(
            "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
            return_value={"google_sheets": {"spreadsheet_id": _SPREADSHEET_ID}},
        ), patch(
            "app.integrations.google.sheets_auth.resolve_google_sheets_access_token",
            return_value="token-abc",
        ), patch(
            "app.integrations.google.sheets_client.GoogleSheetsClient",
            return_value=MockGoogleSheetsClient(),
        ), patch(
            "app.integrations.google.sheets_summary_mapper.build_summary_sheet_data",
            return_value={
                "matrix": [["Senast uppdaterad"]],
                "write_range": f"{TAB_SUMMARY}!A1",
                "priority_job_ids": [],
                "report": _sample_report(),
                "tab": TAB_SUMMARY,
                "clear_range": SUMMARY_CLEAR_RANGE,
            },
        ), patch(
            "app.integrations.factory.get_integration_adapter",
        ) as gmail_adapter:
            response = TestClient(app).post(
                "/integrations/google-sheets/refresh-summary",
                json={},
                headers={"X-Tenant-ID": _TENANT_ID},
            )
        assert response.json()["status"] == "refreshed"
        gmail_adapter.assert_not_called()

    def test_tenant_scoped_summary_build(self):
        db = _make_db()
        with patch(
            "app.integrations.google.sheets_summary_mapper.generate_daily_report",
            return_value=_sample_report(),
        ) as gen_report, patch(
            "app.integrations.google.sheets_summary_mapper.JobRepository.list_jobs",
            return_value=[],
        ):
            build_summary_sheet_data(db, _OTHER_TENANT, since_hours=12)
            gen_report.assert_called_once_with(db, tenant_id=_OTHER_TENANT, since_hours=12)
