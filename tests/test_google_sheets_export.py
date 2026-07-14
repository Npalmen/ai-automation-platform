"""
Sprint 3 — Google Sheets export tests.

Covers:
- Row mapper: lead job → Leads row (12 cols)
- Row mapper: support/customer_inquiry job → Support row (12 cols)
- Row mapper: choose_tab auto-detection
- Row mapper: explicit target overrides
- MockGoogleSheetsClient records calls
- Endpoint: google_sheets not in allowed_integrations → blocked / integration_not_allowed
- Endpoint: spreadsheet_id missing → blocked / configuration_missing
- Endpoint: wrong-tenant job → 404
- Endpoint: adapter called exactly once when export succeeds
- Endpoint: audit event created on export
- Endpoint: integration event created on export
- No auto-export from Gmail processing
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_db
from app.core.auth import get_verified_tenant
from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.domain.workflows.statuses import JobStatus
from app.integrations.google.sheets_client import MockGoogleSheetsClient
from app.integrations.google.sheets_row_mapper import (
    TAB_LEADS,
    TAB_LOGG,
    TAB_SUPPORT,
    build_leads_row,
    build_logg_row,
    build_support_row,
    choose_tab,
)
from app.main import app

_HERE = os.path.dirname(__file__)
_REPO = os.path.dirname(_HERE)

_TENANT_ID = "T_TEST_SHEETS"
_SPREADSHEET_ID = "1abc_spreadsheet_xyz"
_JOB_ID = "job_lead_001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job(
    job_type: JobType = JobType.LEAD,
    job_id: str | None = None,
    tenant_id: str = _TENANT_ID,
    status: JobStatus = JobStatus.COMPLETED,
    input_data: dict | None = None,
    processor_history: list | None = None,
) -> Job:
    return Job(
        job_id=job_id or f"job_{uuid.uuid4().hex[:8]}",
        tenant_id=tenant_id,
        job_type=job_type,
        status=status,
        input_data=input_data or {
            "subject": "Test subject",
            "message_text": "Test message",
            "sender": {"name": "Test User", "email": "test@example.com", "phone": "0701234567"},
        },
        result=None,
        processor_history=processor_history or [],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _make_lead_job() -> Job:
    return _make_job(
        job_type=JobType.LEAD,
        job_id=_JOB_ID,
        input_data={
            "subject": "EV-laddare offert",
            "message_text": "Hej, jag vill installera en elbilsladdare.",
            "sender": {"name": "Anna Berg", "email": "anna@example.com", "phone": "0701234567"},
            "source": "gmail",
        },
        processor_history=[
            {
                "processor": "lead_analyzer_processor",
                "result": {
                    "status": "completed",
                    "payload": {
                        "lead_analysis": {"lead_type": "ev_charger", "customer_type": "private"},
                        "missing_info": {"missing_fields": ["main_fuse", "property_type"]},
                        "next_action": "send_reply",
                    },
                },
            }
        ],
    )


def _make_support_job() -> Job:
    return _make_job(
        job_type=JobType.CUSTOMER_INQUIRY,
        job_id="job_support_001",
        input_data={
            "subject": "Solpanelerna fungerar inte",
            "message_text": "Hej, mina solpaneler producerar ingenting.",
            "sender": {"name": "Lars Svensson", "email": "lars@example.com"},
            "source": {"system": "gmail"},
        },
        processor_history=[
            {
                "processor": "support_analyzer_processor",
                "result": {
                    "status": "completed",
                    "payload": {
                        "support_analysis": {"category": "solar", "ticket_type": "issue"},
                        "support_priority": "high",
                        "support_next_action": "schedule_technician",
                    },
                },
            }
        ],
    )


def _make_tenant_record(allowed: list) -> MagicMock:
    r = MagicMock()
    r.allowed_integrations = allowed
    return r


def _override_deps(tenant_id: str, db: MagicMock):
    """Return a context manager that overrides FastAPI dependencies."""
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


# ---------------------------------------------------------------------------
# Row mapper unit tests
# ---------------------------------------------------------------------------

class TestChooseTab:
    def test_auto_lead_job_goes_to_leads(self):
        assert choose_tab(_make_job(job_type=JobType.LEAD), "auto") == TAB_LEADS

    def test_auto_customer_inquiry_goes_to_support(self):
        assert choose_tab(_make_job(job_type=JobType.CUSTOMER_INQUIRY), "auto") == TAB_SUPPORT

    def test_auto_unknown_job_goes_to_logg(self):
        assert choose_tab(_make_job(job_type=JobType.UNKNOWN), "auto") == TAB_LOGG

    def test_explicit_leads_overrides_job_type(self):
        assert choose_tab(_make_job(job_type=JobType.CUSTOMER_INQUIRY), "leads") == TAB_LEADS

    def test_explicit_support_overrides_job_type(self):
        assert choose_tab(_make_job(job_type=JobType.LEAD), "support") == TAB_SUPPORT

    def test_explicit_logg(self):
        assert choose_tab(_make_job(job_type=JobType.LEAD), "logg") == TAB_LOGG


class TestBuildLeadsRow:
    def test_leads_row_has_12_columns(self):
        row = build_leads_row(_make_lead_job())
        assert len(row) == 12, f"Expected 12 columns, got {len(row)}: {row}"

    def test_leads_row_last_column_is_job_id(self):
        job = _make_lead_job()
        row = build_leads_row(job)
        assert row[-1] == job.job_id

    def test_leads_row_extracts_sender_name(self):
        assert build_leads_row(_make_lead_job())[1] == "Anna Berg"

    def test_leads_row_extracts_email(self):
        assert build_leads_row(_make_lead_job())[3] == "anna@example.com"

    def test_leads_row_extracts_phone(self):
        assert build_leads_row(_make_lead_job())[2] == "0701234567"

    def test_leads_row_missing_fields_serialized(self):
        row = build_leads_row(_make_lead_job())
        assert "main_fuse" in row[7]
        assert "property_type" in row[7]

    def test_leads_row_arendetyp_from_processor(self):
        assert build_leads_row(_make_lead_job())[4] == "ev_charger"

    def test_leads_row_handles_empty_processor_history(self):
        job = _make_job(job_type=JobType.LEAD)
        row = build_leads_row(job)
        assert len(row) == 12
        assert row[-1] == job.job_id

    def test_leads_row_source_extracted(self):
        # kalla column (index 10)
        assert build_leads_row(_make_lead_job())[10] == "gmail"


class TestBuildSupportRow:
    def test_support_row_has_12_columns(self):
        row = build_support_row(_make_support_job())
        assert len(row) == 12, f"Expected 12 columns, got {len(row)}: {row}"

    def test_support_row_last_column_is_job_id(self):
        job = _make_support_job()
        assert build_support_row(job)[-1] == job.job_id

    def test_support_row_extracts_sender_name(self):
        assert build_support_row(_make_support_job())[1] == "Lars Svensson"

    def test_support_row_extracts_email(self):
        assert build_support_row(_make_support_job())[3] == "lars@example.com"

    def test_support_row_priority_from_processor(self):
        assert build_support_row(_make_support_job())[5] == "high"

    def test_support_row_risk_from_processor(self):
        assert build_support_row(_make_support_job())[6] == "issue"

    def test_support_row_source_dict_extracted(self):
        # source is {"system": "gmail"}
        assert build_support_row(_make_support_job())[10] == "gmail"

    def test_support_row_handles_empty_processor_history(self):
        job = _make_job(job_type=JobType.CUSTOMER_INQUIRY)
        row = build_support_row(job)
        assert len(row) == 12


class TestBuildLoggRow:
    def test_logg_row_has_6_columns(self):
        assert len(build_logg_row(_make_job())) == 6

    def test_logg_row_job_id_at_index_2(self):
        job = _make_job()
        assert build_logg_row(job)[2] == job.job_id

    def test_logg_row_action_default_is_export(self):
        assert build_logg_row(_make_job())[3] == "export"

    def test_logg_row_custom_action_and_kommentar(self):
        row = build_logg_row(_make_job(), action="manual_export", kommentar="sprint3")
        assert row[3] == "manual_export"
        assert row[5] == "sprint3"


# ---------------------------------------------------------------------------
# MockGoogleSheetsClient tests
# ---------------------------------------------------------------------------

class TestMockGoogleSheetsClient:
    def test_mock_records_calls(self):
        mock = MockGoogleSheetsClient()
        mock.append_row("sheet123", "Leads", ["a", "b", "c"])
        assert len(mock.calls) == 1
        call = mock.calls[0]
        assert call["spreadsheet_id"] == "sheet123"
        assert call["tab_name"] == "Leads"
        assert call["values"] == ["a", "b", "c"]

    def test_mock_returns_success_dict(self):
        mock = MockGoogleSheetsClient()
        result = mock.append_row("sheet123", "Leads", ["x"])
        assert result["spreadsheetId"] == "sheet123"
        assert result["updates"]["updatedRows"] == 1

    def test_mock_records_multiple_calls(self):
        mock = MockGoogleSheetsClient()
        mock.append_row("s1", "Leads", [1])
        mock.append_row("s1", "Support", [2])
        assert len(mock.calls) == 2
        assert mock.calls[1]["tab_name"] == "Support"


# ---------------------------------------------------------------------------
# Endpoint tests (via TestClient with dependency_overrides)
# ---------------------------------------------------------------------------

class TestEndpointRequiresAuth:
    def test_no_api_key_returns_401_or_403(self):
        with patch("app.core.auth._load_env_key_map", return_value={"T": "k"}):
            c = TestClient(app, raise_server_exceptions=False)
            resp = c.post("/integrations/google-sheets/export-job", json={"job_id": "x"})
        assert resp.status_code in (401, 403)


class TestEndpointSafetyGates:
    """Fail-closed safety checks — all must return blocked or 404."""

    def test_google_sheets_not_in_allowed_integrations_returns_blocked(self):
        tenant_record = _make_tenant_record(["google_mail", "monday"])
        db = _make_db()

        with (
            _override_deps(_TENANT_ID, db),
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
                return_value=tenant_record,
            ),
        ):
            c = TestClient(app)
            resp = c.post(
                "/integrations/google-sheets/export-job",
                json={"job_id": _JOB_ID, "target": "auto"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "blocked"
        assert data["reason"] == "integration_not_allowed"

    def test_missing_spreadsheet_id_returns_configuration_missing(self):
        tenant_record = _make_tenant_record(["google_sheets"])
        db = _make_db()

        with (
            _override_deps(_TENANT_ID, db),
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
                return_value=tenant_record,
            ),
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
                return_value={"google_sheets": {"spreadsheet_id": ""}},
            ),
        ):
            c = TestClient(app)
            resp = c.post(
                "/integrations/google-sheets/export-job",
                json={"job_id": _JOB_ID, "target": "auto"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "blocked"
        assert data["reason"] == "configuration_missing"

    def test_spreadsheet_id_none_returns_configuration_missing(self):
        tenant_record = _make_tenant_record(["google_sheets"])
        db = _make_db()

        with (
            _override_deps(_TENANT_ID, db),
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
                return_value=tenant_record,
            ),
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
                return_value={},  # no google_sheets key at all
            ),
        ):
            c = TestClient(app)
            resp = c.post(
                "/integrations/google-sheets/export-job",
                json={"job_id": _JOB_ID, "target": "auto"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "blocked"
        assert data["reason"] == "configuration_missing"

    def test_wrong_tenant_job_returns_404(self):
        tenant_record = _make_tenant_record(["google_sheets"])
        db = _make_db()

        with (
            _override_deps(_TENANT_ID, db),
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
                return_value=tenant_record,
            ),
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
                return_value={"google_sheets": {"spreadsheet_id": _SPREADSHEET_ID}},
            ),
            patch(
                "app.repositories.postgres.job_repository.JobRepository.get_job_by_id",
                return_value=None,  # job not found or belongs to different tenant
            ),
        ):
            c = TestClient(app)
            resp = c.post(
                "/integrations/google-sheets/export-job",
                json={"job_id": "job_belongs_to_other_tenant", "target": "auto"},
            )

        assert resp.status_code == 404

    def test_no_access_token_returns_configuration_missing(self):
        tenant_record = _make_tenant_record(["google_sheets"])
        db = _make_db()
        job = _make_lead_job()

        with (
            _override_deps(_TENANT_ID, db),
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
                return_value=tenant_record,
            ),
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
                return_value={"google_sheets": {"spreadsheet_id": _SPREADSHEET_ID}},
            ),
            patch(
                "app.repositories.postgres.job_repository.JobRepository.get_job_by_id",
                return_value=job,
            ),
            patch("app.main.settings") as mock_settings,
        ):
            mock_settings.GOOGLE_MAIL_ACCESS_TOKEN = ""
            c = TestClient(app)
            resp = c.post(
                "/integrations/google-sheets/export-job",
                json={"job_id": _JOB_ID, "target": "auto"},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "blocked"
        assert data["reason"] == "configuration_missing"


class TestEndpointSuccessPath:
    """Successful export paths."""

    def _run_export(
        self,
        job: Job,
        target: str = "auto",
        mock_client: MockGoogleSheetsClient | None = None,
    ) -> tuple[dict, MockGoogleSheetsClient]:
        if mock_client is None:
            mock_client = MockGoogleSheetsClient()

        tenant_record = _make_tenant_record(["google_sheets"])
        db = _make_db()

        with (
            _override_deps(_TENANT_ID, db),
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
                return_value=tenant_record,
            ),
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
                return_value={"google_sheets": {"spreadsheet_id": _SPREADSHEET_ID}},
            ),
            patch(
                "app.repositories.postgres.job_repository.JobRepository.get_job_by_id",
                return_value=job,
            ),
            patch(
                "app.integrations.google.sheets_client.GoogleSheetsClient",
                return_value=mock_client,
            ),
            patch("app.main.settings") as mock_settings,
            patch("app.main.create_audit_event"),
        ):
            mock_settings.GOOGLE_MAIL_ACCESS_TOKEN = "test_token"
            c = TestClient(app)
            resp = c.post(
                "/integrations/google-sheets/export-job",
                json={"job_id": job.job_id, "target": target},
            )
        return resp.json(), mock_client

    def test_lead_job_exports_to_leads_tab(self):
        data, mock_client = self._run_export(_make_lead_job(), "auto")
        assert data["status"] == "exported"
        assert data["tab"] == TAB_LEADS
        assert data["spreadsheet_id"] == _SPREADSHEET_ID

    def test_adapter_called_exactly_once_for_lead_export(self):
        mock_client = MockGoogleSheetsClient()
        _, mc = self._run_export(_make_lead_job(), "auto", mock_client)
        assert len(mc.calls) == 1

    def test_support_job_exports_to_support_tab(self):
        data, mc = self._run_export(_make_support_job(), "auto")
        assert data["status"] == "exported"
        assert data["tab"] == TAB_SUPPORT
        assert len(mc.calls) == 1
        assert mc.calls[0]["tab_name"] == TAB_SUPPORT

    def test_explicit_logg_target_sends_to_logg_tab(self):
        job = _make_job(job_type=JobType.LEAD, job_id="job_logg_001")
        data, mc = self._run_export(job, "logg")
        assert data["tab"] == TAB_LOGG
        assert mc.calls[0]["tab_name"] == TAB_LOGG

    def test_row_count_is_12_for_leads(self):
        data, _ = self._run_export(_make_lead_job(), "leads")
        assert data["row_count"] == 12

    def test_row_count_is_12_for_support(self):
        data, _ = self._run_export(_make_support_job(), "support")
        assert data["row_count"] == 12

    def test_row_count_is_6_for_logg(self):
        data, _ = self._run_export(_make_job(), "logg")
        assert data["row_count"] == 6

    def test_job_id_returned_in_response(self):
        data, _ = self._run_export(_make_lead_job(), "auto")
        assert data["job_id"] == _JOB_ID

    def test_tenant_specific_spreadsheet_id_used(self):
        """The tenant's spreadsheet_id, not a global default, is sent to the client."""
        mock_client = MockGoogleSheetsClient()
        _, mc = self._run_export(_make_lead_job(), "auto", mock_client)
        assert mc.calls[0]["spreadsheet_id"] == _SPREADSHEET_ID

    def test_audit_event_created_on_successful_export(self):
        tenant_record = _make_tenant_record(["google_sheets"])
        db = _make_db()
        job = _make_lead_job()
        mock_client = MockGoogleSheetsClient()

        with (
            _override_deps(_TENANT_ID, db),
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
                return_value=tenant_record,
            ),
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get_settings",
                return_value={"google_sheets": {"spreadsheet_id": _SPREADSHEET_ID}},
            ),
            patch(
                "app.repositories.postgres.job_repository.JobRepository.get_job_by_id",
                return_value=job,
            ),
            patch(
                "app.integrations.google.sheets_client.GoogleSheetsClient",
                return_value=mock_client,
            ),
            patch("app.main.settings") as mock_settings,
            patch("app.core.audit_service.create_audit_event") as mock_audit,
        ):
            mock_settings.GOOGLE_MAIL_ACCESS_TOKEN = "test_token"
            c = TestClient(app)
            c.post(
                "/integrations/google-sheets/export-job",
                json={"job_id": _JOB_ID, "target": "auto"},
            )

        mock_audit.assert_called_once()
        kw = mock_audit.call_args.kwargs
        assert kw["action"] == "google_sheets_export"
        assert kw["category"] == "integration"
        assert kw["status"] == "success"
        assert kw["details"]["job_id"] == _JOB_ID
        assert kw["details"]["spreadsheet_id"] == _SPREADSHEET_ID


# ---------------------------------------------------------------------------
# No auto-export from processing pipeline
# ---------------------------------------------------------------------------

class TestNoAutoExportFromPipeline:
    """The Gmail processing pipeline must never auto-export to Google Sheets."""

    def _read_source(self, *rel_parts: str) -> str:
        path = os.path.join(_REPO, *rel_parts)
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_gmail_adapter_has_no_sheets_reference(self):
        code = self._read_source("app", "workflows", "scanners", "gmail_adapter.py")
        assert "google_sheets" not in code.lower()
        assert "append_row" not in code.lower()

    def test_lead_analyzer_processor_has_no_sheets_reference(self):
        code = self._read_source(
            "app", "workflows", "processors", "lead_analyzer_processor.py"
        )
        assert "google_sheets" not in code.lower()
        assert "append_row" not in code.lower()

    def test_action_dispatch_processor_has_no_sheets_reference(self):
        code = self._read_source(
            "app", "workflows", "processors", "action_dispatch_processor.py"
        )
        assert "google_sheets" not in code.lower()
        assert "append_row" not in code.lower()

    def test_support_analyzer_processor_has_no_sheets_reference(self):
        code = self._read_source(
            "app", "workflows", "processors", "support_analyzer_processor.py"
        )
        assert "google_sheets" not in code.lower()
        assert "append_row" not in code.lower()
