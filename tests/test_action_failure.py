"""
Tests for action dispatch failure hardening.

Covers:
- action_dispatch_processor returns status="failed" when actions fail
- action_dispatch_processor emits audit event on failure
- orchestrator._finalize_success routes to FAILED (not MANUAL_REVIEW) on action dispatch failure
- failed action is persisted to action_executions
- job result contains error detail from failed actions
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.domain.workflows.statuses import JobStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_job(job_type: JobType = JobType.LEAD) -> Job:
    return Job(
        tenant_id="TENANT_1001",
        job_type=job_type,
        input_data={
            "subject": "Test lead",
            "message_text": "Hello",
            "owner_email": "owner@example.com",
        },
    )


def _job_with_action_dispatch_failure(failed_count: int = 1) -> Job:
    """Job whose processor_history includes a failed action_dispatch result."""
    job = _base_job()
    job.processor_history = [
        {
            "processor": "action_dispatch_processor",
            "result": {
                "status": "failed",
                "summary": "One or more actions failed during dispatch.",
                "requires_human_review": True,
                "payload": {
                    "processor_name": "action_dispatch_processor",
                    "actions_requested": [{"type": "send_email", "to": "bad-email"}],
                    "actions_executed": [],
                    "actions_failed": [
                        {
                            "type": "send_email",
                            "status": "failed",
                            "error": "Invalid email address",
                            "payload": {"type": "send_email", "to": "bad-email"},
                        }
                    ],
                    "executed_count": 0,
                    "failed_count": failed_count,
                    "recommended_next_step": "manual_review",
                },
            },
        }
    ]
    job.result = {
        "status": "failed",
        "requires_human_review": True,
        "payload": job.processor_history[0]["result"]["payload"],
    }
    return job


# ---------------------------------------------------------------------------
# action_dispatch_processor: result shape on failure
# ---------------------------------------------------------------------------

class TestActionDispatchProcessorFailure:

    def test_result_status_is_failed_when_action_raises(self):
        """When execute_action raises, result status must be 'failed', not 'completed'."""
        job = _base_job()
        job.input_data = {
            "actions": [{"type": "send_email", "to": "bad@bad.com"}],
        }

        with patch(
            "app.workflows.processors.action_dispatch_processor.execute_action",
            side_effect=Exception("SMTP error"),
        ), patch(
            "app.workflows.processors.action_dispatch_processor.ActionExecutionRepository"
        ), patch(
            "app.workflows.processors.action_dispatch_processor.create_audit_event"
        ):
            from app.workflows.processors.action_dispatch_processor import (
                process_action_dispatch_job,
            )
            result_job = process_action_dispatch_job(job, db=None)

        latest = next(
            r for r in reversed(result_job.processor_history)
            if r["processor"] == "action_dispatch_processor"
        )
        assert latest["result"]["status"] == "failed"

    def test_failed_count_and_error_in_payload(self):
        """failed_count and error string must be persisted in payload."""
        job = _base_job()
        job.input_data = {
            "actions": [{"type": "send_email", "to": "bad@bad.com"}],
        }

        with patch(
            "app.workflows.processors.action_dispatch_processor.execute_action",
            side_effect=Exception("Invalid recipient"),
        ), patch(
            "app.workflows.processors.action_dispatch_processor.ActionExecutionRepository"
        ), patch(
            "app.workflows.processors.action_dispatch_processor.create_audit_event"
        ):
            from app.workflows.processors.action_dispatch_processor import (
                process_action_dispatch_job,
            )
            result_job = process_action_dispatch_job(job, db=None)

        latest = next(
            r for r in reversed(result_job.processor_history)
            if r["processor"] == "action_dispatch_processor"
        )
        payload = latest["result"]["payload"]
        assert payload["failed_count"] == 1
        assert payload["executed_count"] == 0
        assert len(payload["actions_failed"]) == 1
        assert "Invalid recipient" in payload["actions_failed"][0]["error"]

    def test_audit_event_emitted_on_failure_when_db_provided(self):
        """An audit event must be created when actions fail and db is not None."""
        job = _base_job()
        job.input_data = {
            "actions": [{"type": "send_email", "to": "bad@bad.com"}],
        }
        mock_db = MagicMock()

        with patch(
            "app.workflows.processors.action_dispatch_processor.execute_action",
            side_effect=Exception("SMTP error"),
        ), patch(
            "app.workflows.processors.action_dispatch_processor.ActionExecutionRepository"
        ), patch(
            "app.workflows.processors.action_dispatch_processor.create_audit_event"
        ) as mock_audit:
            from app.workflows.processors.action_dispatch_processor import (
                process_action_dispatch_job,
            )
            process_action_dispatch_job(job, db=mock_db)

        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args.kwargs
        assert call_kwargs["action"] == "action_dispatch_failed"
        assert call_kwargs["status"] == "failed"
        assert call_kwargs["details"]["failed_count"] == 1

    def test_no_audit_event_when_db_is_none(self):
        """No audit event should be attempted when db=None."""
        job = _base_job()
        job.input_data = {
            "actions": [{"type": "send_email", "to": "bad@bad.com"}],
        }

        with patch(
            "app.workflows.processors.action_dispatch_processor.execute_action",
            side_effect=Exception("SMTP error"),
        ), patch(
            "app.workflows.processors.action_dispatch_processor.ActionExecutionRepository"
        ), patch(
            "app.workflows.processors.action_dispatch_processor.create_audit_event"
        ) as mock_audit:
            from app.workflows.processors.action_dispatch_processor import (
                process_action_dispatch_job,
            )
            process_action_dispatch_job(job, db=None)

        mock_audit.assert_not_called()

    def test_no_audit_event_on_full_success(self):
        """No failure audit event when all actions succeed."""
        job = _base_job()
        job.input_data = {
            "actions": [{"type": "create_internal_task", "title": "Test"}],
        }

        with patch(
            "app.workflows.processors.action_dispatch_processor.execute_action",
            return_value={"type": "create_internal_task", "status": "completed"},
        ), patch(
            "app.workflows.processors.action_dispatch_processor.ActionExecutionRepository"
        ), patch(
            "app.workflows.processors.action_dispatch_processor.create_audit_event"
        ) as mock_audit:
            from app.workflows.processors.action_dispatch_processor import (
                process_action_dispatch_job,
            )
            process_action_dispatch_job(job, db=MagicMock())

        mock_audit.assert_not_called()

    def test_result_status_is_completed_on_full_success(self):
        """result status must be 'completed' when all actions succeed."""
        job = _base_job()
        job.input_data = {
            "actions": [{"type": "create_internal_task", "title": "Test"}],
        }

        with patch(
            "app.workflows.processors.action_dispatch_processor.execute_action",
            return_value={"type": "create_internal_task", "status": "completed"},
        ), patch(
            "app.workflows.processors.action_dispatch_processor.ActionExecutionRepository"
        ), patch(
            "app.workflows.processors.action_dispatch_processor.create_audit_event"
        ):
            from app.workflows.processors.action_dispatch_processor import (
                process_action_dispatch_job,
            )
            result_job = process_action_dispatch_job(job, db=None)

        latest = next(
            r for r in reversed(result_job.processor_history)
            if r["processor"] == "action_dispatch_processor"
        )
        assert latest["result"]["status"] == "completed"


# ---------------------------------------------------------------------------
# orchestrator._finalize_success: routes to FAILED on action dispatch failure
# ---------------------------------------------------------------------------

class TestOrchestratorActionDispatchFailureRouting:

    def _make_orchestrator(self):
        from app.workflows.orchestrator import WorkflowOrchestrator
        orch = WorkflowOrchestrator(db=None)
        return orch

    def test_finalize_success_routes_to_failed_when_action_dispatch_has_failures(self):
        """
        If the latest action_dispatch_processor result has failed_count > 0,
        _finalize_success must call _finalize_failure → job status = FAILED.
        """
        orch = self._make_orchestrator()
        job = _job_with_action_dispatch_failure(failed_count=1)

        result = orch._finalize_success(job, JobType.LEAD)

        assert result.status == JobStatus.FAILED

    def test_finalize_success_sets_failed_status_not_manual_review(self):
        """Ensure MANUAL_REVIEW is not used for action dispatch failures."""
        orch = self._make_orchestrator()
        job = _job_with_action_dispatch_failure(failed_count=1)

        result = orch._finalize_success(job, JobType.LEAD)

        assert result.status != JobStatus.MANUAL_REVIEW

    def test_finalize_success_error_in_result_when_action_dispatch_fails(self):
        """Failed job result must contain error detail from the failed actions."""
        orch = self._make_orchestrator()
        job = _job_with_action_dispatch_failure(failed_count=1)

        result = orch._finalize_success(job, JobType.LEAD)

        assert result.result is not None
        assert result.result.get("status") == "failed"
        error_str = result.result.get("payload", {}).get("error", "")
        assert "send_email" in error_str or "Invalid email address" in error_str

    def test_finalize_success_completes_normally_when_no_action_failures(self):
        """When failed_count == 0, _finalize_success proceeds as normal."""
        orch = self._make_orchestrator()
        job = _base_job()
        job.processor_history = [
            {
                "processor": "action_dispatch_processor",
                "result": {
                    "status": "completed",
                    "requires_human_review": False,
                    "payload": {
                        "processor_name": "action_dispatch_processor",
                        "executed_count": 1,
                        "failed_count": 0,
                        "actions_failed": [],
                    },
                },
            }
        ]
        job.result = {"status": "completed", "requires_human_review": False}

        result = orch._finalize_success(job, JobType.LEAD)

        assert result.status == JobStatus.COMPLETED

    def test_finalize_success_manual_review_still_works_without_action_dispatch(self):
        """
        requires_human_review from a non-action-dispatch processor
        (e.g. AI uncertainty) still routes to MANUAL_REVIEW.
        """
        orch = self._make_orchestrator()
        job = _base_job()
        job.processor_history = []  # no action_dispatch entry → failed_count = 0
        job.result = {"status": "completed", "requires_human_review": True}

        result = orch._finalize_success(job, JobType.LEAD)

        assert result.status == JobStatus.MANUAL_REVIEW
