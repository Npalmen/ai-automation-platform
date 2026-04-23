"""
Tests for tenant-config type gate and job-type inference in POST /gmail/process-inbox.

Covers:
  - Type inferred as lead when subject contains lead keyword → JobType.LEAD created
  - Type inferred as invoice when subject contains invoice keyword → JobType.INVOICE created
  - Type inferred as customer_inquiry by default → JobType.CUSTOMER_INQUIRY created
  - Inferred type disabled in tenant config → skipped with "{type}_disabled" reason
  - get_message called BEFORE tenant gate (type must be known first)
  - All three types independently gateable
  - Duplicate wins before type-gate check
  - Empty enabled_job_types → all messages skipped
  - dry_run includes inferred_type in response entry
  - created_jobs entry includes inferred_type
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.main import GmailProcessInboxRequest, gmail_process_inbox


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_existing_job(job_id: str = "existing-job"):
    job = MagicMock()
    job.job_id = job_id
    return job


def _make_processed_job(job_id: str = "new-job", status: str = "completed"):
    job = MagicMock()
    job.job_id = job_id
    job.status = MagicMock()
    job.status.value = status
    return job


def _list_result(message_ids: list[str]) -> dict:
    return {
        "status": "success",
        "messages": [{"message_id": mid, "thread_id": f"t{mid}"} for mid in message_ids],
    }


def _detail_result(message_id: str, subject: str = "Kundservice fråga", body: str = "Behöver hjälp") -> dict:
    return {
        "status": "success",
        "message": {
            "message_id": message_id,
            "thread_id": f"t{message_id}",
            "from": "Sender <sender@example.com>",
            "to": "me@example.com",
            "subject": subject,
            "received_at": "Mon, 21 Apr 2026 10:00:00 +0000",
            "snippet": "snippet",
            "label_ids": ["INBOX", "UNREAD"],
            "body_text": body,
        },
    }


def _call(
    list_result: dict,
    existing_jobs: dict,
    detail_results: dict,
    pipeline_jobs: dict,
    tenant_config: dict,
    tenant_id: str = "TENANT_1001",
    dry_run: bool = False,
):
    mock_adapter = MagicMock()

    def fake_execute(action, payload):
        if action == "list_messages":
            return list_result
        if action == "get_message":
            mid = payload["message_id"]
            r = detail_results.get(mid)
            if isinstance(r, Exception):
                raise r
            return r
        if action == "mark_as_read":
            return {"status": "success", "message_id": payload.get("message_id")}
        raise ValueError(f"unexpected action: {action}")

    mock_adapter.execute_action.side_effect = fake_execute

    def fake_get_by_gmail(db, t_id, message_id):
        return existing_jobs.get(message_id)

    def fake_run_pipeline(job, db):
        mid = job.input_data.get("source", {}).get("message_id", "")
        r = pipeline_jobs.get(mid)
        if isinstance(r, Exception):
            raise r
        return r

    with patch("app.main.get_integration_connection_config", return_value={}), \
         patch("app.main.get_integration_adapter", return_value=mock_adapter), \
         patch("app.main.get_tenant_config", return_value=tenant_config), \
         patch("app.main.JobRepository.get_by_gmail_message_id", side_effect=fake_get_by_gmail), \
         patch("app.main.JobRepository.create_job", side_effect=lambda db, job: job), \
         patch("app.main.run_pipeline", side_effect=fake_run_pipeline), \
         patch("app.main.dispatch_action", return_value={"status": "success"}):
        result = gmail_process_inbox(
            request=GmailProcessInboxRequest(max_results=5, dry_run=dry_run),
            db=MagicMock(),
            tenant_id=tenant_id,
        )

    return result, mock_adapter


_CONFIG_ALL_ENABLED = {"enabled_job_types": ["lead", "invoice", "customer_inquiry"]}
_CONFIG_LEAD_ONLY = {"enabled_job_types": ["lead"]}
_CONFIG_INVOICE_ONLY = {"enabled_job_types": ["invoice"]}
_CONFIG_INQUIRY_ONLY = {"enabled_job_types": ["customer_inquiry"]}
_CONFIG_EMPTY = {"enabled_job_types": []}
_CONFIG_NO_LEAD = {"enabled_job_types": ["invoice", "customer_inquiry"]}
_CONFIG_NO_INVOICE = {"enabled_job_types": ["lead", "customer_inquiry"]}
_CONFIG_NO_INQUIRY = {"enabled_job_types": ["lead", "invoice"]}


# ── type inference + job creation ────────────────────────────────────────────

class TestTypeInference:
    def test_lead_subject_creates_lead_job(self):
        from app.domain.workflows.enums import JobType

        captured_jobs = []

        def fake_create(db, job):
            captured_jobs.append(job)
            return job

        with patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_integration_adapter") as mock_get_adapter, \
             patch("app.main.get_tenant_config", return_value=_CONFIG_ALL_ENABLED), \
             patch("app.main.JobRepository.get_by_gmail_message_id", return_value=None), \
             patch("app.main.JobRepository.create_job", side_effect=fake_create), \
             patch("app.main.run_pipeline", return_value=_make_processed_job("j1")), \
             patch("app.main.dispatch_action", return_value={"status": "success"}):

            mock_adapter = MagicMock()
            mock_adapter.execute_action.side_effect = lambda action, payload: (
                _list_result(["msg1"]) if action == "list_messages"
                else _detail_result(payload["message_id"], subject="Offert på produkt") if action == "get_message"
                else {"status": "success"}
            )
            mock_get_adapter.return_value = mock_adapter

            gmail_process_inbox(
                request=GmailProcessInboxRequest(max_results=5),
                db=MagicMock(),
                tenant_id="TENANT_1001",
            )

        assert len(captured_jobs) == 1
        assert captured_jobs[0].job_type == JobType.LEAD

    def test_invoice_subject_creates_invoice_job(self):
        from app.domain.workflows.enums import JobType

        captured_jobs = []

        def fake_create(db, job):
            captured_jobs.append(job)
            return job

        with patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_integration_adapter") as mock_get_adapter, \
             patch("app.main.get_tenant_config", return_value=_CONFIG_ALL_ENABLED), \
             patch("app.main.JobRepository.get_by_gmail_message_id", return_value=None), \
             patch("app.main.JobRepository.create_job", side_effect=fake_create), \
             patch("app.main.run_pipeline", return_value=_make_processed_job("j1")), \
             patch("app.main.dispatch_action", return_value={"status": "success"}):

            mock_adapter = MagicMock()
            mock_adapter.execute_action.side_effect = lambda action, payload: (
                _list_result(["msg1"]) if action == "list_messages"
                else _detail_result(payload["message_id"], subject="Faktura #1234") if action == "get_message"
                else {"status": "success"}
            )
            mock_get_adapter.return_value = mock_adapter

            gmail_process_inbox(
                request=GmailProcessInboxRequest(max_results=5),
                db=MagicMock(),
                tenant_id="TENANT_1001",
            )

        assert len(captured_jobs) == 1
        assert captured_jobs[0].job_type == JobType.INVOICE

    def test_generic_subject_creates_customer_inquiry_job(self):
        from app.domain.workflows.enums import JobType

        captured_jobs = []

        def fake_create(db, job):
            captured_jobs.append(job)
            return job

        with patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_integration_adapter") as mock_get_adapter, \
             patch("app.main.get_tenant_config", return_value=_CONFIG_ALL_ENABLED), \
             patch("app.main.JobRepository.get_by_gmail_message_id", return_value=None), \
             patch("app.main.JobRepository.create_job", side_effect=fake_create), \
             patch("app.main.run_pipeline", return_value=_make_processed_job("j1")), \
             patch("app.main.dispatch_action", return_value={"status": "success"}):

            mock_adapter = MagicMock()
            mock_adapter.execute_action.side_effect = lambda action, payload: (
                _list_result(["msg1"]) if action == "list_messages"
                else _detail_result(payload["message_id"], subject="Hej, jag undrar") if action == "get_message"
                else {"status": "success"}
            )
            mock_get_adapter.return_value = mock_adapter

            gmail_process_inbox(
                request=GmailProcessInboxRequest(max_results=5),
                db=MagicMock(),
                tenant_id="TENANT_1001",
            )

        assert len(captured_jobs) == 1
        assert captured_jobs[0].job_type == JobType.CUSTOMER_INQUIRY

    def test_created_job_entry_includes_inferred_type(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1", subject="Faktura #99")},
            pipeline_jobs={"msg1": _make_processed_job("j1")},
            tenant_config=_CONFIG_ALL_ENABLED,
        )

        assert result["created_jobs"][0]["inferred_type"] == "invoice"

    def test_no_hardcoded_create_monday_in_input_data(self):
        """input_data must not contain a hardcoded actions list."""
        captured_jobs = []

        def fake_create(db, job):
            captured_jobs.append(job)
            return job

        with patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_integration_adapter") as mock_get_adapter, \
             patch("app.main.get_tenant_config", return_value=_CONFIG_ALL_ENABLED), \
             patch("app.main.JobRepository.get_by_gmail_message_id", return_value=None), \
             patch("app.main.JobRepository.create_job", side_effect=fake_create), \
             patch("app.main.run_pipeline", return_value=_make_processed_job("j1")), \
             patch("app.main.dispatch_action", return_value={"status": "success"}):

            mock_adapter = MagicMock()
            mock_adapter.execute_action.side_effect = lambda action, payload: (
                _list_result(["msg1"]) if action == "list_messages"
                else _detail_result(payload["message_id"]) if action == "get_message"
                else {"status": "success"}
            )
            mock_get_adapter.return_value = mock_adapter

            gmail_process_inbox(
                request=GmailProcessInboxRequest(max_results=5),
                db=MagicMock(),
                tenant_id="TENANT_1001",
            )

        assert "actions" not in captured_jobs[0].input_data


# ── tenant config gate ────────────────────────────────────────────────────────

class TestTenantConfigGate:
    def test_lead_disabled_skips_lead_email(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1", subject="Offert intresserad")},
            pipeline_jobs={},
            tenant_config=_CONFIG_NO_LEAD,
        )

        assert result["skipped"] == 1
        assert result["skipped_messages"][0]["reason"] == "lead_disabled"

    def test_invoice_disabled_skips_invoice_email(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1", subject="Faktura #1234")},
            pipeline_jobs={},
            tenant_config=_CONFIG_NO_INVOICE,
        )

        assert result["skipped"] == 1
        assert result["skipped_messages"][0]["reason"] == "invoice_disabled"

    def test_inquiry_disabled_skips_inquiry_email(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1", subject="Hej, hjälp tack")},
            pipeline_jobs={},
            tenant_config=_CONFIG_NO_INQUIRY,
        )

        assert result["skipped"] == 1
        assert result["skipped_messages"][0]["reason"] == "customer_inquiry_disabled"

    def test_all_types_enabled_creates_jobs(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1", subject="Faktura #1")},
            pipeline_jobs={"msg1": _make_processed_job("j1")},
            tenant_config=_CONFIG_ALL_ENABLED,
        )

        assert result["processed"] == 1

    def test_empty_enabled_types_skips_all(self):
        result, _ = _call(
            list_result=_list_result(["msg1", "msg2"]),
            existing_jobs={"msg1": None, "msg2": None},
            detail_results={
                "msg1": _detail_result("msg1", subject="Offert"),
                "msg2": _detail_result("msg2", subject="Faktura"),
            },
            pipeline_jobs={},
            tenant_config=_CONFIG_EMPTY,
        )

        assert result["skipped"] == 2
        assert result["processed"] == 0

    def test_get_message_called_before_gate(self):
        """get_message must be called so type can be inferred — even if type ends up disabled."""
        result, mock_adapter = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1", subject="Faktura #99")},
            pipeline_jobs={},
            tenant_config=_CONFIG_NO_INVOICE,
        )

        actions_called = [
            (c.args[0] if c.args else c.kwargs.get("action"))
            for c in mock_adapter.execute_action.call_args_list
        ]
        assert "get_message" in actions_called
        assert result["skipped"] == 1

    def test_mark_as_read_not_called_when_type_disabled(self):
        result, mock_adapter = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1", subject="Faktura #99")},
            pipeline_jobs={},
            tenant_config=_CONFIG_NO_INVOICE,
        )

        actions_called = [
            (c.args[0] if c.args else c.kwargs.get("action"))
            for c in mock_adapter.execute_action.call_args_list
        ]
        assert "mark_as_read" not in actions_called

    def test_pipeline_not_called_when_type_disabled(self):
        mock_pipeline = MagicMock()

        with patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_integration_adapter") as mock_get_adapter, \
             patch("app.main.get_tenant_config", return_value=_CONFIG_NO_INVOICE), \
             patch("app.main.JobRepository.get_by_gmail_message_id", return_value=None), \
             patch("app.main.JobRepository.create_job", side_effect=lambda db, job: job), \
             patch("app.main.run_pipeline", mock_pipeline), \
             patch("app.main.dispatch_action", return_value={"status": "success"}):

            mock_adapter = MagicMock()
            mock_adapter.execute_action.side_effect = lambda action, payload: (
                _list_result(["msg1"]) if action == "list_messages"
                else _detail_result(payload["message_id"], subject="Faktura #99") if action == "get_message"
                else {"status": "success"}
            )
            mock_get_adapter.return_value = mock_adapter

            gmail_process_inbox(
                request=GmailProcessInboxRequest(max_results=5),
                db=MagicMock(),
                tenant_id="TENANT_1001",
            )

        mock_pipeline.assert_not_called()


# ── duplicate wins before type gate ──────────────────────────────────────────

class TestDuplicateWinsBeforeTenantCheck:
    def test_duplicate_skipped_as_duplicate_even_when_type_disabled(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": _make_existing_job("old-job")},
            detail_results={},
            pipeline_jobs={},
            tenant_config=_CONFIG_EMPTY,
        )

        assert result["skipped"] == 1
        assert result["skipped_messages"][0]["reason"] == "duplicate"
        assert result["skipped_messages"][0]["job_id"] == "old-job"

    def test_duplicate_reason_not_type_disabled(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": _make_existing_job("old-job")},
            detail_results={},
            pipeline_jobs={},
            tenant_config=_CONFIG_EMPTY,
        )

        reasons = [s["reason"] for s in result["skipped_messages"]]
        assert "lead_disabled" not in reasons
        assert "invoice_disabled" not in reasons


# ── dry_run ───────────────────────────────────────────────────────────────────

class TestDryRun:
    def test_dry_run_entry_includes_inferred_type(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1", subject="Faktura #1")},
            pipeline_jobs={},
            tenant_config=_CONFIG_ALL_ENABLED,
            dry_run=True,
        )

        assert result["created_jobs"][0]["inferred_type"] == "invoice"
        assert result["created_jobs"][0]["status"] == "dry_run"

    def test_dry_run_does_not_call_pipeline(self):
        mock_pipeline = MagicMock()

        with patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_integration_adapter") as mock_get_adapter, \
             patch("app.main.get_tenant_config", return_value=_CONFIG_ALL_ENABLED), \
             patch("app.main.JobRepository.get_by_gmail_message_id", return_value=None), \
             patch("app.main.JobRepository.create_job", side_effect=lambda db, job: job), \
             patch("app.main.run_pipeline", mock_pipeline), \
             patch("app.main.dispatch_action", return_value={"status": "success"}):

            mock_adapter = MagicMock()
            mock_adapter.execute_action.side_effect = lambda action, payload: (
                _list_result(["msg1"]) if action == "list_messages"
                else _detail_result(payload["message_id"], subject="Faktura #1") if action == "get_message"
                else {"status": "success"}
            )
            mock_get_adapter.return_value = mock_adapter

            gmail_process_inbox(
                request=GmailProcessInboxRequest(max_results=5, dry_run=True),
                db=MagicMock(),
                tenant_id="TENANT_1001",
            )

        mock_pipeline.assert_not_called()
