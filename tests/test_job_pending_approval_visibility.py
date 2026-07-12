"""
Regression tests for job pending-approval visibility in API responses and orchestrator.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.domain.workflows.statuses import JobStatus
from app.workflows.approval_service import (
    action_dispatch_pending_approval_count,
    enrich_job_response_data,
    has_pending_approval,
)
from app.workflows.orchestrator import WorkflowOrchestrator


def _job_with_action_dispatch_pending(count: int = 1) -> Job:
    return Job(
        job_id=f"job_{uuid.uuid4().hex[:8]}",
        tenant_id="TENANT_TEST",
        job_type=JobType.LEAD,
        status=JobStatus.COMPLETED,
        input_data={},
        result={"status": "completed"},
        processor_history=[
            {
                "processor": "action_dispatch_processor",
                "result": {
                    "status": "completed",
                    "payload": {
                        "processor_name": "action_dispatch_processor",
                        "pending_approval_count": count,
                        "actions_pending_approval": [{"approval_id": "eml_1"}] if count else [],
                    },
                },
            }
        ],
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


class TestPendingApprovalDetection:
    def test_has_pending_approval_from_action_dispatch(self):
        job = _job_with_action_dispatch_pending(2)
        assert has_pending_approval(job) is True
        assert action_dispatch_pending_approval_count(job) == 2

    def test_has_pending_approval_false_without_dispatch_pending(self):
        job = _job_with_action_dispatch_pending(0)
        job.processor_history = []
        assert has_pending_approval(job) is False


class TestJobResponseEnrichment:
    def test_enrich_sets_awaiting_approval_status(self):
        job = _job_with_action_dispatch_pending(1)
        data = enrich_job_response_data(job, db=None)

        assert data["status"] == "awaiting_approval"
        assert data["has_pending_approvals"] is True
        assert data["pending_approvals_count"] == 1

    def test_enrich_uses_db_pending_count_when_higher(self):
        job = _job_with_action_dispatch_pending(0)
        db = MagicMock()

        with patch(
            "app.repositories.postgres.approval_repository.ApprovalRequestRepository.count_pending_for_job",
            return_value=2,
        ):
            data = enrich_job_response_data(job, db=db)

        assert data["status"] == "awaiting_approval"
        assert data["pending_approvals_count"] == 2


class TestOrchestratorFinalizePendingApproval:
    def test_finalize_success_sets_awaiting_approval_when_emails_pending(self):
        orch = WorkflowOrchestrator(db=None)
        job = _job_with_action_dispatch_pending(1)

        result = orch._finalize_success(job, JobType.LEAD)

        assert result.status == JobStatus.AWAITING_APPROVAL
