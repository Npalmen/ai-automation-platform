"""
Tests for invoice default action injection.

Covers:
  _build_invoice_default_actions:
    - produces create_monday_item + create_internal_task
    - item_name uses sender_name, falls back to sender_email, falls back to "Okänd avsändare"
    - column_values contains source="invoice", subject when present, email when present
    - column_values omits subject when absent
    - column_values omits email when absent
    - create_internal_task title and description include sender label
    - create_internal_task metadata contains job_id, tenant_id, detected_job_type

  _build_fallback_actions routing:
    - invoice detected_job_type -> invoice defaults
    - inquiry detected_job_type -> inquiry defaults (unchanged)
    - lead/other -> generic fallback (unchanged)

  _resolve_actions override behaviour:
    - invoice without input_data.actions -> defaults injected
    - invoice WITH input_data.actions -> override wins
    - decisioning actions take priority over defaults

  process_action_dispatch_job (mocked execute_action):
    - both invoice actions executed
    - override actions executed as-is
    - status completed when all succeed
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.workflows.processors.action_dispatch_processor import (
    _build_fallback_actions,
    _build_invoice_default_actions,
    _resolve_actions,
    process_action_dispatch_job,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _invoice_job(input_data: dict | None = None) -> Job:
    job = Job(
        tenant_id="TENANT_1001",
        job_type=JobType.INVOICE,
        input_data=input_data or {},
    )
    job.processor_history = [
        {
            "processor": "classification_processor",
            "result": {"payload": {"detected_job_type": "invoice"}},
        }
    ]
    return job


def _inquiry_job(input_data: dict | None = None) -> Job:
    job = Job(
        tenant_id="TENANT_1001",
        job_type=JobType.CUSTOMER_INQUIRY,
        input_data=input_data or {},
    )
    job.processor_history = [
        {
            "processor": "classification_processor",
            "result": {"payload": {"detected_job_type": "customer_inquiry"}},
        }
    ]
    return job


def _lead_job(input_data: dict | None = None) -> Job:
    job = Job(
        tenant_id="TENANT_1001",
        job_type=JobType.LEAD,
        input_data=input_data or {},
    )
    job.processor_history = [
        {
            "processor": "classification_processor",
            "result": {"payload": {"detected_job_type": "lead"}},
        }
    ]
    return job


# ── _build_invoice_default_actions ───────────────────────────────────────────

class TestBuildInvoiceDefaultActions:
    def test_produces_two_actions(self):
        job = _invoice_job({"subject": "Faktura #1", "sender": {"email": "a@ex.com"}})
        assert len(_build_invoice_default_actions(job)) == 2

    def test_first_action_is_create_monday_item(self):
        job = _invoice_job()
        assert _build_invoice_default_actions(job)[0]["type"] == "create_monday_item"

    def test_second_action_is_create_internal_task(self):
        job = _invoice_job()
        assert _build_invoice_default_actions(job)[1]["type"] == "create_internal_task"

    # item_name ---

    def test_item_name_uses_sender_name(self):
        job = _invoice_job({"sender": {"name": "Leverantör AB", "email": "lev@ex.com"}})
        assert _build_invoice_default_actions(job)[0]["item_name"] == "Faktura: Leverantör AB"

    def test_item_name_falls_back_to_sender_email(self):
        job = _invoice_job({"sender": {"email": "lev@ex.com"}})
        assert _build_invoice_default_actions(job)[0]["item_name"] == "Faktura: lev@ex.com"

    def test_item_name_falls_back_to_okand_avsandare(self):
        job = _invoice_job({})
        assert _build_invoice_default_actions(job)[0]["item_name"] == "Faktura: Okänd avsändare"

    def test_item_name_flat_sender_keys(self):
        job = _invoice_job({"sender_name": "Flat AB", "sender_email": "flat@ex.com"})
        assert _build_invoice_default_actions(job)[0]["item_name"] == "Faktura: Flat AB"

    # column_values ---

    def test_column_values_source_is_invoice(self):
        job = _invoice_job()
        cv = _build_invoice_default_actions(job)[0]["column_values"]
        assert cv["source"] == "invoice"

    def test_column_values_contains_subject_when_present(self):
        job = _invoice_job({"subject": "Faktura mars 2026"})
        cv = _build_invoice_default_actions(job)[0]["column_values"]
        assert cv["subject"] == "Faktura mars 2026"

    def test_column_values_subject_truncated_at_60(self):
        job = _invoice_job({"subject": "F" * 80})
        cv = _build_invoice_default_actions(job)[0]["column_values"]
        assert len(cv["subject"]) <= 60

    def test_column_values_omits_subject_when_absent(self):
        job = _invoice_job({})
        cv = _build_invoice_default_actions(job)[0]["column_values"]
        assert "subject" not in cv

    def test_column_values_contains_email_when_present(self):
        job = _invoice_job({"sender": {"email": "lev@ex.com"}})
        cv = _build_invoice_default_actions(job)[0]["column_values"]
        assert cv["email"] == "lev@ex.com"

    def test_column_values_omits_email_when_absent(self):
        job = _invoice_job({})
        cv = _build_invoice_default_actions(job)[0]["column_values"]
        assert "email" not in cv

    # create_internal_task ---

    def test_internal_task_title_contains_sender_label(self):
        job = _invoice_job({"sender": {"name": "Leverantör AB"}})
        task = _build_invoice_default_actions(job)[1]
        assert "Leverantör AB" in task["title"]

    def test_internal_task_description_contains_sender_label(self):
        job = _invoice_job({"sender": {"email": "lev@ex.com"}})
        task = _build_invoice_default_actions(job)[1]
        assert "lev@ex.com" in task["description"]

    def test_internal_task_description_contains_subject_when_present(self):
        job = _invoice_job({"subject": "Faktura #99", "sender": {"email": "x@x.com"}})
        task = _build_invoice_default_actions(job)[1]
        assert "Faktura #99" in task["description"]

    def test_internal_task_metadata_job_id(self):
        job = _invoice_job({})
        job.job_id = "inv-job-1"
        task = _build_invoice_default_actions(job)[1]
        assert task["metadata"]["job_id"] == "inv-job-1"

    def test_internal_task_metadata_tenant_id(self):
        job = _invoice_job({})
        task = _build_invoice_default_actions(job)[1]
        assert task["metadata"]["tenant_id"] == "TENANT_1001"

    def test_internal_task_metadata_detected_job_type(self):
        job = _invoice_job({})
        task = _build_invoice_default_actions(job)[1]
        assert task["metadata"]["detected_job_type"] == "invoice"


# ── _build_fallback_actions routing ──────────────────────────────────────────

class TestFallbackActionRouting:
    def test_invoice_gets_invoice_defaults(self):
        job = _invoice_job({"subject": "Faktura"})
        types = [a["type"] for a in _build_fallback_actions(job)]
        assert "create_monday_item" in types
        assert "create_internal_task" in types

    def test_invoice_monday_item_source_is_invoice(self):
        job = _invoice_job({"subject": "Faktura"})
        monday = next(
            a for a in _build_fallback_actions(job) if a["type"] == "create_monday_item"
        )
        assert monday["column_values"]["source"] == "invoice"

    def test_inquiry_still_gets_inquiry_defaults(self):
        job = _inquiry_job({"subject": "Support fråga"})
        types = [a["type"] for a in _build_fallback_actions(job)]
        assert "send_email" in types

    def test_inquiry_monday_source_is_inquiry_not_invoice(self):
        job = _inquiry_job({"subject": "Fråga"})
        monday = next(
            (a for a in _build_fallback_actions(job) if a["type"] == "create_monday_item"),
            None,
        )
        if monday:
            assert monday["column_values"]["source"] == "inquiry"

    def test_lead_does_not_get_invoice_defaults(self):
        job = _lead_job({"subject": "Offert"})
        for action in _build_fallback_actions(job):
            cv = action.get("column_values", {})
            assert cv.get("source") != "invoice"


# ── _resolve_actions override behaviour ──────────────────────────────────────

class TestResolveActions:
    def test_invoice_without_input_actions_gets_defaults(self):
        job = _invoice_job({"subject": "Faktura #1", "sender": {"email": "x@x.com"}})
        types = [a["type"] for a in _resolve_actions(job)]
        assert "create_monday_item" in types
        assert "create_internal_task" in types

    def test_invoice_with_input_actions_uses_override(self):
        override = [{"type": "notify_slack", "channel": "#finance", "message": "Invoice in"}]
        job = _invoice_job({"subject": "Faktura", "actions": override})
        actions = _resolve_actions(job)
        assert len(actions) == 1
        assert actions[0]["type"] == "notify_slack"

    def test_invoice_with_decisioning_actions_uses_decisioning(self):
        job = _invoice_job({"subject": "Faktura"})
        job.processor_history.append({
            "processor": "decisioning_processor",
            "result": {
                "payload": {
                    "actions": [{"type": "send_email", "to": "finance@co.com", "subject": "X", "body": "Y"}]
                }
            },
        })
        actions = _resolve_actions(job)
        assert len(actions) == 1
        assert actions[0]["type"] == "send_email"


# ── process_action_dispatch_job (end-to-end, mocked execute_action) ──────────

class TestProcessActionDispatch:
    def _run(self, job: Job) -> Job:
        with patch(
            "app.workflows.processors.action_dispatch_processor.execute_action",
            return_value={"status": "success", "type": "stub"},
        ):
            return process_action_dispatch_job(job, db=None)

    def test_invoice_default_actions_both_in_requested(self):
        job = _invoice_job({"subject": "Faktura #5", "sender": {"name": "AB Bygg"}})
        result = self._run(job)
        types = [a.get("type") for a in result.result["payload"]["actions_requested"]]
        assert "create_monday_item" in types
        assert "create_internal_task" in types

    def test_invoice_with_override_executes_override_only(self):
        override = [{"type": "notify_slack", "channel": "#finance", "message": "m"}]
        job = _invoice_job({"actions": override})
        result = self._run(job)
        types = [a.get("type") for a in result.result["payload"]["actions_requested"]]
        assert types == ["notify_slack"]

    def test_status_completed_when_all_succeed(self):
        job = _invoice_job({"subject": "Faktura"})
        result = self._run(job)
        assert result.result["status"] == "completed"

    def test_inquiry_still_dispatches_correctly(self):
        job = _inquiry_job({"subject": "Fråga"})
        result = self._run(job)
        types = [a.get("type") for a in result.result["payload"]["actions_requested"]]
        assert "create_monday_item" in types
        assert "send_email" in types

    def test_lead_does_not_dispatch_invoice_actions(self):
        job = _lead_job({"subject": "Offert"})
        result = self._run(job)
        for action in result.result["payload"]["actions_requested"]:
            cv = action.get("column_values", {})
            assert cv.get("source") != "invoice"
