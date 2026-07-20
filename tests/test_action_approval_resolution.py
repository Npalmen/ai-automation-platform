"""Kapitel 2D.1 per-action approval resolution tests."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.repositories.postgres.action_execution_models import ActionExecutionRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.decision_record_models import DecisionRecordRow
from app.repositories.postgres.decision_record_repository import DecisionRecordRepository
from app.repositories.postgres.job_models import JobRecord
from app.workflows.action_approval_resolution import resolve_per_action_approval
from app.workflows.decision_record import DecisionRecordType, ExecutionStatus
from app.workflows.decision_record_service import record_action_authorization
from app.workflows.decision_trace_errors import ReconciliationRequired
from app.workflows.pipeline_run_context import PipelineRunSource, create_trace_session


@pytest.fixture()
def approval_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    JobRecord.__table__.create(engine, checkfirst=True)
    ApprovalRequestRecord.__table__.create(engine, checkfirst=True)
    DecisionRecordRow.__table__.create(engine, checkfirst=True)
    ActionExecutionRecord.__table__.create(engine, checkfirst=True)
    AuditEventRecord.__table__.create(engine, checkfirst=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_decision_records_idempotency "
                "ON decision_records (tenant_id, idempotency_key)"
            )
        )

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

    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed_job(session, tenant_id: str, job_id: str) -> Job:
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    session.add(
        JobRecord(
            job_id=job_id,
            tenant_id=tenant_id,
            job_type="lead",
            status="awaiting_approval",
            input_data={"subject": "test"},
            result={"processor_history": []},
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    return Job(job_id=job_id, tenant_id=tenant_id, job_type=JobType.LEAD, input_data={})


def _seed_approval(session, *, tenant_id: str, job_id: str, operation_id: str, delivery: dict):
    approval_id = f"act_{uuid.uuid4().hex[:12]}"
    record = ApprovalRequestRecord(
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
            "action_type": delivery["type"],
        },
        delivery_payload=delivery,
        created_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        updated_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
    )
    session.add(record)
    session.commit()
    return record


def _seed_authorization(session, job: Job, action: dict, operation_id: str) -> str:
    trace = create_trace_session(job, source=PipelineRunSource.INTAKE, db=session)
    action = dict(action)
    action["_action_operation_id"] = operation_id
    record_action_authorization(
        session, trace, job, action, authorization="approval_required",
    )
    session.commit()
    rows = DecisionRecordRepository.list_for_job(session, tenant_id=job.tenant_id, job_id=job.job_id)
    assert rows
    return rows[0].pipeline_run_id


class TestActionApprovalResolution:
    def test_approve_writes_full_trace_chain(self, approval_db):
        tenant_id = "T_APPROVAL_TRACE"
        job_id = str(uuid.uuid4())
        operation_id = str(uuid.uuid4())
        delivery = {
            "type": "send_customer_auto_reply",
            "to": "c@example.com",
            "subject": "Hej",
            "body": "Tack",
            "tenant_id": tenant_id,
        }
        job = _seed_job(approval_db, tenant_id, job_id)
        auth_run = _seed_authorization(approval_db, job, delivery, operation_id)
        approval = _seed_approval(
            approval_db, tenant_id=tenant_id, job_id=job_id,
            operation_id=operation_id, delivery=delivery,
        )

        with (
            patch("app.workflows.action_executor._integration_allowed_for_action", return_value=True),
            patch("app.workflows.action_executor.is_integration_configured", return_value=True),
            patch("app.workflows.action_executor.get_integration_connection_config", return_value={"configured": True}),
            patch("app.workflows.action_executor.get_integration_adapter") as mock_adapter,
            patch("app.workflows.email_approval_resolution.finalize_email_approval_resolution"),
        ):
            mock_adapter.return_value.execute_action.return_value = {
                "provider": "gmail",
                "message_id": "m1",
            }
            with patch.dict("os.environ", {"DECISION_RECORD_ENFORCE_WRITES": "true"}):
                from app.core.settings import get_settings
                get_settings.cache_clear()
                result = resolve_per_action_approval(
                    approval_db, approval, approved=True, actor="op",
                )
                get_settings.cache_clear()

        assert result.approval_state == "approved"
        assert result.execution_state == ExecutionStatus.SUCCEEDED.value
        assert result.action_operation_id == operation_id
        assert result.contract_conflict is None

        rows = DecisionRecordRepository.list_for_job(approval_db, tenant_id=tenant_id, job_id=job_id)
        types = {r.record_type for r in rows}
        assert DecisionRecordType.ACTION_AUTHORIZATION.value in types
        assert DecisionRecordType.ACTION_APPROVAL_RESOLUTION.value in types
        assert DecisionRecordType.EXECUTION_INTENT.value in types
        assert DecisionRecordType.EXECUTION_OUTCOME.value in types

        auth_row = next(r for r in rows if r.record_type == "action_authorization")
        resume_rows = [r for r in rows if r.pipeline_run_id != auth_row.pipeline_run_id]
        assert resume_rows
        assert all(r.parent_pipeline_run_id == auth_run for r in resume_rows if r.parent_pipeline_run_id)

    def test_contract_conflict_keeps_pending(self, approval_db):
        tenant_id = "T_CONFLICT"
        job_id = str(uuid.uuid4())
        delivery = {"type": "send_email", "to": "a@b.com", "tenant_id": tenant_id}
        job = _seed_job(approval_db, tenant_id, job_id)
        approval = _seed_approval(
            approval_db, tenant_id=tenant_id, job_id=job_id,
            operation_id=str(uuid.uuid4()), delivery=delivery,
        )
        result = resolve_per_action_approval(approval_db, approval, approved=True)
        assert result.contract_conflict
        assert result.approval_state == "pending"
        reloaded = approval_db.get(ApprovalRequestRecord, approval.approval_id)
        assert reloaded is not None
        assert reloaded.state == "pending"

    def test_double_approve_is_idempotent(self, approval_db):
        tenant_id = "T_IDEM"
        job_id = str(uuid.uuid4())
        operation_id = str(uuid.uuid4())
        delivery = {
            "type": "send_customer_auto_reply",
            "to": "c@example.com",
            "subject": "Hej",
            "body": "Tack",
            "tenant_id": tenant_id,
        }
        job = _seed_job(approval_db, tenant_id, job_id)
        _seed_authorization(approval_db, job, delivery, operation_id)
        approval = _seed_approval(
            approval_db, tenant_id=tenant_id, job_id=job_id,
            operation_id=operation_id, delivery=delivery,
        )
        adapter_calls = {"n": 0}

        def _adapter(*_a, **_k):
            adapter_calls["n"] += 1
            mock = MagicMock()
            mock.execute_action.return_value = {"provider": "gmail", "message_id": "m1"}
            return mock

        with (
            patch("app.workflows.action_executor._integration_allowed_for_action", return_value=True),
            patch("app.workflows.action_executor.is_integration_configured", return_value=True),
            patch("app.workflows.action_executor.get_integration_connection_config", return_value={"configured": True}),
            patch("app.workflows.action_executor.get_integration_adapter", side_effect=_adapter),
            patch("app.workflows.email_approval_resolution.finalize_email_approval_resolution"),
        ):
            resolve_per_action_approval(approval_db, approval, approved=True)
            second = resolve_per_action_approval(approval_db, approval, approved=True)

        assert second.idempotent
        assert adapter_calls["n"] == 1

    def test_pending_intent_blocks_blind_retry(self, approval_db):
        tenant_id = "T_PENDING"
        job_id = str(uuid.uuid4())
        operation_id = str(uuid.uuid4())
        delivery = {
            "type": "send_customer_auto_reply",
            "to": "c@example.com",
            "subject": "Hej",
            "body": "Tack",
            "tenant_id": tenant_id,
        }
        job = _seed_job(approval_db, tenant_id, job_id)
        _seed_authorization(approval_db, job, delivery, operation_id)
        approval = _seed_approval(
            approval_db, tenant_id=tenant_id, job_id=job_id,
            operation_id=operation_id, delivery=delivery,
        )

        with patch(
            "app.workflows.action_approval_resolution._commit_pre_adapter_phase",
            side_effect=ReconciliationRequired("simulated crash after intent"),
        ):
            with pytest.raises(ReconciliationRequired):
                resolve_per_action_approval(approval_db, approval, approved=True)

        reloaded = approval_db.get(ApprovalRequestRecord, approval.approval_id)
        assert reloaded is not None
        assert reloaded.state == "pending"
