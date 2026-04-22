"""
Tests for mark-as-handled behavior in POST /gmail/process-inbox.

Covers:
  - Successful message: mark_as_read called on adapter
  - Duplicate: mark_as_read NOT called
  - get_message failure: mark_as_read NOT called
  - pipeline failure: mark_as_read NOT called
  - mark_as_read failure: processed still counted, marked_handled=False, warning in entry
  - marked_handled=True in created_jobs entry on success
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

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


def _detail_result(message_id: str) -> dict:
    return {
        "status": "success",
        "message": {
            "message_id": message_id,
            "thread_id": f"t{message_id}",
            "from": "Sender <sender@example.com>",
            "to": "me@example.com",
            "subject": f"Subject {message_id}",
            "received_at": "Mon, 21 Apr 2026 10:00:00 +0000",
            "snippet": "snippet",
            "label_ids": ["INBOX", "UNREAD"],
            "body_text": f"Body for {message_id}",
        },
    }


def _build_adapter_mock(
    list_result: dict,
    detail_results: dict,          # {message_id: dict | Exception}
    mark_as_read_result=None,      # None = success, Exception = failure
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
            if isinstance(mark_as_read_result, Exception):
                raise mark_as_read_result
            return {"status": "success", "message_id": payload.get("message_id")}
        raise ValueError(f"unexpected action: {action}")

    mock_adapter.execute_action.side_effect = fake_execute
    return mock_adapter


def _call(
    list_result: dict,
    existing_jobs: dict,
    detail_results: dict,
    pipeline_jobs: dict,
    mark_as_read_result=None,
    tenant_id: str = "TENANT_1001",
):
    mock_adapter = _build_adapter_mock(list_result, detail_results, mark_as_read_result)

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
         patch("app.main.JobRepository.get_by_gmail_message_id", side_effect=fake_get_by_gmail), \
         patch("app.main.JobRepository.create_job", side_effect=lambda db, job: job), \
         patch("app.main.run_pipeline", side_effect=fake_run_pipeline):
        result = gmail_process_inbox(
            request=GmailProcessInboxRequest(max_results=5),
            db=MagicMock(),
            tenant_id=tenant_id,
        )

    return result, mock_adapter


# ── mark_as_read called on success ────────────────────────────────────────────

class TestMarkAsReadCalledOnSuccess:
    def test_mark_as_read_called_after_pipeline_success(self):
        _, mock_adapter = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
        )

        actions = [c.args[0] if c.args else c.kwargs.get("action") for c in mock_adapter.execute_action.call_args_list]
        assert "mark_as_read" in actions

    def test_mark_as_read_called_with_correct_message_id(self):
        _, mock_adapter = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
        )

        mark_calls = [
            c for c in mock_adapter.execute_action.call_args_list
            if (c.args[0] if c.args else c.kwargs.get("action")) == "mark_as_read"
        ]
        assert len(mark_calls) == 1
        payload = mark_calls[0].args[1] if len(mark_calls[0].args) > 1 else mark_calls[0].kwargs.get("payload", {})
        assert payload["message_id"] == "msg1"

    def test_created_job_entry_has_marked_handled_true(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
        )

        assert result["created_jobs"][0]["marked_handled"] is True

    def test_no_mark_warning_on_success(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
        )

        assert "mark_warning" not in result["created_jobs"][0]


# ── mark_as_read NOT called for non-successes ─────────────────────────────────

class TestMarkAsReadNotCalledForNonSuccess:
    def test_duplicate_does_not_call_mark_as_read(self):
        _, mock_adapter = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": _make_existing_job("old-job")},
            detail_results={},
            pipeline_jobs={},
        )

        actions = [c.args[0] if c.args else c.kwargs.get("action") for c in mock_adapter.execute_action.call_args_list]
        assert "mark_as_read" not in actions

    def test_get_message_failure_does_not_call_mark_as_read(self):
        _, mock_adapter = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": RuntimeError("Gmail API error (404): not found")},
            pipeline_jobs={},
        )

        actions = [c.args[0] if c.args else c.kwargs.get("action") for c in mock_adapter.execute_action.call_args_list]
        assert "mark_as_read" not in actions

    def test_pipeline_failure_does_not_call_mark_as_read(self):
        _, mock_adapter = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": RuntimeError("DB connection lost")},
        )

        actions = [c.args[0] if c.args else c.kwargs.get("action") for c in mock_adapter.execute_action.call_args_list]
        assert "mark_as_read" not in actions


# ── mark_as_read failure handling ─────────────────────────────────────────────

class TestMarkAsReadFailure:
    def test_processed_still_counted_when_mark_fails(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
            mark_as_read_result=RuntimeError("Gmail API error (403): insufficient scope"),
        )

        assert result["processed"] == 1
        assert result["failed"] == 0

    def test_marked_handled_false_when_mark_fails(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
            mark_as_read_result=RuntimeError("Gmail API error (403): insufficient scope"),
        )

        assert result["created_jobs"][0]["marked_handled"] is False

    def test_mark_warning_present_when_mark_fails(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
            mark_as_read_result=RuntimeError("Gmail API error (403): insufficient scope"),
        )

        entry = result["created_jobs"][0]
        assert "mark_warning" in entry
        assert "403" in entry["mark_warning"]

    def test_job_id_still_present_when_mark_fails(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
            mark_as_read_result=RuntimeError("Gmail API error (403): insufficient scope"),
        )

        assert result["created_jobs"][0]["job_id"] == "job-1"


# ── multiple messages: only successes marked ──────────────────────────────────

class TestMixedBatch:
    def test_only_successful_messages_are_marked(self):
        _, mock_adapter = _call(
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

        mark_calls = [
            c for c in mock_adapter.execute_action.call_args_list
            if (c.args[0] if c.args else c.kwargs.get("action")) == "mark_as_read"
        ]
        marked_ids = [
            (c.args[1] if len(c.args) > 1 else c.kwargs.get("payload", {}))["message_id"]
            for c in mark_calls
        ]
        assert marked_ids == ["new"]
