"""
Tests for job-creation Slack notification in POST /gmail/process-inbox.

Covers:
  - Successful job creation triggers dispatch_action with notify_slack
  - notify_slack action contains correct tenant_id, channel, message fields
  - message body contains sender, subject, job_id, tenant, source, type
  - Duplicate message does NOT trigger notification
  - type_disabled skip does NOT trigger notification
  - get_message failure does NOT trigger notification
  - pipeline failure does NOT trigger notification
  - Notification failure is non-fatal: processed still counted, notified=False
  - notify_warning present in entry when notification fails
  - notified=True in created_jobs entry on success
  - notified=False in created_jobs entry on notify failure
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


def _detail_result(
    message_id: str = "msg1",
    from_header: str = "Erik Lindqvist <erik@example.com>",
    subject: str = "New inquiry",
    body_text: str = "Hello",
) -> dict:
    return {
        "status": "success",
        "message": {
            "message_id": message_id,
            "thread_id": f"t{message_id}",
            "from": from_header,
            "to": "me@example.com",
            "subject": subject,
            "received_at": "Mon, 21 Apr 2026 10:00:00 +0000",
            "snippet": "snippet",
            "label_ids": ["INBOX", "UNREAD"],
            "body_text": body_text,
        },
    }


_CONFIG_ALL_ENABLED = {"enabled_job_types": ["lead", "invoice", "customer_inquiry"]}
_CONFIG_INQUIRY_DISABLED = {"enabled_job_types": ["lead", "invoice"]}


def _call(
    list_result: dict,
    existing_jobs: dict,
    detail_results: dict,            # {message_id: dict | Exception}
    pipeline_jobs: dict,             # {message_id: Job | Exception}
    tenant_config: dict = _CONFIG_ALL_ENABLED,
    dispatch_action_side_effect=None,  # None=success, Exception=failure
    tenant_id: str = "TENANT_1001",
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
        # mark_as_read and anything else
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
         patch("app.main.JobRepository.get_by_source_thread_id", return_value=None), \
         patch("app.main.JobRepository.create_job", side_effect=lambda db, job: job), \
         patch("app.main.run_pipeline", side_effect=fake_run_pipeline), \
         patch("app.main.dispatch_action", side_effect=dispatch_action_side_effect) as mock_dispatch:
        result = gmail_process_inbox(
            request=GmailProcessInboxRequest(max_results=5),
            db=MagicMock(),
            tenant_id=tenant_id,
        )

    return result, mock_dispatch


# ── notification triggered on success ─────────────────────────────────────────

class TestNotificationTriggeredOnSuccess:
    def test_dispatch_action_called_after_successful_lead(self):
        _, mock_dispatch = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
        )
        mock_dispatch.assert_called_once()

    def test_notify_slack_action_type(self):
        _, mock_dispatch = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
        )
        action = mock_dispatch.call_args[0][0]
        assert action["type"] == "notify_slack"

    def test_action_contains_tenant_id(self):
        _, mock_dispatch = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
            tenant_id="TENANT_1001",
        )
        action = mock_dispatch.call_args[0][0]
        assert action["tenant_id"] == "TENANT_1001"

    def test_action_targets_inbox_channel(self):
        _, mock_dispatch = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
        )
        action = mock_dispatch.call_args[0][0]
        assert action["channel"] == "#inbox"

    def test_message_body_contains_sender(self):
        _, mock_dispatch = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1", from_header="Erik Lindqvist <erik@example.com>")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
        )
        msg = mock_dispatch.call_args[0][0]["message"]
        assert "Erik Lindqvist" in msg

    def test_message_body_contains_subject(self):
        _, mock_dispatch = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1", subject="Pricing question")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
        )
        msg = mock_dispatch.call_args[0][0]["message"]
        assert "Pricing question" in msg

    def test_message_body_contains_inferred_type(self):
        _, mock_dispatch = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1", subject="Faktura #99")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
        )
        msg = mock_dispatch.call_args[0][0]["message"]
        assert "invoice" in msg

    def test_message_body_contains_job_id(self):
        _, mock_dispatch = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-abc")},
        )
        msg = mock_dispatch.call_args[0][0]["message"]
        assert "job-abc" in msg

    def test_message_body_contains_source_gmail(self):
        _, mock_dispatch = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
        )
        msg = mock_dispatch.call_args[0][0]["message"]
        assert "gmail" in msg.lower()

    def test_created_jobs_entry_has_notified_true(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
        )
        assert result["created_jobs"][0]["notified"] is True


# ── notification NOT triggered for non-successes ──────────────────────────────

class TestNotificationNotTriggered:
    def test_duplicate_does_not_notify(self):
        _, mock_dispatch = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": _make_existing_job("old-job")},
            detail_results={},
            pipeline_jobs={},
        )
        mock_dispatch.assert_not_called()

    def test_type_disabled_does_not_notify(self):
        _, mock_dispatch = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            # Subject chosen to classify as customer_inquiry (no lead/invoice/partner keywords)
            detail_results={"msg1": _detail_result("msg1", subject="Hej, när öppnar ni?")},
            pipeline_jobs={},
            tenant_config=_CONFIG_INQUIRY_DISABLED,
        )
        mock_dispatch.assert_not_called()

    def test_get_message_failure_does_not_notify(self):
        _, mock_dispatch = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": RuntimeError("Gmail API error (404): not found")},
            pipeline_jobs={},
        )
        mock_dispatch.assert_not_called()

    def test_pipeline_failure_does_not_notify(self):
        _, mock_dispatch = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": RuntimeError("DB connection lost")},
        )
        mock_dispatch.assert_not_called()


# ── notification failure is non-fatal ─────────────────────────────────────────

class TestNotificationFailureNonFatal:
    def test_processed_count_unchanged_when_notify_fails(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
            dispatch_action_side_effect=RuntimeError("Slack webhook unreachable"),
        )
        assert result["processed"] == 1
        assert result["failed"] == 0

    def test_notified_false_when_notify_fails(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
            dispatch_action_side_effect=RuntimeError("Slack webhook unreachable"),
        )
        assert result["created_jobs"][0]["notified"] is False

    def test_notify_warning_present_when_notify_fails(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
            dispatch_action_side_effect=RuntimeError("Slack webhook unreachable"),
        )
        entry = result["created_jobs"][0]
        assert "notify_warning" in entry
        assert "Slack" in entry["notify_warning"] or "unreachable" in entry["notify_warning"]

    def test_job_id_still_present_when_notify_fails(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
            dispatch_action_side_effect=RuntimeError("Slack webhook unreachable"),
        )
        assert result["created_jobs"][0]["job_id"] == "job-1"

    def test_no_notify_warning_when_notify_succeeds(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
        )
        assert "notify_warning" not in result["created_jobs"][0]


# ── mixed batch: only successes notified ──────────────────────────────────────

class TestMixedBatch:
    def test_only_successful_messages_trigger_notification(self):
        _, mock_dispatch = _call(
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
        # dispatch_action called exactly once — for "new" only
        assert mock_dispatch.call_count == 1
        action = mock_dispatch.call_args[0][0]
        assert "new-job" in action["message"]
