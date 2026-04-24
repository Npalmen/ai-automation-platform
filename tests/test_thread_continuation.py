"""Tests for thread continuation in POST /gmail/process-inbox.

When an incoming Gmail message shares a thread_id with an existing job,
the system updates that job instead of creating a new one.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.main import gmail_process_inbox, GmailProcessInboxRequest
from app.domain.workflows.models import Job
from app.domain.workflows.enums import JobType
from app.domain.workflows.statuses import JobStatus


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_job(job_id: str = "existing-job", thread_id: str = "thread-abc") -> Job:
    job = MagicMock(spec=Job)
    job.job_id = job_id
    job.tenant_id = "TENANT_1001"
    job.job_type = JobType.LEAD
    job.status = JobStatus.COMPLETED
    job.processor_history = ["old-history"]
    job.input_data = {
        "subject": "Original subject",
        "message_text": "Original message",
        "sender": {"name": "Alice", "email": "alice@example.com"},
        "source": {
            "system": "gmail",
            "message_id": "msg-original",
            "thread_id": thread_id,
        },
    }
    job.result = {}
    return job


def _make_processed_job(job_id: str = "existing-job") -> MagicMock:
    j = MagicMock()
    j.job_id = job_id
    j.status = JobStatus.COMPLETED
    j.input_data = {}
    return j


def _list_result(message_ids: list[str]) -> dict:
    return {
        "status": "success",
        "messages": [{"message_id": mid, "thread_id": f"thread-{mid}"} for mid in message_ids],
    }


def _detail_result(
    message_id: str,
    thread_id: str = "thread-abc",
    subject: str = "Re: Fråga",
    body_text: str = "Here is my reply with more details.",
    sender_name: str = "Alice",
    sender_email: str = "alice@example.com",
) -> dict:
    return {
        "message": {
            "message_id": message_id,
            "thread_id": thread_id,
            "from": f"{sender_name} <{sender_email}>",
            "subject": subject,
            "body_text": body_text,
        }
    }


_ALL_TYPES = {"enabled_job_types": ["lead", "invoice", "customer_inquiry"]}


def _call(
    list_result: dict,
    detail_results: dict,
    existing_by_msg: dict,          # {message_id: Job | None}
    existing_by_thread: dict | None = None,  # {thread_id: Job | None} — None means always None
    pipeline_result=None,
    update_result=None,
    dry_run: bool = False,
    tenant_id: str = "TENANT_1001",
):
    """Run gmail_process_inbox with full mocks for all repository calls."""

    def fake_execute(action, payload):
        if action == "list_messages":
            return list_result
        if action == "get_message":
            mid = payload["message_id"]
            r = detail_results.get(mid)
            if isinstance(r, Exception):
                raise r
            return r
        return {"status": "success"}

    mock_adapter = MagicMock()
    mock_adapter.execute_action.side_effect = fake_execute

    def fake_get_by_msg(db, t_id, message_id):
        return existing_by_msg.get(message_id)

    def fake_get_by_thread(db, t_id, source_system, thread_id):
        if existing_by_thread is None:
            return None
        return existing_by_thread.get(thread_id)

    def fake_run_pipeline(job, db):
        if isinstance(pipeline_result, Exception):
            raise pipeline_result
        if pipeline_result is not None:
            return pipeline_result
        return _make_processed_job(job.job_id)

    def fake_update_job(db, job):
        if isinstance(update_result, Exception):
            raise update_result
        return job

    with patch("app.main.get_integration_connection_config", return_value={}), \
         patch("app.main.get_integration_adapter", return_value=mock_adapter), \
         patch("app.main.get_tenant_config", return_value=_ALL_TYPES), \
         patch("app.main.JobRepository.get_by_gmail_message_id", side_effect=fake_get_by_msg), \
         patch("app.main.JobRepository.get_by_source_thread_id", side_effect=fake_get_by_thread), \
         patch("app.main.JobRepository.create_job", side_effect=lambda db, job: job) as mock_create, \
         patch("app.main.JobRepository.update_job", side_effect=fake_update_job) as mock_update, \
         patch("app.main.run_pipeline", side_effect=fake_run_pipeline), \
         patch("app.main.dispatch_action", return_value={"status": "success"}):
        result = gmail_process_inbox(
            request=GmailProcessInboxRequest(max_results=5, dry_run=dry_run),
            db=MagicMock(),
            tenant_id=tenant_id,
        )
        return result, mock_create, mock_update, mock_adapter


# ── 1. New thread → creates new job ──────────────────────────────────────────

class TestNewThread:
    def test_new_thread_id_creates_new_job(self):
        result, mock_create, mock_update, _ = _call(
            list_result=_list_result(["msg1"]),
            detail_results={"msg1": _detail_result("msg1", thread_id="new-thread")},
            existing_by_msg={"msg1": None},
            existing_by_thread={"new-thread": None},
        )

        mock_create.assert_called_once()
        mock_update.assert_not_called()
        assert result["processed"] == 1
        assert result["created_jobs"][0]["continued"] is False

    def test_new_job_entry_has_no_continuation_reason(self):
        result, _, _, _ = _call(
            list_result=_list_result(["msg1"]),
            detail_results={"msg1": _detail_result("msg1", thread_id="new-thread")},
            existing_by_msg={"msg1": None},
            existing_by_thread={"new-thread": None},
        )

        entry = result["created_jobs"][0]
        assert entry["continued"] is False
        assert "continuation_reason" not in entry


# ── 2. Existing thread → updates existing job ─────────────────────────────────

class TestContinuation:
    def test_existing_thread_updates_existing_job_not_creates_new(self):
        existing = _make_job(job_id="existing-job", thread_id="thread-abc")
        result, mock_create, mock_update, _ = _call(
            list_result=_list_result(["msg2"]),
            detail_results={"msg2": _detail_result("msg2", thread_id="thread-abc")},
            existing_by_msg={"msg2": None},
            existing_by_thread={"thread-abc": existing},
        )

        mock_create.assert_not_called()
        mock_update.assert_called_once()
        assert result["processed"] == 1

    def test_continuation_entry_has_continued_true(self):
        existing = _make_job(job_id="existing-job", thread_id="thread-abc")
        result, _, _, _ = _call(
            list_result=_list_result(["msg2"]),
            detail_results={"msg2": _detail_result("msg2", thread_id="thread-abc")},
            existing_by_msg={"msg2": None},
            existing_by_thread={"thread-abc": existing},
        )

        entry = result["created_jobs"][0]
        assert entry["continued"] is True
        assert entry["continuation_reason"] == "thread_id_match"
        assert entry["job_id"] == "existing-job"

    def test_continuation_appends_to_conversation_messages(self):
        existing = _make_job(thread_id="thread-abc")
        captured_input = {}

        def fake_update(db, job):
            captured_input.update(job.input_data)
            return job

        with patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_integration_adapter") as mock_get_adapter, \
             patch("app.main.get_tenant_config", return_value=_ALL_TYPES), \
             patch("app.main.JobRepository.get_by_gmail_message_id", return_value=None), \
             patch("app.main.JobRepository.get_by_source_thread_id", return_value=existing), \
             patch("app.main.JobRepository.update_job", side_effect=fake_update), \
             patch("app.main.run_pipeline", return_value=_make_processed_job()), \
             patch("app.main.dispatch_action", return_value={"status": "success"}):
            mock_adapter = MagicMock()
            mock_adapter.execute_action.side_effect = lambda action, payload: (
                _list_result(["msg2"]) if action == "list_messages"
                else _detail_result("msg2", thread_id="thread-abc", subject="Re: Original", body_text="My reply") if action == "get_message"
                else {"status": "success"}
            )
            mock_get_adapter.return_value = mock_adapter

            gmail_process_inbox(
                request=GmailProcessInboxRequest(max_results=5),
                db=MagicMock(),
                tenant_id="TENANT_1001",
            )

        messages = captured_input.get("conversation_messages", [])
        assert len(messages) == 1
        assert messages[0]["message_id"] == "msg2"
        assert messages[0]["thread_id"] == "thread-abc"
        assert messages[0]["subject"] == "Re: Original"
        assert messages[0]["message_text"] == "My reply"
        assert messages[0]["source"] == "gmail"

    def test_continuation_preserves_original_input_data(self):
        existing = _make_job(thread_id="thread-abc")
        captured_input = {}

        def fake_update(db, job):
            captured_input.update(job.input_data)
            return job

        with patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_integration_adapter") as mock_get_adapter, \
             patch("app.main.get_tenant_config", return_value=_ALL_TYPES), \
             patch("app.main.JobRepository.get_by_gmail_message_id", return_value=None), \
             patch("app.main.JobRepository.get_by_source_thread_id", return_value=existing), \
             patch("app.main.JobRepository.update_job", side_effect=fake_update), \
             patch("app.main.run_pipeline", return_value=_make_processed_job()), \
             patch("app.main.dispatch_action", return_value={"status": "success"}):
            mock_adapter = MagicMock()
            mock_adapter.execute_action.side_effect = lambda action, payload: (
                _list_result(["msg2"]) if action == "list_messages"
                else _detail_result("msg2", thread_id="thread-abc") if action == "get_message"
                else {"status": "success"}
            )
            mock_get_adapter.return_value = mock_adapter

            gmail_process_inbox(
                request=GmailProcessInboxRequest(max_results=5),
                db=MagicMock(),
                tenant_id="TENANT_1001",
            )

        assert captured_input.get("subject") == "Original subject"
        assert captured_input.get("message_text") == "Original message"

    def test_continuation_updates_latest_fields(self):
        existing = _make_job(thread_id="thread-abc")
        captured_input = {}

        def fake_update(db, job):
            captured_input.update(job.input_data)
            return job

        with patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_integration_adapter") as mock_get_adapter, \
             patch("app.main.get_tenant_config", return_value=_ALL_TYPES), \
             patch("app.main.JobRepository.get_by_gmail_message_id", return_value=None), \
             patch("app.main.JobRepository.get_by_source_thread_id", return_value=existing), \
             patch("app.main.JobRepository.update_job", side_effect=fake_update), \
             patch("app.main.run_pipeline", return_value=_make_processed_job()), \
             patch("app.main.dispatch_action", return_value={"status": "success"}):
            mock_adapter = MagicMock()
            mock_adapter.execute_action.side_effect = lambda action, payload: (
                _list_result(["msg2"]) if action == "list_messages"
                else _detail_result("msg2", thread_id="thread-abc",
                                    subject="Re: Svar", body_text="Mer info nu.",
                                    sender_name="Bob", sender_email="bob@example.com") if action == "get_message"
                else {"status": "success"}
            )
            mock_get_adapter.return_value = mock_adapter

            gmail_process_inbox(
                request=GmailProcessInboxRequest(max_results=5),
                db=MagicMock(),
                tenant_id="TENANT_1001",
            )

        assert captured_input["latest_message_text"] == "Mer info nu."
        assert captured_input["latest_subject"] == "Re: Svar"
        assert captured_input["latest_sender"]["name"] == "Bob"
        assert captured_input["latest_sender"]["email"] == "bob@example.com"

    def test_continuation_runs_pipeline(self):
        existing = _make_job(thread_id="thread-abc")
        pipeline_calls = []

        def fake_pipeline(job, db):
            pipeline_calls.append(job)
            return _make_processed_job(job.job_id)

        with patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_integration_adapter") as mock_get_adapter, \
             patch("app.main.get_tenant_config", return_value=_ALL_TYPES), \
             patch("app.main.JobRepository.get_by_gmail_message_id", return_value=None), \
             patch("app.main.JobRepository.get_by_source_thread_id", return_value=existing), \
             patch("app.main.JobRepository.update_job", side_effect=lambda db, job: job), \
             patch("app.main.run_pipeline", side_effect=fake_pipeline), \
             patch("app.main.dispatch_action", return_value={"status": "success"}):
            mock_adapter = MagicMock()
            mock_adapter.execute_action.side_effect = lambda action, payload: (
                _list_result(["msg2"]) if action == "list_messages"
                else _detail_result("msg2", thread_id="thread-abc") if action == "get_message"
                else {"status": "success"}
            )
            mock_get_adapter.return_value = mock_adapter

            gmail_process_inbox(
                request=GmailProcessInboxRequest(max_results=5),
                db=MagicMock(),
                tenant_id="TENANT_1001",
            )

        assert len(pipeline_calls) == 1

    def test_continuation_marks_message_as_read(self):
        existing = _make_job(thread_id="thread-abc")
        result, _, _, mock_adapter = _call(
            list_result=_list_result(["msg2"]),
            detail_results={"msg2": _detail_result("msg2", thread_id="thread-abc")},
            existing_by_msg={"msg2": None},
            existing_by_thread={"thread-abc": existing},
        )

        actions_called = [
            c.kwargs.get("action") or (c.args[0] if c.args else None)
            for c in mock_adapter.execute_action.call_args_list
        ]
        assert "mark_as_read" in actions_called
        assert result["created_jobs"][0]["marked_handled"] is True


# ── 3. Dedup wins before continuation ─────────────────────────────────────────

class TestDeduplicationStillWins:
    def test_dedup_skips_before_continuation_lookup(self):
        existing_by_msg = {"msg1": _make_job(job_id="old-job")}
        result, mock_create, mock_update, _ = _call(
            list_result=_list_result(["msg1"]),
            detail_results={},
            existing_by_msg=existing_by_msg,
            existing_by_thread=None,
        )

        mock_create.assert_not_called()
        mock_update.assert_not_called()
        assert result["skipped"] == 1
        assert result["skipped_messages"][0]["reason"] == "duplicate"


# ── 4. Dry run with existing thread ───────────────────────────────────────────

class TestDryRunContinuation:
    def test_dry_run_does_not_update_existing_job(self):
        existing = _make_job(thread_id="thread-abc")
        result, mock_create, mock_update, _ = _call(
            list_result=_list_result(["msg2"]),
            detail_results={"msg2": _detail_result("msg2", thread_id="thread-abc")},
            existing_by_msg={"msg2": None},
            existing_by_thread={"thread-abc": existing},
            dry_run=True,
        )

        mock_update.assert_not_called()
        mock_create.assert_not_called()

    def test_dry_run_continuation_response_shows_existing_job_id(self):
        existing = _make_job(job_id="existing-job", thread_id="thread-abc")
        result, _, _, _ = _call(
            list_result=_list_result(["msg2"]),
            detail_results={"msg2": _detail_result("msg2", thread_id="thread-abc")},
            existing_by_msg={"msg2": None},
            existing_by_thread={"thread-abc": existing},
            dry_run=True,
        )

        entry = result["created_jobs"][0]
        assert entry["status"] == "dry_run"
        assert entry["job_id"] == "existing-job"
        assert entry["continuation_reason"] == "thread_id_match"

    def test_dry_run_does_not_mark_as_read(self):
        existing = _make_job(thread_id="thread-abc")
        result, _, _, mock_adapter = _call(
            list_result=_list_result(["msg2"]),
            detail_results={"msg2": _detail_result("msg2", thread_id="thread-abc")},
            existing_by_msg={"msg2": None},
            existing_by_thread={"thread-abc": existing},
            dry_run=True,
        )

        actions = [
            c.kwargs.get("action") or (c.args[0] if c.args else None)
            for c in mock_adapter.execute_action.call_args_list
        ]
        assert "mark_as_read" not in actions


# ── 5. Missing thread_id falls back to new-job path ───────────────────────────

class TestMissingThreadId:
    def test_missing_thread_id_creates_new_job(self):
        result, mock_create, mock_update, _ = _call(
            list_result={
                "status": "success",
                "messages": [{"message_id": "msg1", "thread_id": ""}],
            },
            detail_results={"msg1": _detail_result("msg1", thread_id="")},
            existing_by_msg={"msg1": None},
            existing_by_thread=None,
        )

        mock_create.assert_called_once()
        mock_update.assert_not_called()
        assert result["processed"] == 1
        assert result["created_jobs"][0]["continued"] is False


# ── 6. Tenant isolation ───────────────────────────────────────────────────────

class TestTenantIsolation:
    def test_same_thread_id_different_tenant_does_not_continue(self):
        """get_by_source_thread_id returns None for the requesting tenant
        even though the same thread_id exists under a different tenant."""
        result, mock_create, mock_update, _ = _call(
            list_result=_list_result(["msg1"]),
            detail_results={"msg1": _detail_result("msg1", thread_id="thread-abc")},
            existing_by_msg={"msg1": None},
            existing_by_thread={"thread-abc": None},  # no match for this tenant
        )

        mock_create.assert_called_once()
        mock_update.assert_not_called()
        assert result["created_jobs"][0]["continued"] is False


# ── 7. Existing new-job flow unaffected ───────────────────────────────────────

class TestExistingFlowUnaffected:
    def test_new_lead_job_created_normally(self):
        result, mock_create, _, _ = _call(
            list_result=_list_result(["msg1"]),
            detail_results={"msg1": _detail_result("msg1", thread_id="t-new",
                                                    subject="Offert önskas", body_text="Intresserad av köp")},
            existing_by_msg={"msg1": None},
            existing_by_thread={"t-new": None},
        )

        mock_create.assert_called_once()
        assert result["created_jobs"][0]["inferred_type"] == "lead"

    def test_invoice_type_inference_still_works(self):
        result, _, _, _ = _call(
            list_result=_list_result(["msg1"]),
            detail_results={"msg1": _detail_result("msg1", thread_id="t-new",
                                                    subject="Faktura #9999", body_text="Belopp: 5 000 kr")},
            existing_by_msg={"msg1": None},
            existing_by_thread={"t-new": None},
        )

        assert result["created_jobs"][0]["inferred_type"] == "invoice"

    def test_customer_inquiry_type_inference_still_works(self):
        result, _, _, _ = _call(
            list_result=_list_result(["msg1"]),
            detail_results={"msg1": _detail_result("msg1", thread_id="t-new",
                                                    subject="Fråga om support", body_text="Jag behöver hjälp.")},
            existing_by_msg={"msg1": None},
            existing_by_thread={"t-new": None},
        )

        assert result["created_jobs"][0]["inferred_type"] == "customer_inquiry"
