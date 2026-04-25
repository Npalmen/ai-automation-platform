"""Tests for send_customer_auto_reply + send_internal_handoff actions."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.domain.workflows.enums import JobType
from app.domain.workflows.statuses import JobStatus
from app.domain.workflows.models import Job
from app.workflows.processors.action_dispatch_processor import (
    _build_inquiry_default_actions,
    _build_lead_default_actions,
    _build_skipped_action,
    process_action_dispatch_job,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_job(
    job_type: JobType = JobType.LEAD,
    input_data: dict | None = None,
    tenant_id: str = "TENANT_1001",
) -> Job:
    job = Job(
        job_id="job-test-001",
        tenant_id=tenant_id,
        job_type=job_type,
        status=JobStatus.PROCESSING,
        input_data=input_data or {
            "sender": {"name": "Test Person", "email": "test@example.com"},
            "subject": "Intresserad av solpaneler",
            "message_text": "Hej, jag vill ha offert.",
        },
    )
    return job


def _settings(
    followups_enabled: bool = True,
    leads_enabled: bool = True,
    support_enabled: bool = True,
    support_email: str = "internal@company.com",
) -> dict:
    return {
        "followups_enabled": followups_enabled,
        "leads_enabled": leads_enabled,
        "support_enabled": support_enabled,
        "support_email": support_email,
    }


# ---------------------------------------------------------------------------
# _build_skipped_action
# ---------------------------------------------------------------------------

class TestBuildSkippedAction:
    def test_has_skip_flag(self):
        result = _build_skipped_action("send_customer_auto_reply", "no_email")
        assert result["_skip"] is True

    def test_has_type(self):
        result = _build_skipped_action("send_internal_handoff", "reason")
        assert result["type"] == "send_internal_handoff"

    def test_has_reason(self):
        result = _build_skipped_action("send_customer_auto_reply", "followups_enabled=false")
        assert result["_skip_reason"] == "followups_enabled=false"


# ---------------------------------------------------------------------------
# _build_lead_default_actions
# ---------------------------------------------------------------------------

class TestLeadDefaultActions:
    def test_sends_customer_auto_reply_when_email_and_followups_enabled(self):
        job = _make_job()
        actions = _build_lead_default_actions(job, _settings())
        types = [a["type"] for a in actions]
        assert "send_customer_auto_reply" in types

    def test_auto_reply_not_skipped_when_conditions_met(self):
        job = _make_job()
        actions = _build_lead_default_actions(job, _settings())
        auto_reply = next(a for a in actions if a["type"] == "send_customer_auto_reply")
        assert not auto_reply.get("_skip")

    def test_sends_internal_handoff(self):
        job = _make_job()
        actions = _build_lead_default_actions(job, _settings())
        types = [a["type"] for a in actions]
        assert "send_internal_handoff" in types

    def test_internal_handoff_to_configured_email(self):
        job = _make_job()
        actions = _build_lead_default_actions(job, _settings(support_email="sales@company.com"))
        handoff = next(a for a in actions if a["type"] == "send_internal_handoff")
        assert handoff["to"] == "sales@company.com"

    def test_skips_auto_reply_when_followups_disabled(self):
        job = _make_job()
        actions = _build_lead_default_actions(job, _settings(followups_enabled=False))
        auto_reply = next(a for a in actions if a["type"] == "send_customer_auto_reply")
        assert auto_reply.get("_skip") is True
        assert "followups_enabled=false" in auto_reply["_skip_reason"]

    def test_skips_auto_reply_when_no_customer_email(self):
        job = _make_job(input_data={
            "sender": {"name": "No Email"},
            "subject": "Förfrågan",
            "message_text": "Text",
        })
        actions = _build_lead_default_actions(job, _settings())
        auto_reply = next(a for a in actions if a["type"] == "send_customer_auto_reply")
        assert auto_reply.get("_skip") is True
        assert "no_customer_email" in auto_reply["_skip_reason"]

    def test_auto_reply_to_is_sender_email(self):
        job = _make_job()
        actions = _build_lead_default_actions(job, _settings())
        auto_reply = next(a for a in actions if a["type"] == "send_customer_auto_reply")
        assert auto_reply["to"] == "test@example.com"

    def test_always_creates_monday_item(self):
        job = _make_job()
        actions = _build_lead_default_actions(job, _settings())
        types = [a["type"] for a in actions]
        assert "create_monday_item" in types

    def test_auto_reply_without_settings_uses_defaults(self):
        job = _make_job()
        actions = _build_lead_default_actions(job)
        types = [a["type"] for a in actions]
        assert "send_customer_auto_reply" in types
        assert "send_internal_handoff" in types


# ---------------------------------------------------------------------------
# _build_inquiry_default_actions
# ---------------------------------------------------------------------------

class TestInquiryDefaultActions:
    def test_sends_customer_auto_reply(self):
        job = _make_job(job_type=JobType.CUSTOMER_INQUIRY)
        actions = _build_inquiry_default_actions(job, _settings())
        types = [a["type"] for a in actions]
        assert "send_customer_auto_reply" in types

    def test_sends_internal_support_handoff(self):
        job = _make_job(job_type=JobType.CUSTOMER_INQUIRY)
        actions = _build_inquiry_default_actions(job, _settings())
        types = [a["type"] for a in actions]
        assert "send_internal_handoff" in types

    def test_handoff_to_configured_support_email(self):
        job = _make_job(job_type=JobType.CUSTOMER_INQUIRY)
        actions = _build_inquiry_default_actions(job, _settings(support_email="help@firm.com"))
        handoff = next(a for a in actions if a["type"] == "send_internal_handoff")
        assert handoff["to"] == "help@firm.com"

    def test_skips_auto_reply_when_followups_disabled(self):
        job = _make_job(job_type=JobType.CUSTOMER_INQUIRY)
        actions = _build_inquiry_default_actions(job, _settings(followups_enabled=False))
        auto_reply = next(a for a in actions if a["type"] == "send_customer_auto_reply")
        assert auto_reply.get("_skip") is True

    def test_skips_auto_reply_when_no_email(self):
        job = _make_job(
            job_type=JobType.CUSTOMER_INQUIRY,
            input_data={"sender": {}, "subject": "Fråga", "message_text": "Hej"},
        )
        actions = _build_inquiry_default_actions(job, _settings())
        auto_reply = next(a for a in actions if a["type"] == "send_customer_auto_reply")
        assert auto_reply.get("_skip") is True

    def test_always_creates_monday_item(self):
        job = _make_job(job_type=JobType.CUSTOMER_INQUIRY)
        actions = _build_inquiry_default_actions(job, _settings())
        assert any(a["type"] == "create_monday_item" for a in actions)


# ---------------------------------------------------------------------------
# process_action_dispatch_job — skipped actions in result
# ---------------------------------------------------------------------------

class TestProcessActionDispatchSkipped:
    def _mock_execute(self, action):
        return {
            "type": action["type"],
            "status": "executed",
            "executed_at": "2026-01-01T00:00:00+00:00",
            "target": action.get("to") or action.get("item_name"),
            "provider": "stub",
            "payload": action,
            "integration_result": {"ok": True},
        }

    def test_skipped_action_appears_in_result(self):
        job = _make_job(input_data={
            "sender": {"name": "A"},
            "subject": "S",
            "message_text": "M",
        })

        with patch(
            "app.workflows.processors.action_dispatch_processor._read_automation_settings"
        ) as mock_settings, patch(
            "app.workflows.processors.action_dispatch_processor.execute_action",
            side_effect=self._mock_execute,
        ):
            mock_settings.return_value = _settings(followups_enabled=False)
            result = process_action_dispatch_job(job, db=None)

        payload = result.processor_history[-1]["result"]["payload"]
        assert payload["skipped_count"] >= 1
        skipped_types = [a["type"] for a in payload["actions_skipped"]]
        assert "send_customer_auto_reply" in skipped_types

    def test_skipped_does_not_appear_in_executed(self):
        job = _make_job(input_data={
            "sender": {"name": "A"},
            "subject": "S",
            "message_text": "M",
        })

        with patch(
            "app.workflows.processors.action_dispatch_processor._read_automation_settings"
        ) as mock_settings, patch(
            "app.workflows.processors.action_dispatch_processor.execute_action",
            side_effect=self._mock_execute,
        ):
            mock_settings.return_value = _settings(followups_enabled=False)
            result = process_action_dispatch_job(job, db=None)

        payload = result.processor_history[-1]["result"]["payload"]
        executed_types = [a["type"] for a in payload["actions_executed"]]
        assert "send_customer_auto_reply" not in executed_types

    def test_skipped_persisted_with_skipped_status(self):
        job = _make_job(input_data={
            "sender": {"name": "A"},
            "subject": "S",
            "message_text": "M",
        })
        mock_db = MagicMock()

        with patch(
            "app.workflows.processors.action_dispatch_processor._read_automation_settings"
        ) as mock_settings, patch(
            "app.workflows.processors.action_dispatch_processor.execute_action",
            side_effect=self._mock_execute,
        ), patch(
            "app.workflows.processors.action_dispatch_processor.ActionExecutionRepository"
            ".create_from_executed_action"
        ) as mock_persist:
            mock_settings.return_value = _settings(followups_enabled=False)
            process_action_dispatch_job(job, db=mock_db)

        calls = mock_persist.call_args_list
        skipped_calls = [
            c for c in calls
            if c.kwargs.get("executed_action", {}).get("status") == "skipped"
        ]
        assert len(skipped_calls) >= 1


# ---------------------------------------------------------------------------
# Tenant isolation
# ---------------------------------------------------------------------------

class TestTenantIsolation:
    def test_settings_read_per_tenant(self):
        job_a = _make_job(tenant_id="TENANT_A")
        job_b = _make_job(tenant_id="TENANT_B")

        call_log: list[str] = []

        def fake_settings(job, db):
            call_log.append(job.tenant_id)
            return _settings()

        with patch(
            "app.workflows.processors.action_dispatch_processor._read_automation_settings",
            side_effect=fake_settings,
        ), patch(
            "app.workflows.processors.action_dispatch_processor.execute_action",
            return_value={"type": "x", "status": "executed", "executed_at": "", "target": None,
                          "provider": "stub", "payload": {}, "integration_result": {}},
        ):
            process_action_dispatch_job(job_a, db=None)
            process_action_dispatch_job(job_b, db=None)

        assert "TENANT_A" in call_log
        assert "TENANT_B" in call_log
