"""Focused tests for Google Sheets mapper normalization and OAuth refresh."""
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
    TAB_SUPPORT,
    build_leads_row,
    build_support_row,
    normalize_sheet_cell,
)
from app.main import app

_TENANT_ID = "T_TEST_SHEETS"
_SPREADSHEET_ID = "1abc_spreadsheet_xyz"
_REPO = os.path.dirname(os.path.dirname(__file__))


def _make_job(
    *,
    job_type: JobType,
    status: JobStatus = JobStatus.AWAITING_APPROVAL,
    processor_history: list | None = None,
    job_id: str | None = None,
) -> Job:
    return Job(
        job_id=job_id or f"job_{uuid.uuid4().hex[:8]}",
        tenant_id=_TENANT_ID,
        job_type=job_type,
        status=status,
        input_data={
            "subject": "Test subject",
            "message_text": "Test message body",
            "sender": {"name": "Test User", "email": "test@example.com", "phone": "0701234567"},
            "source": {"system": "gmail"},
        },
        processor_history=processor_history or [],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _inquiry_processor_history(*, priority_category: str = "normal", action: str = "create_task") -> list:
    return [
        {
            "processor": "support_analyzer_processor",
            "result": {
                "status": "completed",
                "payload": {
                    "support_analysis": {"category": "ev_charger_fault", "ticket_type": "warranty"},
                    "support_priority": {
                        "score": 15,
                        "category": priority_category,
                        "reasons": ["ticket_type:warranty (+10)", "requires_human (+5)"],
                        "business_risk_reason": None,
                    },
                    "support_next_action": {
                        "action": action,
                        "requires_approval": True,
                        "reason": "Kontakta kunden inom 24 h",
                    },
                },
            },
        }
    ]


def _manual_review_processor_history() -> list:
    return [
        {
            "processor": "support_analyzer_processor",
            "result": {
                "status": "completed",
                "payload": {
                    "support_analysis": {"category": "safety", "ticket_type": "emergency"},
                    "support_priority": {
                        "score": 80,
                        "category": "critical",
                        "reasons": ["urgency:critical (+50)", "ticket_type:emergency (+15)"],
                        "business_risk_reason": None,
                    },
                    "support_next_action": {
                        "action": "escalate",
                        "requires_approval": True,
                        "reason": "Kritisk urgency — kräver omedelbar mänsklig hantering.",
                    },
                },
            },
        }
    ]


class TestNormalizeSheetCell:
    def test_none_becomes_blank(self):
        assert normalize_sheet_cell(None) == ""

    def test_list_joined_deterministically(self):
        assert normalize_sheet_cell(["a", "b"]) == "a; b"

    def test_support_priority_dict_readable(self):
        value = {
            "score": 80,
            "category": "critical",
            "reasons": ["urgency:critical (+50)"],
            "business_risk_reason": None,
        }
        text = normalize_sheet_cell(value)
        assert "critical" in text
        assert "80" in text
        assert "urgency:critical" in text

    def test_support_next_action_dict_readable(self):
        value = {
            "action": "escalate",
            "requires_approval": True,
            "reason": "Kritisk urgency",
        }
        text = normalize_sheet_cell(value)
        assert text.startswith("escalate")
        assert "Kritisk urgency" in text
        assert "approval required" in text

    def test_dict_falls_back_to_sorted_json(self):
        text = normalize_sheet_cell({"z_key": 1, "a_key": 2})
        assert text == '{"a_key": 2, "z_key": 1}'


class TestSupportRowScalars:
    def test_inquiry_support_row_exports_scalars_only(self):
        job = _make_job(
            job_type=JobType.CUSTOMER_INQUIRY,
            processor_history=_inquiry_processor_history(),
        )
        row = build_support_row(job)
        assert len(row) == 12
        for cell in row:
            assert isinstance(cell, (str, int, float, bool))
        assert row[-1] == job.job_id
        assert "warranty" in row[6]
        assert "create_task" in row[8]
        assert "15" in row[5]

    def test_manual_review_support_row_exports_scalars_only(self):
        job = _make_job(
            job_type=JobType.CUSTOMER_INQUIRY,
            status=JobStatus.MANUAL_REVIEW,
            processor_history=_manual_review_processor_history(),
        )
        row = build_support_row(job)
        assert len(row) == 12
        for cell in row:
            assert isinstance(cell, (str, int, float, bool))
        assert row[9] == "manual_review"
        assert "escalate" in row[8]
        assert "critical" in row[5]

    def test_lead_mapping_unchanged(self):
        from tests.test_google_sheets_export import _make_lead_job

        row = build_leads_row(_make_lead_job())
        assert len(row) == 12
        assert row[1] == "Anna Berg"
        assert row[4] == "ev_charger"


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


def _make_tenant_record(allowed: list) -> MagicMock:
    record = MagicMock()
    record.allowed_integrations = allowed
    return record


class TestSheetsOAuthRefresh:
    def _run_export(self, job: Job, *, token: str | None = "fresh_token", refresh_error: str | None = None):
        mock_client = MockGoogleSheetsClient()
        db = MagicMock()
        db.add = MagicMock()
        db.commit = MagicMock()
        tenant_record = _make_tenant_record(["google_sheets"])

        resolve_patch = (
            patch(
                "app.integrations.google.sheets_auth.resolve_google_sheets_access_token",
                side_effect=RuntimeError(refresh_error),
            )
            if refresh_error
            else patch(
                "app.integrations.google.sheets_auth.resolve_google_sheets_access_token",
                return_value=token,
            )
        )

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
            resolve_patch,
            patch("app.main.create_audit_event"),
            patch("app.main.settings") as mock_settings,
        ):
            mock_settings.GOOGLE_MAIL_ACCESS_TOKEN = ""
            client = TestClient(app)
            resp = client.post(
                "/integrations/google-sheets/export-job",
                json={"job_id": job.job_id, "target": "auto"},
            )
        return resp.json(), mock_client

    def test_export_uses_refreshed_token_not_stale_env(self):
        job = _make_job(
            job_type=JobType.CUSTOMER_INQUIRY,
            processor_history=_inquiry_processor_history(),
        )
        data, mock_client = self._run_export(job)
        assert data["status"] == "exported"
        assert data["tab"] == TAB_SUPPORT
        assert len(mock_client.calls) == 1

    def test_refresh_failure_returns_safe_blocked_error(self):
        job = _make_job(job_type=JobType.LEAD)
        data, mock_client = self._run_export(
            job,
            refresh_error="Google OAuth refresh credentials are not configured for Sheets export.",
        )
        assert data["status"] == "blocked"
        assert data["reason"] == "configuration_missing"
        assert len(mock_client.calls) == 0

    def test_integration_allowlist_still_enforced(self):
        db = MagicMock()
        tenant_record = _make_tenant_record(["google_mail"])

        with (
            _override_deps(_TENANT_ID, db),
            patch(
                "app.repositories.postgres.tenant_config_repository.TenantConfigRepository.get",
                return_value=tenant_record,
            ),
        ):
            client = TestClient(app)
            resp = client.post(
                "/integrations/google-sheets/export-job",
                json={"job_id": "job_x", "target": "auto"},
            )
        data = resp.json()
        assert data["status"] == "blocked"
        assert data["reason"] == "integration_not_allowed"

    def test_success_response_documents_append_only(self):
        job = _make_job(job_type=JobType.LEAD)
        data, _ = self._run_export(job)
        assert data["export_mode"] == "append_only"
        assert "not idempotent" in data["duplicate_warning"]

    def test_export_endpoint_does_not_reference_gmail_mutation(self):
        code = open(os.path.join(_REPO, "app", "main.py"), encoding="utf-8").read()
        start = code.index("def google_sheets_export_job")
        end = code.index("def _extract_invoice_payload_from_history", start)
        block = code[start:end]
        assert "GoogleMailClient" not in block
        assert "mark_as_read" not in block
        assert "execute_action" not in block
