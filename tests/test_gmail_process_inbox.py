"""
Tests for POST /gmail/process-inbox.

Calls the endpoint function directly (no TestClient/httpx) — matches repo pattern.

Covers:
  - _parse_from_header: Name <email>, quoted name, bare email, empty string
  - returns processed count and created_jobs list
  - maps message fields into correct job input_data shape
  - skips messages where get_message raises
  - returns empty result when no unread messages
  - Gmail list_messages failure raises HTTPException 503
  - max_results defaults to 5 and is forwarded
  - query is always "is:unread"
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.main import _parse_from_header, GmailProcessInboxRequest, gmail_process_inbox


# ── _parse_from_header ────────────────────────────────────────────────────────

def test_parse_from_header_name_and_email():
    name, email = _parse_from_header("Erik Lindqvist <erik@example.com>")
    assert name == "Erik Lindqvist"
    assert email == "erik@example.com"


def test_parse_from_header_quoted_name():
    name, email = _parse_from_header('"Erik Lindqvist" <erik@example.com>')
    assert name == "Erik Lindqvist"
    assert email == "erik@example.com"


def test_parse_from_header_bare_email():
    name, email = _parse_from_header("erik@example.com")
    assert name == ""
    assert email == "erik@example.com"


def test_parse_from_header_empty():
    name, email = _parse_from_header("")
    assert name == ""
    assert email == ""


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_list_result(message_ids: list[str]) -> dict:
    return {
        "status": "success",
        "messages": [
            {
                "message_id": mid,
                "thread_id": f"t{mid}",
                "from": f"Sender {mid} <sender{mid}@example.com>",
                "subject": f"Subject {mid}",
                "received_at": "Mon, 21 Apr 2026 10:00:00 +0000",
                "snippet": f"Snippet {mid}",
                "label_ids": ["INBOX", "UNREAD"],
            }
            for mid in message_ids
        ],
    }


def _make_detail_result(message_id: str) -> dict:
    return {
        "status": "success",
        "message": {
            "message_id": message_id,
            "thread_id": f"t{message_id}",
            "from": f"Sender {message_id} <sender{message_id}@example.com>",
            "to": "recipient@example.com",
            "subject": f"Subject {message_id}",
            "received_at": "Mon, 21 Apr 2026 10:00:00 +0000",
            "snippet": f"Snippet {message_id}",
            "label_ids": ["INBOX", "UNREAD"],
            "body_text": f"Body text for {message_id}",
        },
    }


def _make_job(job_id: str, status: str = "completed"):
    job = MagicMock()
    job.job_id = job_id
    job.status = MagicMock()
    job.status.value = status
    return job


def _call(
    list_result: dict,
    detail_results: dict,
    pipeline_jobs: dict,
    max_results: int = 5,
    tenant_id: str = "TENANT_1001",
):
    """
    Call gmail_process_inbox with mocked adapter and pipeline.

    detail_results: {message_id: result_dict | Exception}
    pipeline_jobs:  {message_id: Job mock | Exception}
    """
    def fake_execute(action, payload):
        if action == "list_messages":
            return list_result
        if action == "get_message":
            mid = payload.get("message_id")
            r = detail_results.get(mid)
            if isinstance(r, Exception):
                raise r
            return r
        raise ValueError(f"unexpected action {action}")

    mock_adapter = MagicMock()
    mock_adapter.execute_action.side_effect = fake_execute

    def fake_run_pipeline(job, db):
        mid = job.input_data.get("source", {}).get("message_id", "")
        r = pipeline_jobs.get(mid)
        if isinstance(r, Exception):
            raise r
        return r

    with patch("app.main.get_integration_connection_config", return_value={}), \
         patch("app.main.get_integration_adapter", return_value=mock_adapter), \
         patch("app.main.get_tenant_config", return_value={"enabled_job_types": ["lead", "invoice", "customer_inquiry"]}), \
         patch("app.main.JobRepository.get_by_gmail_message_id", return_value=None), \
         patch("app.main.JobRepository.get_by_source_thread_id", return_value=None), \
         patch("app.main.JobRepository.create_job", side_effect=lambda db, job: job), \
         patch("app.main.run_pipeline", side_effect=fake_run_pipeline), \
         patch("app.main.dispatch_action", return_value={"status": "success"}):
        return gmail_process_inbox(
            request=GmailProcessInboxRequest(max_results=max_results),
            db=MagicMock(),
            tenant_id=tenant_id,
        )


# ── endpoint behaviour ────────────────────────────────────────────────────────

class TestGmailProcessInbox:
    def test_returns_processed_count_and_job_ids(self):
        result = _call(
            list_result=_make_list_result(["msg1", "msg2"]),
            detail_results={
                "msg1": _make_detail_result("msg1"),
                "msg2": _make_detail_result("msg2"),
            },
            pipeline_jobs={
                "msg1": _make_job("job-aaa"),
                "msg2": _make_job("job-bbb"),
            },
        )

        assert result["processed"] == 2
        job_ids = [j["job_id"] for j in result["created_jobs"]]
        assert "job-aaa" in job_ids
        assert "job-bbb" in job_ids
        message_ids = [j["message_id"] for j in result["created_jobs"]]
        assert "msg1" in message_ids
        assert "msg2" in message_ids

    def test_job_input_data_shape(self):
        captured = {}

        def fake_run_pipeline(job, db):
            captured.update(job.input_data)
            return _make_job("job-x")

        mock_adapter = MagicMock()
        mock_adapter.execute_action.side_effect = lambda action, payload: (
            _make_list_result(["msg1"]) if action == "list_messages"
            else _make_detail_result(payload["message_id"])
        )

        with patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_integration_adapter", return_value=mock_adapter), \
             patch("app.main.get_tenant_config", return_value={"enabled_job_types": ["lead", "invoice", "customer_inquiry"]}), \
             patch("app.main.JobRepository.get_by_gmail_message_id", return_value=None), \
             patch("app.main.JobRepository.get_by_source_thread_id", return_value=None), \
             patch("app.main.JobRepository.create_job", side_effect=lambda db, job: job), \
             patch("app.main.run_pipeline", side_effect=fake_run_pipeline), \
             patch("app.main.dispatch_action", return_value={"status": "success"}):
            gmail_process_inbox(
                request=GmailProcessInboxRequest(max_results=1),
                db=MagicMock(),
                tenant_id="TENANT_1001",
            )

        assert captured["subject"] == "Subject msg1"
        assert captured["message_text"] == "Body text for msg1"
        assert captured["sender"]["name"] == "Sender msg1"
        assert captured["sender"]["email"] == "sendermsg1@example.com"
        assert captured["source"]["system"] == "gmail"
        assert captured["source"]["message_id"] == "msg1"
        assert captured["source"]["thread_id"] == "tmsg1"
        assert "actions" not in captured

    def test_skips_message_when_get_message_raises(self):
        result = _call(
            list_result=_make_list_result(["msg1", "msg2"]),
            detail_results={
                "msg1": RuntimeError("Gmail API error (404): not found"),
                "msg2": _make_detail_result("msg2"),
            },
            pipeline_jobs={"msg2": _make_job("job-bbb")},
        )

        assert result["processed"] == 1
        assert result["created_jobs"][0]["message_id"] == "msg2"

    def test_skips_message_when_pipeline_raises(self):
        result = _call(
            list_result=_make_list_result(["msg1", "msg2"]),
            detail_results={
                "msg1": _make_detail_result("msg1"),
                "msg2": _make_detail_result("msg2"),
            },
            pipeline_jobs={
                "msg1": RuntimeError("DB connection lost"),
                "msg2": _make_job("job-bbb"),
            },
        )

        assert result["processed"] == 1
        assert result["created_jobs"][0]["message_id"] == "msg2"

    def test_empty_inbox_returns_zero(self):
        result = _call(
            list_result={"status": "success", "messages": []},
            detail_results={},
            pipeline_jobs={},
        )

        assert result["processed"] == 0
        assert result["created_jobs"] == []

    def test_list_messages_failure_raises_503(self):
        mock_adapter = MagicMock()
        mock_adapter.execute_action.side_effect = RuntimeError("Gmail API error (401)")

        with patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_integration_adapter", return_value=mock_adapter):
            with pytest.raises(HTTPException) as exc_info:
                gmail_process_inbox(
                    request=GmailProcessInboxRequest(max_results=5),
                    db=MagicMock(),
                    tenant_id="TENANT_1001",
                )

        assert exc_info.value.status_code == 503
        assert "list_messages failed" in exc_info.value.detail

    def test_max_results_forwarded_to_adapter(self):
        captured = {}

        def fake_execute(action, payload):
            if action == "list_messages":
                captured.update(payload)
                return {"status": "success", "messages": []}
            raise ValueError("unexpected")

        mock_adapter = MagicMock()
        mock_adapter.execute_action.side_effect = fake_execute

        with patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_integration_adapter", return_value=mock_adapter):
            gmail_process_inbox(
                request=GmailProcessInboxRequest(max_results=10),
                db=MagicMock(),
                tenant_id="TENANT_1001",
            )

        assert captured["max_results"] == 10

    def test_default_max_results_is_5(self):
        captured = {}

        def fake_execute(action, payload):
            if action == "list_messages":
                captured.update(payload)
                return {"status": "success", "messages": []}
            raise ValueError("unexpected")

        mock_adapter = MagicMock()
        mock_adapter.execute_action.side_effect = fake_execute

        with patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_integration_adapter", return_value=mock_adapter):
            gmail_process_inbox(
                request=GmailProcessInboxRequest(),
                db=MagicMock(),
                tenant_id="TENANT_1001",
            )

        assert captured["max_results"] == 5

    def test_query_is_always_unread(self):
        captured = {}

        def fake_execute(action, payload):
            if action == "list_messages":
                captured.update(payload)
                return {"status": "success", "messages": []}
            raise ValueError("unexpected")

        mock_adapter = MagicMock()
        mock_adapter.execute_action.side_effect = fake_execute

        with patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_integration_adapter", return_value=mock_adapter):
            gmail_process_inbox(
                request=GmailProcessInboxRequest(),
                db=MagicMock(),
                tenant_id="TENANT_1001",
            )

        assert captured["query"] == "is:unread"

    def test_response_includes_status_per_job(self):
        result = _call(
            list_result=_make_list_result(["msg1"]),
            detail_results={"msg1": _make_detail_result("msg1")},
            pipeline_jobs={"msg1": _make_job("job-aaa", status="completed")},
        )

        assert result["created_jobs"][0]["status"] == "completed"
