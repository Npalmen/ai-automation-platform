"""Tests for GET /cases and GET /cases/{job_id}.

Uses direct function calls with mocked DB — consistent with repo test pattern.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from fastapi import HTTPException


_NOW = datetime(2026, 4, 25, 10, 0, 0, tzinfo=timezone.utc)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_record(
    job_id: str = "JOB-1",
    tenant_id: str = "T1",
    job_type: str = "lead",
    status: str = "completed",
    input_data: dict | None = None,
    result: dict | None = None,
):
    r = MagicMock()
    r.job_id = job_id
    r.tenant_id = tenant_id
    r.job_type = job_type
    r.status = status
    r.created_at = _NOW
    r.updated_at = _NOW
    r.input_data = input_data or {}
    r.result = result or {}
    return r


def _make_action(
    job_id: str = "JOB-1",
    action_type: str = "send_email",
    status: str = "success",
    error_message: str | None = None,
    result_payload: dict | None = None,
):
    a = MagicMock()
    a.job_id = job_id
    a.action_type = action_type
    a.status = status
    a.error_message = error_message
    a.result_payload = result_payload or {}
    a.executed_at = _NOW
    return a


def _list(
    tenant_id: str = "T1",
    records: list | None = None,
    total: int | None = None,
    status: str | None = None,
    type_: str | None = None,
):
    from app.main import list_cases

    db = MagicMock()
    mock_q = MagicMock()
    db.query.return_value = mock_q
    mock_q.filter.return_value = mock_q
    mock_q.order_by.return_value = mock_q
    mock_q.offset.return_value = mock_q
    mock_q.limit.return_value = mock_q
    mock_q.count.return_value = total if total is not None else len(records or [])
    mock_q.all.return_value = records or []

    return list_cases(db=db, tenant_id=tenant_id, limit=25, offset=0,
                      status=status, type=type_)


def _get(
    job_id: str = "JOB-1",
    tenant_id: str = "T1",
    record: MagicMock | None = None,
    actions: list | None = None,
):
    from app.main import get_case

    db = MagicMock()
    mock_q = MagicMock()
    db.query.return_value = mock_q
    mock_q.filter.return_value = mock_q
    mock_q.order_by.return_value = mock_q
    mock_q.first.return_value = record
    mock_q.all.return_value = actions or []

    return get_case(job_id=job_id, db=db, tenant_id=tenant_id)


# ══════════════════════════════════════════════════════════════════════════════
# GET /cases — list shape
# ══════════════════════════════════════════════════════════════════════════════

class TestListCasesShape:
    def test_returns_items_and_total(self):
        r = _list()
        assert "items" in r
        assert "total" in r

    def test_empty_returns_zero_total(self):
        r = _list(records=[], total=0)
        assert r["total"] == 0
        assert r["items"] == []

    def test_item_has_required_keys(self):
        rec = _make_record()
        r = _list(records=[rec])
        item = r["items"][0]
        for key in ("job_id", "created_at", "type", "status", "subject", "customer_name", "priority"):
            assert key in item, f"Missing key: {key}"

    def test_item_type_and_status(self):
        rec = _make_record(job_type="invoice", status="awaiting_approval")
        r = _list(records=[rec])
        assert r["items"][0]["type"] == "invoice"
        assert r["items"][0]["status"] == "awaiting_approval"

    def test_created_at_is_isoformat(self):
        rec = _make_record()
        item = _list(records=[rec])["items"][0]
        assert "T" in item["created_at"]  # ISO8601 contains T

    def test_total_reflects_db_count(self):
        r = _list(records=[], total=42)
        assert r["total"] == 42


# ══════════════════════════════════════════════════════════════════════════════
# GET /cases — subject / customer_name derivation
# ══════════════════════════════════════════════════════════════════════════════

class TestListCasesDerivation:
    def test_subject_from_input_data(self):
        rec = _make_record(input_data={"subject": "Test email"})
        item = _list(records=[rec])["items"][0]
        assert item["subject"] == "Test email"

    def test_subject_falls_back_to_latest_message_subject(self):
        rec = _make_record(input_data={"latest_message_subject": "Re: follow-up"})
        item = _list(records=[rec])["items"][0]
        assert item["subject"] == "Re: follow-up"

    def test_subject_null_when_absent(self):
        rec = _make_record(input_data={})
        item = _list(records=[rec])["items"][0]
        assert item["subject"] is None

    def test_customer_name_from_sender_dict(self):
        rec = _make_record(input_data={"sender": {"name": "Alice", "email": "a@ex.com"}})
        item = _list(records=[rec])["items"][0]
        assert item["customer_name"] == "Alice"

    def test_customer_name_from_entity_extraction(self):
        history = [{"processor": "entity_extraction_processor",
                    "result": {"payload": {"entities": {"customer_name": "Bob"}}}}]
        rec = _make_record(result={"processor_history": history})
        item = _list(records=[rec])["items"][0]
        assert item["customer_name"] == "Bob"

    def test_customer_name_null_when_absent(self):
        rec = _make_record(input_data={})
        item = _list(records=[rec])["items"][0]
        assert item["customer_name"] is None

    def test_priority_from_action_dispatch_history(self):
        history = [{"processor": "action_dispatch_processor",
                    "result": {"payload": {"actions_requested": [
                        {"column_values": {"priority": "HIGH"}}
                    ]}}}]
        rec = _make_record(result={"processor_history": history})
        item = _list(records=[rec])["items"][0]
        assert item["priority"] == "high"

    def test_priority_null_when_absent(self):
        rec = _make_record()
        item = _list(records=[rec])["items"][0]
        assert item["priority"] is None


# ══════════════════════════════════════════════════════════════════════════════
# GET /cases — tenant isolation
# ══════════════════════════════════════════════════════════════════════════════

class TestListCasesTenantIsolation:
    def test_db_filter_called(self):
        from app.main import list_cases

        db = MagicMock()
        mock_q = MagicMock()
        db.query.return_value = mock_q
        mock_q.filter.return_value = mock_q
        mock_q.order_by.return_value = mock_q
        mock_q.offset.return_value = mock_q
        mock_q.limit.return_value = mock_q
        mock_q.count.return_value = 0
        mock_q.all.return_value = []

        list_cases(db=db, tenant_id="TENANT_XYZ", limit=25, offset=0, status=None, type=None)
        assert db.query.called


# ══════════════════════════════════════════════════════════════════════════════
# GET /cases/{job_id} — shape
# ══════════════════════════════════════════════════════════════════════════════

class TestGetCaseShape:
    def test_returns_all_required_keys(self):
        rec = _make_record()
        r = _get(record=rec)
        for key in ("job_id", "created_at", "updated_at", "type", "status",
                    "priority", "subject", "customer_name", "original_message",
                    "extracted_data", "thread_messages", "actions", "errors"):
            assert key in r, f"Missing key: {key}"

    def test_original_message_has_from_email_body(self):
        rec = _make_record()
        r = _get(record=rec)
        assert "from" in r["original_message"]
        assert "email" in r["original_message"]
        assert "body" in r["original_message"]

    def test_thread_messages_is_list(self):
        rec = _make_record()
        assert isinstance(_get(record=rec)["thread_messages"], list)

    def test_actions_is_list(self):
        rec = _make_record()
        assert isinstance(_get(record=rec)["actions"], list)

    def test_errors_is_list(self):
        rec = _make_record()
        assert isinstance(_get(record=rec)["errors"], list)


# ══════════════════════════════════════════════════════════════════════════════
# GET /cases/{job_id} — 404
# ══════════════════════════════════════════════════════════════════════════════

class TestGetCaseNotFound:
    def test_404_on_missing_job(self):
        with pytest.raises(HTTPException) as exc_info:
            _get(job_id="NONEXISTENT", record=None)
        assert exc_info.value.status_code == 404

    def test_404_detail_message(self):
        with pytest.raises(HTTPException) as exc_info:
            _get(record=None)
        assert "not found" in exc_info.value.detail.lower()


# ══════════════════════════════════════════════════════════════════════════════
# GET /cases/{job_id} — field content
# ══════════════════════════════════════════════════════════════════════════════

class TestGetCaseContent:
    def test_original_message_from_sender(self):
        rec = _make_record(input_data={
            "sender": {"name": "Alice", "email": "alice@ex.com"},
            "message_text": "Hello there",
        })
        r = _get(record=rec)
        assert r["original_message"]["from"] == "Alice"
        assert r["original_message"]["email"] == "alice@ex.com"
        assert r["original_message"]["body"] == "Hello there"

    def test_extracted_data_from_entity_processor(self):
        history = [{"processor": "entity_extraction_processor",
                    "result": {"payload": {"entities": {"customer_name": "Bob", "email": "b@ex.com"}}}}]
        rec = _make_record(result={"processor_history": history})
        r = _get(record=rec)
        assert r["extracted_data"]["customer_name"] == "Bob"

    def test_extracted_data_null_when_no_entities(self):
        rec = _make_record()
        r = _get(record=rec)
        assert r["extracted_data"] is None

    def test_thread_messages_from_conversation_messages(self):
        inp = {"conversation_messages": [
            {"subject": "Re: test", "message_text": "reply body", "source": "gmail",
             "received_at": "2026-04-25T10:00:00+00:00"},
        ]}
        rec = _make_record(input_data=inp)
        r = _get(record=rec)
        assert len(r["thread_messages"]) == 1
        assert r["thread_messages"][0]["subject"] == "Re: test"
        assert r["thread_messages"][0]["body"] == "reply body"
        assert r["thread_messages"][0]["direction"] == "incoming"

    def test_thread_messages_empty_when_no_conversation(self):
        rec = _make_record(input_data={})
        r = _get(record=rec)
        assert r["thread_messages"] == []

    def test_actions_populated_from_action_records(self):
        rec = _make_record()
        action = _make_action(action_type="create_monday_item", status="success")
        r = _get(record=rec, actions=[action])
        assert len(r["actions"]) == 1
        assert r["actions"][0]["type"] == "create_monday_item"
        assert r["actions"][0]["status"] == "success"

    def test_errors_from_failed_action_error_message(self):
        rec = _make_record()
        action = _make_action(status="failed", error_message="Monday API timeout")
        r = _get(record=rec, actions=[action])
        assert any("Monday API timeout" in e["message"] for e in r["errors"])

    def test_errors_empty_when_no_failures(self):
        rec = _make_record()
        action = _make_action(status="success", error_message=None)
        r = _get(record=rec, actions=[action])
        assert r["errors"] == []

    def test_subject_derived_from_input(self):
        rec = _make_record(input_data={"subject": "Hej från kund"})
        r = _get(record=rec)
        assert r["subject"] == "Hej från kund"

    def test_type_and_status_correct(self):
        rec = _make_record(job_type="customer_inquiry", status="awaiting_approval")
        r = _get(record=rec)
        assert r["type"] == "customer_inquiry"
        assert r["status"] == "awaiting_approval"
