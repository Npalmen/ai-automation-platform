"""Dispatch-boundary authorization regression tests (Kapitel 2B)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.workflows.processors.action_dispatch_processor import (
    _apply_dispatch_authorization,
    process_action_dispatch_job,
)


def _job_with_policy(job_type: JobType = JobType.LEAD, *, policy_decision: str = "auto_execute") -> Job:
    job = Job(
        job_id="job-auth-001",
        tenant_id="TENANT_1001",
        job_type=job_type,
        input_data={
            "subject": "Test",
            "message_text": "Hej, vill ha offert.",
            "sender": {"name": "Anna", "email": "anna@example.com"},
        },
    )
    detected = job_type.value if hasattr(job_type, "value") else str(job_type)
    job.processor_history = [
        {
            "processor": "policy_processor",
            "result": {
                "payload": {
                    "decision": policy_decision,
                    "detected_job_type": detected,
                }
            },
        }
    ]
    return job


class TestDispatchBoundaryAuthorization:
    def test_injected_monday_requires_approval_when_manual(self):
        job = _job_with_policy()
        job.input_data["actions"] = [
            {"type": "create_monday_item", "tenant_id": job.tenant_id, "item_name": "Lead: Anna"},
        ]
        settings = {"auto_actions": {"lead": "manual"}, "internal_notification_email": "ops@example.com"}
        actions = _apply_dispatch_authorization(job, job.input_data["actions"], settings)
        monday = next(a for a in actions if a.get("type") == "create_monday_item")
        assert monday.get("_needs_approval") is True

    def test_injected_unknown_action_blocked(self):
        job = _job_with_policy()
        actions = _apply_dispatch_authorization(
            job,
            [{"type": "totally_unknown_action"}],
            {"auto_actions": {"lead": "full_auto"}},
        )
        assert actions[0].get("_skip") is True
        assert actions[0].get("_skip_reason") == "action_blocked"

    def test_multi_action_creates_separate_approvals(self):
        job = _job_with_policy()
        db = MagicMock()
        created: list[str] = []

        def capture_approval(db, job, action, index):
            created.append(action["type"])
            return {"approval_id": f"act_{index}", "status": "pending_approval", "action_type": action["type"]}

        with (
            patch(
                "app.workflows.processors.action_dispatch_processor._read_automation_settings",
                return_value={
                    "followups_enabled": True,
                    "auto_actions": {"lead": False},
                    "internal_notification_email": "ops@example.com",
                },
            ),
            patch(
                "app.workflows.processors.action_dispatch_processor._resolve_actions",
                return_value=[
                    {"type": "send_customer_auto_reply", "tenant_id": job.tenant_id, "to": "anna@example.com", "subject": "Re", "body": "Hej"},
                    {"type": "create_monday_item", "tenant_id": job.tenant_id, "item_name": "Lead"},
                ],
            ),
            patch(
                "app.workflows.processors.action_dispatch_processor._create_action_approval_record",
                side_effect=capture_approval,
            ),
            patch("app.workflows.processors.action_dispatch_processor.execute_action") as mock_exec,
        ):
            process_action_dispatch_job(job, db)

        assert mock_exec.call_count == 0
        assert set(created) == {"send_customer_auto_reply", "create_monday_item"}
