"""Regression tests for semi-auto per-action approval materialization."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.evaluation.live.observation import build_job_observation
from app.repositories.postgres.action_execution_models import ActionExecutionRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.approval_repository import ApprovalRequestRepository
from app.repositories.postgres.decision_record_models import DecisionRecordRow
from app.repositories.postgres.decision_record_repository import DecisionRecordRepository
from app.repositories.postgres.job_models import JobRecord
from app.workflows.action_approval_resolution import resolve_per_action_approval
from app.workflows.approval_dispatcher import dispatch_approval_request
from app.workflows.approval_service import build_approval_request
from app.workflows.decision_record_service import record_action_authorization
from app.workflows.decision_trace_errors import ContractConflict
from app.workflows.pipeline_run_context import PipelineRunSource, create_trace_session
from app.workflows.processors.action_dispatch_processor import (
    _apply_dispatch_authorization,
    process_action_dispatch_job,
)
from app.workflows.processors.ai_processor_utils import append_processor_result


def _sqlite_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    JobRecord.__table__.create(engine, checkfirst=True)
    ApprovalRequestRecord.__table__.create(engine, checkfirst=True)
    DecisionRecordRow.__table__.create(engine, checkfirst=True)
    AuditEventRecord.__table__.create(engine, checkfirst=True)
    ActionExecutionRecord.__table__.create(engine, checkfirst=True)

    @event.listens_for(DecisionRecordRow, "before_insert")
    def _assign_event_sequence(mapper, connection, target):
        if connection.dialect.name != "sqlite":
            return
        if getattr(target, "event_sequence", None) is None:
            result = connection.execute(
                DecisionRecordRow.__table__.select().with_only_columns(
                    DecisionRecordRow.event_sequence
                )
            )
            max_seq = 0
            for row in result:
                max_seq = max(max_seq, int(row[0] or 0))
            target.event_sequence = max_seq + 1

    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_decision_records_idempotency "
                "ON decision_records (tenant_id, idempotency_key)"
            )
        )
    return sessionmaker(bind=engine)()


def _lead_job(*, policy_decision: str = "send_for_approval") -> Job:
    job = Job(
        job_id=str(uuid.uuid4()),
        tenant_id="T_SEMI",
        job_type=JobType.LEAD,
        input_data={
            "subject": "Offert solceller",
            "message_text": "Hej, jag vill ha offert.",
            "sender": {"name": "Anna", "email": "anna@example.com"},
        },
    )
    job.processor_history = [
        {
            "processor": "policy_processor",
            "result": {
                "payload": {
                    "decision": policy_decision,
                    "detected_job_type": "lead",
                    "recommended_next_step": "awaiting_approval",
                }
            },
        }
    ]
    return job


def _seed_job_record(db, job: Job) -> None:
    now = datetime.now(timezone.utc)
    db.add(
        JobRecord(
            job_id=job.job_id,
            tenant_id=job.tenant_id,
            job_type="lead",
            status="processing",
            input_data=job.input_data,
            result={"processor_history": job.processor_history},
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()


class TestSendForApprovalDispatchMaterialization:
    def test_send_for_approval_queues_external_actions_for_approval(self):
        job = _lead_job()
        settings = {
            "auto_actions": {"lead": "manual"},
            "internal_notification_email": "ops@example.com",
            "followups_enabled": True,
        }
        actions = _apply_dispatch_authorization(
            job,
            [{"type": "send_customer_auto_reply", "to": "anna@example.com", "subject": "Hej", "body": "Tack"}],
            settings,
        )
        assert actions[0].get("_needs_approval") is True
        assert actions[0].get("_skip") is not True

    def test_action_dispatch_creates_per_action_approval_and_authorization(self):
        db = _sqlite_session()
        job = _lead_job()
        _seed_job_record(db, job)
        trace = create_trace_session(job, source=PipelineRunSource.INTAKE, db=db)

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
                "app.workflows.processors.action_dispatch_processor._resolve_actions",
                return_value=[
                    {
                        "type": "send_customer_auto_reply",
                        "tenant_id": job.tenant_id,
                        "to": "anna@example.com",
                        "subject": "Hej",
                        "body": "Tack",
                    }
                ],
            ),
        ):
            updated = process_action_dispatch_job(job, db=db, trace=trace)

        payload = updated.result["payload"]
        assert payload["pending_approval_count"] == 1
        rows = ApprovalRequestRepository.list_for_job(db, tenant_id=job.tenant_id, job_id=job.job_id)
        assert len(rows) == 1
        assert rows[0].next_on_approve == "action_execute"
        assert rows[0].request_payload.get("action_operation_id")

        auth = DecisionRecordRepository.get_action_authorization(
            db,
            tenant_id=job.tenant_id,
            action_operation_id=rows[0].request_payload["action_operation_id"],
        )
        assert auth is not None
        assert auth.action_authorization == "approval_required"

        job_with_handoff = append_processor_result(
            updated,
            "human_handoff_processor",
            {
                "status": "completed",
                "payload": {"approval_request": build_approval_request(updated)},
            },
        )
        dispatch_approval_request(db, job_with_handoff)
        rows_after = ApprovalRequestRepository.list_for_job(
            db, tenant_id=job.tenant_id, job_id=job.job_id,
        )
        assert len(rows_after) == 1
        assert rows_after[0].next_on_approve == "action_execute"


class TestPerActionResolutionPersistence:
    def test_approve_writes_resolution_record_with_relations(self):
        db = _sqlite_session()
        tenant_id = "T_RES"
        job_id = str(uuid.uuid4())
        operation_id = str(uuid.uuid4())
        delivery = {
            "type": "send_customer_auto_reply",
            "to": "c@example.com",
            "subject": "Hej",
            "body": "Tack",
            "tenant_id": tenant_id,
        }
        now = datetime.now(timezone.utc)
        db.add(
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
        trace = create_trace_session(job, source=PipelineRunSource.INTAKE, db=db)
        action = dict(delivery)
        action["_action_operation_id"] = operation_id
        record_action_authorization(
            db, trace, job, action, authorization="approval_required",
        )
        approval_id = f"act_{uuid.uuid4().hex[:12]}"
        db.add(
            ApprovalRequestRecord(
                approval_id=approval_id,
                tenant_id=tenant_id,
                job_id=job_id,
                job_type="lead",
                state="pending",
                channel="dashboard",
                title="Action",
                summary="Pending",
                next_on_approve="action_execute",
                request_payload={
                    "approval_id": approval_id,
                    "state": "pending",
                    "action_operation_id": operation_id,
                },
                delivery_payload=delivery,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()

        approval = db.get(ApprovalRequestRecord, approval_id)
        with (
            patch(
                "app.workflows.action_executor._integration_allowed_for_action",
                return_value=True,
            ),
            patch(
                "app.workflows.action_executor.is_integration_configured",
                return_value=True,
            ),
            patch(
                "app.workflows.action_executor.get_integration_connection_config",
                return_value={"configured": True},
            ),
            patch(
                "app.workflows.action_executor.get_integration_adapter",
                return_value=MagicMock(
                    execute_action=MagicMock(return_value={"provider": "gmail", "message_id": "m1"})
                ),
            ),
            patch(
                "app.workflows.email_approval_resolution.finalize_email_approval_resolution",
            ),
        ):
            result = resolve_per_action_approval(db, approval, approved=True, actor="op")

        assert result.approval_state == "approved"
        db.commit()

        records = DecisionRecordRepository.list_for_job(db, tenant_id=tenant_id, job_id=job_id)
        resolution = next(r for r in records if r.record_type == "action_approval_resolution")
        assert resolution.tenant_id == tenant_id
        assert resolution.job_id == job_id
        assert resolution.action_operation_id == operation_id
        assert resolution.pipeline_run_id
        assert resolution.metadata_json["approval_id"] == approval_id

        observation = build_job_observation(db, tenant_id, job_id)
        trace_summary = observation["execution_trace"]
        assert trace_summary["approval_resolution"] is not None
        assert trace_summary["execution_intent"] is not None
        assert trace_summary["execution_outcome"] is not None

    def test_reject_writes_resolution_without_intent(self):
        db = _sqlite_session()
        tenant_id = "T_REJ"
        job_id = str(uuid.uuid4())
        operation_id = str(uuid.uuid4())
        delivery = {
            "type": "send_customer_auto_reply",
            "to": "c@example.com",
            "subject": "Hej",
            "body": "Tack",
            "tenant_id": tenant_id,
        }
        now = datetime.now(timezone.utc)
        db.add(
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
        trace = create_trace_session(job, source=PipelineRunSource.INTAKE, db=db)
        action = dict(delivery)
        action["_action_operation_id"] = operation_id
        record_action_authorization(
            db, trace, job, action, authorization="approval_required",
        )
        approval_id = f"act_{uuid.uuid4().hex[:12]}"
        db.add(
            ApprovalRequestRecord(
                approval_id=approval_id,
                tenant_id=tenant_id,
                job_id=job_id,
                job_type="lead",
                state="pending",
                channel="dashboard",
                title="Action",
                summary="Pending",
                next_on_approve="action_execute",
                request_payload={
                    "approval_id": approval_id,
                    "state": "pending",
                    "action_operation_id": operation_id,
                },
                delivery_payload=delivery,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()

        approval = db.get(ApprovalRequestRecord, approval_id)
        with patch(
            "app.workflows.email_approval_resolution.finalize_email_approval_resolution",
        ):
            result = resolve_per_action_approval(db, approval, approved=False, actor="op")
        assert result.approval_state == "rejected"
        records = DecisionRecordRepository.list_for_job(db, tenant_id=tenant_id, job_id=job_id)
        assert any(r.record_type == "action_approval_resolution" for r in records)
        assert not any(r.record_type == "execution_intent" for r in records)

    def test_approve_fails_closed_when_resolution_write_blocked(self):
        db = _sqlite_session()
        tenant_id = "T_FAIL"
        job_id = str(uuid.uuid4())
        operation_id = str(uuid.uuid4())
        delivery = {
            "type": "send_customer_auto_reply",
            "to": "c@example.com",
            "subject": "Hej",
            "body": "Tack",
            "tenant_id": tenant_id,
        }
        now = datetime.now(timezone.utc)
        db.add(
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
        trace = create_trace_session(job, source=PipelineRunSource.INTAKE, db=db)
        action = dict(delivery)
        action["_action_operation_id"] = operation_id
        record_action_authorization(
            db, trace, job, action, authorization="approval_required",
        )
        approval_id = f"act_{uuid.uuid4().hex[:12]}"
        db.add(
            ApprovalRequestRecord(
                approval_id=approval_id,
                tenant_id=tenant_id,
                job_id=job_id,
                job_type="lead",
                state="pending",
                channel="dashboard",
                title="Action",
                summary="Pending",
                next_on_approve="action_execute",
                request_payload={
                    "approval_id": approval_id,
                    "state": "pending",
                    "action_operation_id": operation_id,
                },
                delivery_payload=delivery,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        approval = db.get(ApprovalRequestRecord, approval_id)

        with (
            patch(
                "app.workflows.decision_record_service.append_record",
                return_value=None,
            ),
            patch(
                "app.core.settings.resolve_decision_record_enforce_writes",
                return_value=True,
            ),
        ):
            with pytest.raises(ContractConflict):
                resolve_per_action_approval(db, approval, approved=True, actor="op")
