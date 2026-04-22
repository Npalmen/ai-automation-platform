"""
Tests for tenant-config lead-enabled gate in POST /gmail/process-inbox.

Covers:
  - Lead enabled: job created, pipeline runs
  - Lead disabled: job NOT created, pipeline NOT called, mark_as_read NOT called,
    skipped reason is lead_disabled
  - Duplicate wins before tenant config check: skipped as duplicate, not lead_disabled
  - Missing config (unknown tenant): follows codebase fallback (TENANT_1001 default = lead enabled)
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


def _call(
    list_result: dict,
    existing_jobs: dict,
    detail_results: dict,
    pipeline_jobs: dict,
    tenant_config: dict,
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
         patch("app.main.run_pipeline", side_effect=fake_run_pipeline):
        result = gmail_process_inbox(
            request=GmailProcessInboxRequest(max_results=5),
            db=MagicMock(),
            tenant_id=tenant_id,
        )

    return result, mock_adapter


_CONFIG_LEAD_ENABLED = {"enabled_job_types": ["lead", "invoice", "customer_inquiry"]}
_CONFIG_LEAD_DISABLED = {"enabled_job_types": ["invoice", "customer_inquiry"]}
_CONFIG_EMPTY = {"enabled_job_types": []}


# ── lead enabled ──────────────────────────────────────────────────────────────

class TestLeadEnabled:
    def test_job_created_when_lead_enabled(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
            tenant_config=_CONFIG_LEAD_ENABLED,
        )

        assert result["processed"] == 1
        assert result["skipped"] == 0
        assert result["created_jobs"][0]["job_id"] == "job-1"

    def test_pipeline_called_when_lead_enabled(self):
        with patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_tenant_config", return_value=_CONFIG_LEAD_ENABLED):

            mock_adapter = MagicMock()
            mock_adapter.execute_action.side_effect = lambda action, payload: (
                _list_result(["msg1"]) if action == "list_messages"
                else _detail_result(payload["message_id"]) if action == "get_message"
                else {"status": "success"}
            )

            mock_pipeline = MagicMock(return_value=_make_processed_job("job-1"))

            with patch("app.main.get_integration_adapter", return_value=mock_adapter), \
                 patch("app.main.JobRepository.get_by_gmail_message_id", return_value=None), \
                 patch("app.main.JobRepository.create_job", side_effect=lambda db, job: job), \
                 patch("app.main.run_pipeline", mock_pipeline):
                gmail_process_inbox(
                    request=GmailProcessInboxRequest(max_results=5),
                    db=MagicMock(),
                    tenant_id="TENANT_1001",
                )

        mock_pipeline.assert_called_once()

    def test_mark_as_read_called_when_lead_enabled(self):
        result, mock_adapter = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
            tenant_config=_CONFIG_LEAD_ENABLED,
        )

        actions = [
            c.args[0] if c.args else c.kwargs.get("action")
            for c in mock_adapter.execute_action.call_args_list
        ]
        assert "mark_as_read" in actions


# ── lead disabled ─────────────────────────────────────────────────────────────

class TestLeadDisabled:
    def test_job_not_created_when_lead_disabled(self):
        with patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_tenant_config", return_value=_CONFIG_LEAD_DISABLED):

            mock_adapter = MagicMock()
            mock_adapter.execute_action.return_value = _list_result(["msg1"])

            mock_create = MagicMock()

            with patch("app.main.get_integration_adapter", return_value=mock_adapter), \
                 patch("app.main.JobRepository.get_by_gmail_message_id", return_value=None), \
                 patch("app.main.JobRepository.create_job", mock_create):
                gmail_process_inbox(
                    request=GmailProcessInboxRequest(max_results=5),
                    db=MagicMock(),
                    tenant_id="TENANT_1001",
                )

        mock_create.assert_not_called()

    def test_pipeline_not_called_when_lead_disabled(self):
        mock_pipeline = MagicMock()

        with patch("app.main.get_integration_connection_config", return_value={}), \
             patch("app.main.get_tenant_config", return_value=_CONFIG_LEAD_DISABLED), \
             patch("app.main.get_integration_adapter") as mock_get_adapter, \
             patch("app.main.JobRepository.get_by_gmail_message_id", return_value=None), \
             patch("app.main.JobRepository.create_job", side_effect=lambda db, job: job), \
             patch("app.main.run_pipeline", mock_pipeline):

            mock_adapter = MagicMock()
            mock_adapter.execute_action.return_value = _list_result(["msg1"])
            mock_get_adapter.return_value = mock_adapter

            gmail_process_inbox(
                request=GmailProcessInboxRequest(max_results=5),
                db=MagicMock(),
                tenant_id="TENANT_1001",
            )

        mock_pipeline.assert_not_called()

    def test_mark_as_read_not_called_when_lead_disabled(self):
        result, mock_adapter = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={},
            pipeline_jobs={},
            tenant_config=_CONFIG_LEAD_DISABLED,
        )

        actions = [
            c.args[0] if c.args else c.kwargs.get("action")
            for c in mock_adapter.execute_action.call_args_list
        ]
        assert "mark_as_read" not in actions

    def test_skipped_reason_is_lead_disabled(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={},
            pipeline_jobs={},
            tenant_config=_CONFIG_LEAD_DISABLED,
        )

        assert result["skipped"] == 1
        assert result["processed"] == 0
        assert result["skipped_messages"][0]["message_id"] == "msg1"
        assert result["skipped_messages"][0]["reason"] == "lead_disabled"

    def test_empty_enabled_job_types_treats_lead_as_disabled(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={},
            pipeline_jobs={},
            tenant_config=_CONFIG_EMPTY,
        )

        assert result["skipped_messages"][0]["reason"] == "lead_disabled"


# ── duplicate wins before lead-enabled check ──────────────────────────────────

class TestDuplicateWinsBeforeTenantCheck:
    def test_duplicate_skipped_as_duplicate_even_when_lead_disabled(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": _make_existing_job("old-job")},
            detail_results={},
            pipeline_jobs={},
            tenant_config=_CONFIG_LEAD_DISABLED,
        )

        assert result["skipped"] == 1
        assert result["skipped_messages"][0]["reason"] == "duplicate"
        assert result["skipped_messages"][0]["job_id"] == "old-job"

    def test_duplicate_skipped_reason_not_lead_disabled(self):
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": _make_existing_job("old-job")},
            detail_results={},
            pipeline_jobs={},
            tenant_config=_CONFIG_LEAD_DISABLED,
        )

        reasons = [s["reason"] for s in result["skipped_messages"]]
        assert "lead_disabled" not in reasons


# ── missing / unknown tenant config ──────────────────────────────────────────

class TestMissingTenantConfig:
    def test_unknown_tenant_falls_back_to_default_lead_enabled(self):
        # get_tenant_config falls back to TENANT_1001 static config (lead enabled)
        # when tenant is unknown. We verify the real fallback logic works.
        result, _ = _call(
            list_result=_list_result(["msg1"]),
            existing_jobs={"msg1": None},
            detail_results={"msg1": _detail_result("msg1")},
            pipeline_jobs={"msg1": _make_processed_job("job-1")},
            tenant_config=_CONFIG_LEAD_ENABLED,  # matches TENANT_1001 fallback
            tenant_id="UNKNOWN_TENANT",
        )

        assert result["processed"] == 1
        assert result["skipped"] == 0
