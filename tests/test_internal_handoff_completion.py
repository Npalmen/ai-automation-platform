"""Tests for internal handoff completion, ready_cases, and daily summary metrics."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.domain.workflows.statuses import JobStatus
from app.reporting.daily_report import generate_daily_report
from app.workflows.approval_service import enrich_job_response_data
from app.workflows.email_approval_resolution import (
    INTERNAL_HANDOFF_ACTION,
    count_internal_handoffs_sent_since,
    finalize_email_approval_resolution,
)


def _internal_handoff_job(
    *,
    job_id: str | None = None,
    pending_in_processor: int = 1,
    approval_id: str = "eml_test_001",
) -> Job:
    return Job(
        job_id=job_id or f"job_{uuid.uuid4().hex[:8]}",
        tenant_id="TENANT_TEST",
        job_type=JobType.LEAD,
        status=JobStatus.AWAITING_APPROVAL,
        input_data={"subject": "Offertförfrågan", "sender_email": "kund@example.com"},
        result={"requires_human_review": False},
        processor_history=[
            {
                "processor": "action_dispatch_processor",
                "result": {
                    "status": "completed",
                    "payload": {
                        "processor_name": "action_dispatch_processor",
                        "pending_approval_count": pending_in_processor,
                        "actions_pending_approval": [
                            {
                                "approval_id": approval_id,
                                "type": INTERNAL_HANDOFF_ACTION,
                            }
                        ],
                        "actions_executed": [],
                    },
                },
            }
        ],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _approval_record(
    *,
    approval_id: str = "eml_test_001",
    job_id: str,
    delivery_type: str = INTERNAL_HANDOFF_ACTION,
):
    record = MagicMock()
    record.approval_id = approval_id
    record.tenant_id = "TENANT_TEST"
    record.job_id = job_id
    record.job_type = "lead"
    record.delivery_payload = {
        "type": delivery_type,
        "to": "ops@example.com",
        "subject": "Intern handoff",
        "body": "Sammanfattning",
    }
    return record


class TestFinalizeEmailApprovalResolution:
    def test_approved_internal_handoff_clears_stale_pending_state(self):
        job = _internal_handoff_job(pending_in_processor=1)
        approval = _approval_record(job_id=job.job_id)
        db = MagicMock()
        send_result = {
            "type": INTERNAL_HANDOFF_ACTION,
            "status": "executed",
            "target": "ops@example.com",
        }

        with (
            patch(
                "app.workflows.email_approval_resolution.JobRepository.get_job_by_id",
                return_value=job,
            ) as mock_get,
            patch(
                "app.workflows.email_approval_resolution.JobRepository.update_job",
                side_effect=lambda _db, updated: updated,
            ) as mock_update,
            patch(
                "app.workflows.email_approval_resolution.ApprovalRequestRepository.count_pending_for_job",
                return_value=0,
            ),
            patch(
                "app.workflows.email_approval_resolution.ActionExecutionRepository.list_for_job",
                return_value=[],
            ),
            patch(
                "app.workflows.email_approval_resolution.ActionExecutionRepository.create_from_executed_action"
            ) as mock_create_exec,
            patch("app.workflows.email_approval_resolution.create_audit_event"),
        ):
            result = finalize_email_approval_resolution(
                db,
                approval,
                approved=True,
                actor="operator",
                note=None,
                send_result=send_result,
                send_error=None,
            )

        mock_get.assert_called_once()
        mock_update.assert_called_once()
        mock_create_exec.assert_called_once()
        assert result.status == JobStatus.COMPLETED
        payload = result.processor_history[-1]["result"]["payload"]
        assert payload["pending_approval_count"] == 0
        assert payload["actions_pending_approval"] == []
        assert len(payload["actions_executed"]) == 1

        with patch(
            "app.repositories.postgres.approval_repository.ApprovalRequestRepository.count_pending_for_job",
            return_value=0,
        ):
            enriched = enrich_job_response_data(result, db=db)
        assert enriched["status"] == "completed"
        assert enriched["has_pending_approvals"] is False
        assert enriched["pending_approvals_count"] == 0

    def test_customer_case_not_marked_fully_resolved(self):
        job = _internal_handoff_job()
        approval = _approval_record(job_id=job.job_id)
        db = MagicMock()
        send_result = {"type": INTERNAL_HANDOFF_ACTION, "status": "executed"}

        with (
            patch(
                "app.workflows.email_approval_resolution.JobRepository.get_job_by_id",
                return_value=job,
            ),
            patch(
                "app.workflows.email_approval_resolution.JobRepository.update_job",
                side_effect=lambda _db, updated: updated,
            ),
            patch(
                "app.workflows.email_approval_resolution.ApprovalRequestRepository.count_pending_for_job",
                return_value=0,
            ),
            patch(
                "app.workflows.email_approval_resolution.ActionExecutionRepository.list_for_job",
                return_value=[],
            ),
            patch(
                "app.workflows.email_approval_resolution.ActionExecutionRepository.create_from_executed_action"
            ),
            patch("app.workflows.email_approval_resolution.create_audit_event"),
        ):
            result = finalize_email_approval_resolution(
                db,
                approval,
                approved=True,
                actor="operator",
                note=None,
                send_result=send_result,
                send_error=None,
            )

        assert result.result["customer_case_open"] is True
        assert result.result["automation_phase"] == "internal_handoff_sent"
        assert "Intern handoff skickad" in result.result["summary"]

    def test_failed_send_does_not_mark_handoff_completed(self):
        job = _internal_handoff_job()
        approval = _approval_record(job_id=job.job_id)
        db = MagicMock()

        with (
            patch(
                "app.workflows.email_approval_resolution.JobRepository.get_job_by_id",
                return_value=job,
            ),
            patch(
                "app.workflows.email_approval_resolution.JobRepository.update_job",
                side_effect=lambda _db, updated: updated,
            ),
            patch(
                "app.workflows.email_approval_resolution.ApprovalRequestRepository.count_pending_for_job",
                return_value=0,
            ),
            patch(
                "app.workflows.email_approval_resolution.ActionExecutionRepository.list_for_job",
                return_value=[],
            ),
            patch(
                "app.workflows.email_approval_resolution.ActionExecutionRepository.create_from_failed_action"
            ) as mock_failed,
            patch("app.workflows.email_approval_resolution.create_audit_event"),
        ):
            result = finalize_email_approval_resolution(
                db,
                approval,
                approved=True,
                actor="operator",
                note=None,
                send_result=None,
                send_error="Gmail unavailable",
            )

        mock_failed.assert_called_once()
        assert result.status == JobStatus.MANUAL_REVIEW
        assert result.result["requires_human_review"] is True
        assert "kunde inte skickas" in result.result["summary"]
        assert "internal_handoff_sent_at" not in result.result

    def test_retry_does_not_double_record_execution(self):
        job = _internal_handoff_job()
        approval = _approval_record(job_id=job.job_id)
        db = MagicMock()
        existing = MagicMock()
        existing.request_payload = {"approval_id": approval.approval_id}
        send_result = {"type": INTERNAL_HANDOFF_ACTION, "status": "executed"}

        with (
            patch(
                "app.workflows.email_approval_resolution.JobRepository.get_job_by_id",
                return_value=job,
            ),
            patch(
                "app.workflows.email_approval_resolution.JobRepository.update_job",
                side_effect=lambda _db, updated: updated,
            ),
            patch(
                "app.workflows.email_approval_resolution.ApprovalRequestRepository.count_pending_for_job",
                return_value=0,
            ),
            patch(
                "app.workflows.email_approval_resolution.ActionExecutionRepository.list_for_job",
                return_value=[existing],
            ),
            patch(
                "app.workflows.email_approval_resolution.ActionExecutionRepository.create_from_executed_action"
            ) as mock_create,
            patch("app.workflows.email_approval_resolution.create_audit_event"),
        ):
            finalize_email_approval_resolution(
                db,
                approval,
                approved=True,
                actor="operator",
                note=None,
                send_result=send_result,
                send_error=None,
            )

        mock_create.assert_not_called()


class TestReadyCasesSourceOfTruth:
    def test_ready_cases_uses_pending_approval_count(self):
        from app.main import _compute_summary

        db = MagicMock()
        scalar_values = iter([0, 0, 0, 0, 0])

        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.scalar.side_effect = lambda: next(scalar_values, 0)

        with patch(
            "app.main.ApprovalRequestRepository.count_pending_for_tenant",
            return_value=8,
        ) as mock_pending:
            summary = _compute_summary(db, "TENANT_TEST")

        mock_pending.assert_called_once_with(db, "TENANT_TEST")
        assert summary["ready_cases"] == 8

    def test_enrich_uses_db_count_when_processor_stale(self):
        job = _internal_handoff_job(pending_in_processor=1)
        job.status = JobStatus.COMPLETED
        db = MagicMock()

        with patch(
            "app.repositories.postgres.approval_repository.ApprovalRequestRepository.count_pending_for_job",
            return_value=0,
        ):
            data = enrich_job_response_data(job, db=db)

        assert data["status"] == "completed"
        assert data["pending_approvals_count"] == 0
        assert data["has_pending_approvals"] is False


class TestDailySummaryInternalHandoffs:
    def test_counts_successful_internal_handoff_once(self):
        mock_db = MagicMock()
        now = datetime.now(timezone.utc)

        with (
            patch("app.reporting.daily_report.JobRepository.list_jobs", return_value=[]),
            patch(
                "app.reporting.daily_report.ApprovalRequestRepository.count_pending_for_tenant",
                return_value=0,
            ),
            patch(
                "app.reporting.daily_report.count_internal_handoffs_sent_since",
                return_value=1,
            ),
        ):
            report = generate_daily_report(mock_db, tenant_id="TENANT_TEST", since_hours=24)

        assert report["counts"]["internal_handoffs_sent"] == 1
        assert "interna handoffs skickade" in report["rendered_text"]

    def test_internal_handoff_line_omitted_when_zero(self):
        mock_db = MagicMock()

        with (
            patch("app.reporting.daily_report.JobRepository.list_jobs", return_value=[]),
            patch(
                "app.reporting.daily_report.ApprovalRequestRepository.count_pending_for_tenant",
                return_value=0,
            ),
            patch(
                "app.reporting.daily_report.count_internal_handoffs_sent_since",
                return_value=0,
            ),
        ):
            report = generate_daily_report(mock_db, tenant_id="TENANT_TEST", since_hours=24)

        assert report["counts"]["internal_handoffs_sent"] == 0
        assert "interna handoffs skickade" not in report["rendered_text"]

    def test_count_internal_handoffs_uses_distinct_jobs(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.scalar.return_value = 2

        count = count_internal_handoffs_sent_since(
            db,
            tenant_id="TENANT_TEST",
            since=datetime.now(timezone.utc),
        )
        assert count == 2


class TestApprovalViaEmailDeferred:
    """Document current state: parser exists but Gmail intake is not wired."""

    def test_parser_recognizes_godkann(self):
        from app.workflows.approval_command_parser import parse_approval_command

        result = parse_approval_command("GODKÄNN\n\n> quoted reply")
        assert result["parsed"] is True
        assert result["command"] == "approve"

    def test_gmail_intake_does_not_import_parser(self):
        import app.main as main_module

        source = open(main_module.__file__, encoding="utf-8").read()
        assert "approval_command_parser" not in source
        assert "parse_approval_command" not in source
