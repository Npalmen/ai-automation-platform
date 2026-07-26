"""Regression tests for approval_dispatcher vs per-action approval rows."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.repositories.postgres.action_execution_models import ActionExecutionRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.approval_repository import ApprovalRequestRepository
from app.repositories.postgres.decision_record_models import DecisionRecordRow
from app.repositories.postgres.job_models import JobRecord
from app.workflows.approval_dispatcher import dispatch_approval_request
from app.workflows.approval_service import build_approval_request
from app.workflows.processors.ai_processor_utils import append_processor_result


@pytest.fixture()
def dispatcher_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    JobRecord.__table__.create(engine, checkfirst=True)
    ApprovalRequestRecord.__table__.create(engine, checkfirst=True)
    DecisionRecordRow.__table__.create(engine, checkfirst=True)
    ActionExecutionRecord.__table__.create(engine, checkfirst=True)
    AuditEventRecord.__table__.create(engine, checkfirst=True)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def test_dispatch_skips_db_upsert_when_per_action_pending(dispatcher_db):
    """Job-level dispatcher must not shadow per-action approval rows."""
    tenant_id = "T_DISPATCH"
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    dispatcher_db.add(
        JobRecord(
            job_id=job_id,
            tenant_id=tenant_id,
            job_type="lead",
            status="awaiting_approval",
            input_data={},
            result={"processor_history": []},
            created_at=now,
            updated_at=now,
        )
    )
    job = Job(job_id=job_id, tenant_id=tenant_id, job_type=JobType.LEAD, input_data={})

    per_action_id = f"act_{uuid.uuid4().hex[:12]}"
    dispatcher_db.add(
        ApprovalRequestRecord(
            approval_id=per_action_id,
            tenant_id=tenant_id,
            job_id=job_id,
            job_type="lead",
            state="pending",
            channel="dashboard",
            title="Per-action",
            summary="Reply",
            next_on_approve="action_execute",
            request_payload={"action_operation_id": str(uuid.uuid4())},
            delivery_payload={"type": "send_customer_auto_reply", "to": "a@b.com"},
            created_at=now,
            updated_at=now,
        )
    )
    dispatcher_db.commit()

    approval_request = build_approval_request(job)
    job = append_processor_result(
        job,
        "human_handoff_processor",
        {
            "status": "completed",
            "payload": {"approval_request": approval_request},
        },
    )
    job = append_processor_result(
        job,
        "action_dispatch_processor",
        {
            "status": "completed",
            "payload": {
                "actions_pending_approval": [{"approval_id": per_action_id}],
                "pending_approval_count": 1,
            },
        },
    )

    dispatch_approval_request(dispatcher_db, job)

    rows = ApprovalRequestRepository.list_for_job(dispatcher_db, tenant_id=tenant_id, job_id=job_id)
    assert len(rows) == 1
    assert rows[0].approval_id == per_action_id
    assert rows[0].next_on_approve == "action_execute"


def test_dispatch_materializes_per_action_before_job_level_upsert(dispatcher_db):
    """Trusted live-eval jobs materialize per-action rows before job-level fallback."""
    tenant_id = "T_MATERIALIZE"
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    dispatcher_db.add(
        JobRecord(
            job_id=job_id,
            tenant_id=tenant_id,
            job_type="lead",
            status="awaiting_approval",
            input_data={
                "subject": "Offert solceller",
                "message_text": "Hej, jag vill ha offert.",
                "sender": {"name": "Anna", "email": "anna@example.com"},
                "live_eval": {
                    "evaluation_run_id": "run-materialize",
                    "tenant_id": tenant_id,
                    "scenario_id": "TBSM01_lead_approve_reply",
                    "attempt_id": 1,
                    "transport_mode": "live_gmail",
                    "ai_mode": "fixture_ai",
                    "config_hash": "abc123",
                    "trusted": True,
                },
            },
            result={"processor_history": []},
            created_at=now,
            updated_at=now,
        )
    )
    job = Job(
        job_id=job_id,
        tenant_id=tenant_id,
        job_type=JobType.LEAD,
        input_data={
            "subject": "Offert solceller",
            "message_text": "Hej, jag vill ha offert.",
            "sender": {"name": "Anna", "email": "anna@example.com"},
            "live_eval": {
                "evaluation_run_id": "run-materialize",
                "tenant_id": tenant_id,
                "scenario_id": "TBSM01_lead_approve_reply",
                "attempt_id": 1,
                "transport_mode": "live_gmail",
                "ai_mode": "fixture_ai",
                "config_hash": "abc123",
                "trusted": True,
            },
        },
    )
    job.processor_history = [
        {
            "processor": "policy_processor",
            "result": {
                "payload": {
                    "decision": "send_for_approval",
                    "detected_job_type": "lead",
                    "recommended_next_step": "awaiting_approval",
                }
            },
        }
    ]

    approval_request = build_approval_request(job)
    job = append_processor_result(
        job,
        "human_handoff_processor",
        {
            "status": "completed",
            "payload": {"approval_request": approval_request},
        },
    )

    with (
        patch(
            "app.workflows.processors.action_dispatch_processor._read_automation_settings",
            return_value={
                "followups_enabled": True,
                "auto_actions": {"lead": "manual"},
                "internal_notification_email": "ops@example.com",
            },
        ),
        patch(
            "app.workflows.processors.action_dispatch_processor._compute_lead_sla_payload",
            return_value=None,
        ),
    ):
        dispatch_approval_request(dispatcher_db, job)

    rows = ApprovalRequestRepository.list_for_job(dispatcher_db, tenant_id=tenant_id, job_id=job_id)
    assert len(rows) >= 1
    assert any(row.next_on_approve == "action_execute" for row in rows)
    assert not any(row.next_on_approve == "action_dispatch" for row in rows)
