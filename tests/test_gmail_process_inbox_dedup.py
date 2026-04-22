"""
Tests for POST /gmail/process-inbox deduplication and updated response format.

Covers:
  - Duplicate message: repo returns existing job → skipped, no new job created
  - New message: repo returns None → job created, processed count = 1
  - get_message failure → failed, not skipped, not processed
  - Missing message_id in stub → failed
  - Mixed batch: one duplicate, one new, one get_message failure
  - Response shape: processed, skipped, failed, created_jobs, skipped_messages, failed_messages
  - get_by_gmail_message_id called with correct args
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest
from fastapi import HTTPException

from app.main import GmailProcessInboxRequest, gmail_process_inbox


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_existing_job(job_id: str = "existing-job-123"):
    job = MagicMock()
    job.job_id = job_id
    return job


def _make_processed_job(job_id: str = "new-job-456", status: str = "completed"):
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


def _detail_result(message_id: str) -> dict:
    return {
        "status": "success",
        "message": {
            "message_id": message_id,
            "thread_id": f"t{message_id}",
            "from": f"Sender <sender@example.com>",
            "to": "me@example.com",
            "subject": f"Subject {message_id}",
            "received_at": "Mon, 21 Apr 2026 10:00:00 +0000",
            "snippet": "snippet",
            "label_ids": ["INBOX", "UNREAD"],
            "body_text": f"Body for {message_id}",
        },
    }


def _call(
    list_result: dict,
    existing_jobs: dict,          # {message_id: Job | None}
    detail_results: dict,         # {message_id: dict | Exception}
    pipeline_jobs: dict,          # {message_id: Job | Exception}
    max_results: int = 5,
    tenant_id: str = "TENANT_1001",
):
    def fake_execute(action, payload):
        if action == "list_messages":
            return list_result
        if action == "get_message":
            mid = payload["message_id"]
            r = detail_results.get(mid)
            if isinstance(r, Exception):
                raise r
            return r
        raise ValueError(f"unexpected action: {action}")

    def fake_get_by_gmail_message_id(db, t_id, message_id):
        return existing_jobs.get(message_id)

    def fake_run_pipeline(job, db):
        mid = job.input_data.get("source", {}).get("message_id", "")
        r = pipeline_jobs.get(mid)
        if isinstance(r, Exception):
            raise r
        return r

    mock_adapter = MagicMock()
    mock_adapter.execute_action.side_effect = fake_execute

    with patch("app.main.get_integration_connection_config", return_value={}), \
         patch("app.main.get_integration_adapter", return_value=mock_adapter), \
         patch(
             "app.main.JobRepository.get_by_gmail_message_id",
             side_effect=fake_get_by_gmail_message_id,
         ), \
         patch("app.main.JobRepository.create_job", side_effect=lambda db, job: job), \
         patch("app.main.run_pipeline", side_effect=fake_run_pipeline):
        return gmail_process_inbox(
            request=GmailProcessInboxRequest(max_results=max_results),
            db=MagicMock(),
            tenant_id=tenant_id,
        )


# ── deduplication ─────────────────────────────────────────────────────────────

class TestDeduplication:
    def test_duplicate_message_is_skipped(self):
        existing = _make_existing_job("existing-job-123")
        result = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": existing},
            detail_results={},
            pipeline_jobs={},
        )

        assert result["processed"] == 0
        assert result["skipped"] == 1
        assert result["failed"] == 0
        assert result["created_jobs"] == []
        assert len(result["skipped_messages"]) == 1

        skip = result["skipped_messages"][0]
        assert skip["message_id"] == "msg1"
        assert skip["reason"] == "duplicate"
        assert skip["job_id"] == "existing-job-123"

    def test_duplicate_does_not_create_job(self):
        existing = _make_existing_job()

        with patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_integration_adapter") as mock_get_adapter, \
             patch("app.main.JobRepository.get_by_gmail_message_id", return_value=existing), \
             patch("app.main.JobRepository.create_job") as mock_create:

            mock_adapter = MagicMock()
            mock_adapter.execute_action.return_value = _list_result(["msg1"])
            mock_get_adapter.return_value = mock_adapter

            gmail_process_inbox(
                request=GmailProcessInboxRequest(max_results=5),
                db=MagicMock(),
                tenant_id="TENANT_1001",
            )

        mock_create.assert_not_called()

    def test_new_message_is_processed(self):
        result = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("new-job-456")},
        )

        assert result["processed"] == 1
        assert result["skipped"] == 0
        assert result["failed"] == 0
        assert result["created_jobs"][0]["message_id"] == "msg1"
        assert result["created_jobs"][0]["job_id"] == "new-job-456"

    def test_get_by_gmail_called_with_correct_args(self):
        captured_calls = []

        def fake_get_by_gmail(db, tenant_id, message_id):
            captured_calls.append((tenant_id, message_id))
            return None

        def fake_execute(action, payload):
            if action == "list_messages":
                return _list_result(["msg1", "msg2"])
            return _detail_result(payload["message_id"])

        mock_adapter = MagicMock()
        mock_adapter.execute_action.side_effect = fake_execute

        with patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_integration_adapter", return_value=mock_adapter), \
             patch("app.main.JobRepository.get_by_gmail_message_id", side_effect=fake_get_by_gmail), \
             patch("app.main.JobRepository.create_job", side_effect=lambda db, job: job), \
             patch("app.main.run_pipeline", return_value=_make_processed_job()):
            gmail_process_inbox(
                request=GmailProcessInboxRequest(max_results=5),
                db=MagicMock(),
                tenant_id="TENANT_1001",
            )

        assert ("TENANT_1001", "msg1") in captured_calls
        assert ("TENANT_1001", "msg2") in captured_calls


# ── failure handling ──────────────────────────────────────────────────────────

class TestFailureHandling:
    def test_get_message_failure_goes_to_failed(self):
        result = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": RuntimeError("Gmail API error (404): not found")},
            pipeline_jobs={},
        )

        assert result["processed"] == 0
        assert result["skipped"] == 0
        assert result["failed"] == 1
        assert result["failed_messages"][0]["message_id"] == "msg1"
        assert "404" in result["failed_messages"][0]["reason"]

    def test_missing_message_id_goes_to_failed(self):
        list_result_with_empty_id = {
            "status": "success",
            "messages": [{"message_id": "", "thread_id": "t1"}],
        }
        result = _call(
            list_result=list_result_with_empty_id,
            existing_jobs={},
            detail_results={},
            pipeline_jobs={},
        )

        assert result["failed"] == 1
        assert result["failed_messages"][0]["reason"] == "missing message_id"

    def test_pipeline_failure_goes_to_failed(self):
        result = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": RuntimeError("DB connection lost")},
        )

        assert result["processed"] == 0
        assert result["failed"] == 1
        assert result["failed_messages"][0]["message_id"] == "msg1"


# ── mixed batch ───────────────────────────────────────────────────────────────

class TestMixedBatch:
    def test_one_duplicate_one_new_one_failed(self):
        result = _call(
            list_result=_list_result(["dup", "new", "bad"]),
            existing_jobs={
                "dup": _make_existing_job("old-job"),
                "new": None,
                "bad": None,
            },
            detail_results={
                "new": _detail_result("new"),
                "bad": RuntimeError("Gmail API error (500): server error"),
            },
            pipeline_jobs={"new": _make_processed_job("new-job")},
        )

        assert result["processed"] == 1
        assert result["skipped"] == 1
        assert result["failed"] == 1

        assert result["created_jobs"][0]["job_id"] == "new-job"
        assert result["skipped_messages"][0]["job_id"] == "old-job"
        assert result["failed_messages"][0]["message_id"] == "bad"

    def test_empty_inbox(self):
        result = _call(
            list_result={"status": "success", "messages": []},
            existing_jobs={},
            detail_results={},
            pipeline_jobs={},
        )

        assert result["processed"] == 0
        assert result["skipped"] == 0
        assert result["failed"] == 0
        assert result["created_jobs"] == []
        assert result["skipped_messages"] == []
        assert result["failed_messages"] == []


# ── response shape ────────────────────────────────────────────────────────────

class TestResponseShape:
    def test_all_keys_present(self):
        result = _call(
            list_result={"status": "success", "messages": []},
            existing_jobs={},
            detail_results={},
            pipeline_jobs={},
        )

        assert "processed" in result
        assert "skipped" in result
        assert "failed" in result
        assert "created_jobs" in result
        assert "skipped_messages" in result
        assert "failed_messages" in result

    def test_skipped_message_shape(self):
        existing = _make_existing_job("old-job")
        result = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": existing},
            detail_results={},
            pipeline_jobs={},
        )

        skip = result["skipped_messages"][0]
        assert "message_id" in skip
        assert "reason" in skip
        assert "job_id" in skip
