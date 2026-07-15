"""Tests for Gmail manual-review operator handoff."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.domain.workflows.statuses import JobStatus
from app.reporting.daily_report import generate_daily_report
from app.workflows.manual_review_handoff import (
    MANUAL_REVIEW_GMAIL_LABEL,
    apply_manual_review_handoff,
    build_manual_review_reason,
    extract_gmail_message_id,
    get_handoff_state,
    is_unresolved_manual_review,
    job_needs_manual_review_handoff,
    post_pipeline_gmail_message_outcome,
    resolve_manual_review_job,
)


def _gmail_job(
    *,
    job_id: str = "job-1",
    tenant_id: str = "TENANT_A",
    status: JobStatus = JobStatus.MANUAL_REVIEW,
    message_id: str = "gmail-msg-1",
    processor_history: list | None = None,
) -> Job:
    return Job(
        job_id=job_id,
        tenant_id=tenant_id,
        job_type=JobType.CUSTOMER_INQUIRY,
        status=status,
        input_data={
            "subject": "Det luktar bränt",
            "message_text": "Hej, det luktar bränt vid elskåpet.",
            "sender": {"name": "Sara", "email": "sara@example.com"},
            "source": {
                "system": "gmail",
                "message_id": message_id,
                "thread_id": "thread-1",
            },
        },
        processor_history=processor_history
        or [
            {
                "processor": "human_handoff_processor",
                "result": {
                    "payload": {
                        "reason_codes": ["risk:safety_risk"],
                        "human_summary": "Safety risk detected",
                    }
                },
            }
        ],
        result={"requires_human_review": True},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _mock_gmail_adapter():
    adapter = MagicMock()
    adapter.client.ensure_label.return_value = "Label_123"
    adapter.client.modify_message_labels.return_value = None
    adapter.client.find_label_id.return_value = "Label_123"
    adapter.client.mark_as_read.return_value = None
    adapter.execute_action.side_effect = lambda action, payload: {
        "status": "success",
        "action": action,
        **payload,
    }
    return adapter


class TestManualReviewReasonAndSource:
    def test_extract_gmail_message_id_from_source(self):
        job = _gmail_job()
        assert extract_gmail_message_id(job) == "gmail-msg-1"

    def test_missing_gmail_source_returns_none(self):
        job = _gmail_job()
        job.input_data = {"subject": "x"}
        assert extract_gmail_message_id(job) is None

    def test_safety_risk_reason_from_human_handoff(self):
        job = _gmail_job()
        reason, codes = build_manual_review_reason(job)
        assert "risk:safety_risk" in codes
        assert reason

    def test_complaint_reason_codes(self):
        job = _gmail_job(
            processor_history=[
                {
                    "processor": "human_handoff_processor",
                    "result": {
                        "payload": {
                            "reason_codes": ["risk:complaint"],
                            "human_summary": "Complaint case",
                        }
                    },
                }
            ]
        )
        _, codes = build_manual_review_reason(job)
        assert codes == ["risk:complaint"]


class TestApplyManualReviewHandoff:
    def test_safety_job_applies_unread_and_label(self):
        job = _gmail_job()
        db = MagicMock()
        adapter = _mock_gmail_adapter()

        with patch(
            "app.workflows.manual_review_handoff.JobRepository.update_job",
            side_effect=lambda db, j: j,
        ), patch(
            "app.workflows.manual_review_handoff.create_audit_event",
        ), patch(
            "app.workflows.action_executor.execute_action",
            return_value={"status": "success"},
        ):
            result = apply_manual_review_handoff(db, job, adapter=adapter, notify=True)

        assert result["applied"] is True
        adapter.client.ensure_label.assert_called_once_with(MANUAL_REVIEW_GMAIL_LABEL)
        adapter.client.modify_message_labels.assert_called_once_with(
            "gmail-msg-1",
            add_label_ids=["UNREAD", "Label_123"],
        )
        handoff = get_handoff_state(result["job"])
        assert handoff["gmail_handoff_complete"] is True
        assert handoff["manual_review_reason_codes"] == ["risk:safety_risk"]

    def test_missing_gmail_message_id_fails_closed(self):
        job = _gmail_job()
        job.input_data.pop("source")
        db = MagicMock()
        result = apply_manual_review_handoff(db, job, adapter=_mock_gmail_adapter())
        assert result["fail_closed"] is True
        assert result["applied"] is False

    def test_idempotent_second_apply_skips_gmail_api(self):
        job = _gmail_job()
        job.result = {
            "manual_review_handoff": {
                "gmail_message_id": "gmail-msg-1",
                "gmail_handoff_complete": True,
                "gmail_label_applied": True,
                "gmail_marked_unread": True,
            }
        }
        db = MagicMock()
        adapter = _mock_gmail_adapter()

        with patch(
            "app.workflows.manual_review_handoff.JobRepository.update_job",
            side_effect=lambda db, j: j,
        ), patch("app.workflows.manual_review_handoff.create_audit_event"):
            result = apply_manual_review_handoff(db, job, adapter=adapter, notify=False)

        assert result["idempotent"] is True
        adapter.client.ensure_label.assert_not_called()
        adapter.client.modify_message_labels.assert_not_called()

    def test_normal_completed_job_does_not_need_handoff(self):
        job = _gmail_job(status=JobStatus.COMPLETED)
        assert job_needs_manual_review_handoff(job) is False


class TestPostPipelineGmailOutcome:
    def test_manual_review_skips_mark_as_read(self):
        job = _gmail_job(status=JobStatus.MANUAL_REVIEW)
        adapter = _mock_gmail_adapter()
        db = MagicMock()

        with patch(
            "app.workflows.manual_review_handoff.apply_manual_review_handoff",
            return_value={"applied": True, "job": job},
        ) as apply_mock:
            outcome = post_pipeline_gmail_message_outcome(
                db, "TENANT_A", job, "gmail-msg-1", adapter
            )

        apply_mock.assert_called_once()
        assert outcome["manual_review_handoff"] is True
        assert outcome["marked_handled"] is False
        adapter.execute_action.assert_not_called()

    def test_completed_job_marks_read(self):
        job = _gmail_job(status=JobStatus.COMPLETED)
        job.result = {"requires_human_review": False}
        adapter = _mock_gmail_adapter()

        outcome = post_pipeline_gmail_message_outcome(
            MagicMock(), "TENANT_A", job, "gmail-msg-1", adapter
        )

        adapter.execute_action.assert_called_once_with(
            action="mark_as_read",
            payload={"message_id": "gmail-msg-1"},
        )
        assert outcome["marked_handled"] is True


class TestResolveManualReview:
    def test_resolve_removes_label_and_records_audit(self):
        job = _gmail_job()
        job.result = {
            "manual_review_handoff": {
                "gmail_message_id": "gmail-msg-1",
                "gmail_handoff_complete": True,
            }
        }
        db = MagicMock()
        adapter = _mock_gmail_adapter()

        with patch(
            "app.workflows.manual_review_handoff.JobRepository.update_job",
            side_effect=lambda db, j: j,
        ), patch(
            "app.workflows.manual_review_handoff.create_audit_event",
        ) as audit_mock:
            result = resolve_manual_review_job(
                db,
                job,
                actor="niklas",
                note="handled",
                mark_gmail_read=True,
                adapter=adapter,
            )

        assert result["status"] == "resolved"
        assert result["job"].status == JobStatus.COMPLETED
        adapter.client.modify_message_labels.assert_called()
        adapter.client.mark_as_read.assert_called_once_with("gmail-msg-1")
        audit_mock.assert_called_once()
        assert not is_unresolved_manual_review(result["job"])

    def test_resolve_is_idempotent(self):
        job = _gmail_job(status=JobStatus.COMPLETED)
        job.result = {
            "manual_review_handoff": {
                "resolved_at": "2026-01-01T00:00:00+00:00",
            }
        }
        result = resolve_manual_review_job(MagicMock(), job)
        assert result["status"] == "already_resolved"


class TestTenantIsolation:
    def test_resolve_uses_job_tenant_only(self):
        job = _gmail_job(tenant_id="TENANT_A")
        job.result = {
            "manual_review_handoff": {
                "gmail_message_id": "gmail-msg-1",
                "gmail_handoff_complete": True,
            }
        }
        db = MagicMock()

        with patch(
            "app.workflows.manual_review_handoff.JobRepository.update_job",
            side_effect=lambda db, j: j,
        ), patch(
            "app.workflows.manual_review_handoff.create_audit_event",
        ) as audit_mock, patch(
            "app.workflows.manual_review_handoff._get_gmail_adapter",
            return_value=_mock_gmail_adapter(),
        ):
            resolve_manual_review_job(db, job)

        audit_mock.assert_called_once()
        assert audit_mock.call_args.kwargs["tenant_id"] == "TENANT_A"


class TestDailySummaryIncludesManualReview:
    def test_unresolved_manual_review_counted(self):
        job = _gmail_job()
        db = MagicMock()
        with patch(
            "app.reporting.daily_report.JobRepository.list_jobs",
            return_value=[job],
        ), patch(
            "app.reporting.daily_report.ApprovalRequestRepository.count_pending_for_tenant",
            return_value=0,
        ):
            report = generate_daily_report(db, tenant_id="TENANT_A", since_hours=24)

        assert report["counts"]["unresolved_manual_review"] == 1
        assert "manuell granskning" in report["rendered_text"]


class TestNoCustomerEmailOnHandoff:
    def test_apply_does_not_send_customer_email(self):
        job = _gmail_job()
        db = MagicMock()
        adapter = _mock_gmail_adapter()

        with patch(
            "app.workflows.manual_review_handoff.JobRepository.update_job",
            side_effect=lambda db, j: j,
        ), patch(
            "app.workflows.manual_review_handoff.create_audit_event",
        ), patch(
            "app.workflows.action_executor.execute_action",
            return_value={"status": "success"},
        ) as exec_mock:
            apply_manual_review_handoff(db, job, adapter=adapter, notify=True)

        assert all(
            call.args[0].get("type") != "send_customer_auto_reply"
            for call in exec_mock.call_args_list
        )
