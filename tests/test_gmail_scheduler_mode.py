"""
Tests for scheduler-friendly /gmail/process-inbox improvements.

Covers:
  Query handling:
    - default query "is:unread" used when request.query is absent
    - custom query forwarded to list_messages
    - query_used in response matches what was used

  Dry run:
    - dry_run=True does not call JobRepository.create_job
    - dry_run=True does not call run_pipeline
    - dry_run=True does not call mark_as_read
    - dry_run=True does not call dispatch_action (no Slack notify)
    - dry_run=True still reads messages (get_message still called)
    - dry_run response contains dry_run=True
    - dry_run created_jobs entry has status="dry_run", job_id=None
    - dry_run processed count reflects would-be items

  Scheduler-friendly response fields:
    - response includes dry_run, query_used, max_results, scanned
    - scanned equals number of messages returned by list_messages

  Non-dry-run still works correctly:
    - duplicate detection works
    - lead_disabled works
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


def _detail_result(message_id: str = "msg1") -> dict:
    return {
        "status": "success",
        "message": {
            "message_id": message_id,
            "thread_id": f"t{message_id}",
            "from": "Erik <erik@example.com>",
            "to": "me@example.com",
            "subject": f"Subject {message_id}",
            "received_at": "Mon, 21 Apr 2026 10:00:00 +0000",
            "snippet": "snippet",
            "label_ids": ["INBOX", "UNREAD"],
            "body_text": "Hello",
        },
    }


_CONFIG_ALL_ENABLED = {"enabled_job_types": ["lead", "invoice", "customer_inquiry"]}
_CONFIG_NO_LEAD = {"enabled_job_types": ["invoice", "customer_inquiry"]}


def _call(
    list_result: dict,
    existing_jobs: dict,
    detail_results: dict,
    pipeline_jobs: dict,
    max_results: int = 5,
    dry_run: bool = False,
    query: str | None = None,
    tenant_config: dict = _CONFIG_ALL_ENABLED,
    tenant_id: str = "TENANT_1001",
):
    captured_list_payloads: list = []
    mock_adapter = MagicMock()

    def fake_execute(action, payload):
        if action == "list_messages":
            captured_list_payloads.append(dict(payload))
            return list_result
        if action == "get_message":
            mid = payload["message_id"]
            r = detail_results.get(mid)
            if isinstance(r, Exception):
                raise r
            return r
        return {"status": "success"}

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
         patch("app.main.JobRepository.create_job", side_effect=lambda db, job: job) as mock_create, \
         patch("app.main.run_pipeline", side_effect=fake_run_pipeline) as mock_pipeline, \
         patch("app.main.dispatch_action") as mock_dispatch:
        result = gmail_process_inbox(
            request=GmailProcessInboxRequest(
                max_results=max_results,
                dry_run=dry_run,
                query=query,
            ),
            db=MagicMock(),
            tenant_id=tenant_id,
        )

    return result, mock_adapter, mock_create, mock_pipeline, mock_dispatch, captured_list_payloads


# ── query handling ────────────────────────────────────────────────────────────

class TestQueryHandling:
    def test_default_query_is_unread(self):
        _, _, _, _, _, list_payloads = _call(
            list_result=_list_result([]),
            existing_jobs={},
            detail_results={},
            pipeline_jobs={},
        )
        assert list_payloads[0]["query"] == "is:unread"

    def test_custom_query_forwarded_to_list_messages(self):
        _, _, _, _, _, list_payloads = _call(
            list_result=_list_result([]),
            existing_jobs={},
            detail_results={},
            pipeline_jobs={},
            query="is:unread newer_than:2d",
        )
        assert list_payloads[0]["query"] == "is:unread newer_than:2d"

    def test_none_query_uses_default(self):
        _, _, _, _, _, list_payloads = _call(
            list_result=_list_result([]),
            existing_jobs={},
            detail_results={},
            pipeline_jobs={},
            query=None,
        )
        assert list_payloads[0]["query"] == "is:unread"

    def test_query_used_in_response_matches_custom(self):
        result, *_ = _call(
            list_result=_list_result([]),
            existing_jobs={},
            detail_results={},
            pipeline_jobs={},
            query="label:inbox is:unread",
        )
        assert result["query_used"] == "label:inbox is:unread"

    def test_query_used_in_response_is_default_when_none(self):
        result, *_ = _call(
            list_result=_list_result([]),
            existing_jobs={},
            detail_results={},
            pipeline_jobs={},
        )
        assert result["query_used"] == "is:unread"


# ── dry_run mode ──────────────────────────────────────────────────────────────

class TestDryRun:
    def test_dry_run_does_not_create_jobs(self):
        _, _, mock_create, _, _, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={},
            dry_run=True,
        )
        mock_create.assert_not_called()

    def test_dry_run_does_not_run_pipeline(self):
        _, _, _, mock_pipeline, _, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={},
            dry_run=True,
        )
        mock_pipeline.assert_not_called()

    def test_dry_run_does_not_mark_as_read(self):
        _, mock_adapter, _, _, _, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={},
            dry_run=True,
        )
        actions_called = [
            c.args[0] if c.args else c.kwargs.get("action")
            for c in mock_adapter.execute_action.call_args_list
        ]
        assert "mark_as_read" not in actions_called

    def test_dry_run_does_not_notify_slack(self):
        _, _, _, _, mock_dispatch, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={},
            dry_run=True,
        )
        mock_dispatch.assert_not_called()

    def test_dry_run_still_reads_message_detail(self):
        _, mock_adapter, _, _, _, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={},
            dry_run=True,
        )
        actions_called = [
            c.args[0] if c.args else c.kwargs.get("action")
            for c in mock_adapter.execute_action.call_args_list
        ]
        assert "get_message" in actions_called

    def test_dry_run_response_has_dry_run_true(self):
        result, *_ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={},
            dry_run=True,
        )
        assert result["dry_run"] is True

    def test_non_dry_run_response_has_dry_run_false(self):
        result, *_ = _call(
            list_result=_list_result([]),
            existing_jobs={},
            detail_results={},
            pipeline_jobs={},
            dry_run=False,
        )
        assert result["dry_run"] is False

    def test_dry_run_entry_status_is_dry_run(self):
        result, *_ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={},
            dry_run=True,
        )
        assert result["created_jobs"][0]["status"] == "dry_run"

    def test_dry_run_entry_job_id_is_none(self):
        result, *_ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={},
            dry_run=True,
        )
        assert result["created_jobs"][0]["job_id"] is None

    def test_dry_run_entry_marked_handled_false(self):
        result, *_ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={},
            dry_run=True,
        )
        assert result["created_jobs"][0]["marked_handled"] is False

    def test_dry_run_entry_notified_false(self):
        result, *_ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={},
            dry_run=True,
        )
        assert result["created_jobs"][0]["notified"] is False

    def test_dry_run_processed_count_reflects_would_be_items(self):
        result, *_ = _call(
            list_result=_list_result(["msg1", "msg2"]),
            existing_jobs={"msg1": None, "msg2": None},
            detail_results={
                "msg1": _detail_result("msg1"),
                "msg2": _detail_result("msg2"),
            },
            pipeline_jobs={},
            dry_run=True,
        )
        assert result["processed"] == 2

    def test_dry_run_skips_duplicates_normally(self):
        result, *_ = _call(
            list_result=_list_result(["dup", "new"]),
            existing_jobs={"dup": _make_existing_job("old"), "new": None},
            detail_results={"new": _detail_result("new")},
            pipeline_jobs={},
            dry_run=True,
        )
        assert result["skipped"] == 1
        assert result["skipped_messages"][0]["reason"] == "duplicate"

    def test_dry_run_skips_type_disabled_normally(self):
        # A lead-keyword email is skipped when lead is not in enabled_job_types.
        result, *_ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": {
                "status": "success",
                "message": {
                    "message_id": "msg1",
                    "thread_id": "tmsg1",
                    "from": "Erik <erik@example.com>",
                    "to": "me@example.com",
                    "subject": "Offert önskas",
                    "received_at": "Mon, 21 Apr 2026 10:00:00 +0000",
                    "snippet": "snippet",
                    "label_ids": ["INBOX", "UNREAD"],
                    "body_text": "",
                },
            }},
            pipeline_jobs={},
            tenant_config=_CONFIG_NO_LEAD,
            dry_run=True,
        )
        assert result["skipped"] == 1
        assert result["skipped_messages"][0]["reason"] == "lead_disabled"


# ── scheduler-friendly response fields ───────────────────────────────────────

class TestSchedulerResponseFields:
    def test_response_includes_dry_run(self):
        result, *_ = _call(
            list_result=_list_result([]),
            existing_jobs={},
            detail_results={},
            pipeline_jobs={},
        )
        assert "dry_run" in result

    def test_response_includes_query_used(self):
        result, *_ = _call(
            list_result=_list_result([]),
            existing_jobs={},
            detail_results={},
            pipeline_jobs={},
        )
        assert "query_used" in result

    def test_response_includes_max_results(self):
        result, *_ = _call(
            list_result=_list_result([]),
            existing_jobs={},
            detail_results={},
            pipeline_jobs={},
            max_results=10,
        )
        assert result["max_results"] == 10

    def test_response_includes_scanned(self):
        result, *_ = _call(
            list_result=_list_result(["msg1", "msg2", "msg3"]),
            existing_jobs={"msg1": None, "msg2": None, "msg3": None},
            detail_results={
                "msg1": _detail_result("msg1"),
                "msg2": _detail_result("msg2"),
                "msg3": _detail_result("msg3"),
            },
            pipeline_jobs={
                "msg1": _make_processed_job("j1"),
                "msg2": _make_processed_job("j2"),
                "msg3": _make_processed_job("j3"),
            },
        )
        assert result["scanned"] == 3

    def test_scanned_reflects_list_result_count(self):
        result, *_ = _call(
            list_result=_list_result([]),
            existing_jobs={},
            detail_results={},
            pipeline_jobs={},
        )
        assert result["scanned"] == 0
