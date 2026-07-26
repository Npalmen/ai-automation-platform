"""HTTP regression tests for semi-auto approval resolution contract."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.decision_record_repository import DecisionRecordRepository
from app.repositories.postgres.job_models import JobRecord
from app.workflows.decision_record_service import record_action_authorization
from app.workflows.pipeline_run_context import PipelineRunSource, create_trace_session


@pytest.fixture()
def approval_db():
    from sqlalchemy import create_engine, event, text
    from sqlalchemy.orm import sessionmaker

    from app.repositories.postgres.action_execution_models import ActionExecutionRecord
    from app.repositories.postgres.audit_models import AuditEventRecord
    from app.repositories.postgres.decision_record_models import DecisionRecordRow

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


def _seed(approval_db, *, state: str = "pending"):
    tenant_id = "T_HTTP"
    job_id = str(uuid.uuid4())
    operation_id = str(uuid.uuid4())
    delivery = {
        "type": "send_customer_auto_reply",
        "to": "c@example.com",
        "subject": "Hej",
        "body": "Tack",
        "tenant_id": tenant_id,
    }
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    approval_db.add(
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
    trace = create_trace_session(job, source=PipelineRunSource.INTAKE, db=approval_db)
    action = dict(delivery)
    action["_action_operation_id"] = operation_id
    record_action_authorization(
        approval_db, trace, job, action, authorization="approval_required",
    )
    approval_id = f"act_{uuid.uuid4().hex[:12]}"
    approval_db.add(
        ApprovalRequestRecord(
            approval_id=approval_id,
            tenant_id=tenant_id,
            job_id=job_id,
            job_type="lead",
            state=state,
            channel="dashboard",
            title="Action",
            summary="Pending",
            next_on_approve="action_execute",
            request_payload={
                "approval_id": approval_id,
                "state": state,
                "action_operation_id": operation_id,
                "action_type": delivery["type"],
            },
            delivery_payload=delivery,
            created_at=now,
            updated_at=now,
        )
    )
    approval_db.commit()
    approval = approval_db.get(ApprovalRequestRecord, approval_id)
    return approval_db, approval


class TestSemiAutoApprovalHttp:
    def test_first_approve_writes_resolution_record(self, approval_db):
        db, approval = _seed(approval_db)
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
            from app.main import _resolve_email_approval

            result = _resolve_email_approval(db, approval, approved=True, actor="op")

        assert result["status"] == "approved"
        rows = DecisionRecordRepository.list_for_job(
            db, tenant_id=approval.tenant_id, job_id=approval.job_id,
        )
        assert any(r.record_type == "action_approval_resolution" for r in rows)

    def test_duplicate_approve_returns_idempotent(self, approval_db):
        db, approval = _seed(approval_db, state="approved")
        from app.main import _resolve_email_approval

        result = _resolve_email_approval(db, approval, approved=True, actor="op")
        assert result["idempotent"] is True
        assert result["status"] == "approved"

    def test_stale_approve_after_reject_returns_409(self, approval_db):
        db, approval = _seed(approval_db, state="rejected")
        from app.main import _resolve_email_approval

        with pytest.raises(HTTPException) as exc_info:
            _resolve_email_approval(db, approval, approved=True, actor="op")
        assert exc_info.value.status_code == 409

    def test_reject_writes_resolution_record(self, approval_db):
        db, approval = _seed(approval_db)
        with patch("app.workflows.email_approval_resolution.finalize_email_approval_resolution"):
            from app.main import _resolve_email_approval

            result = _resolve_email_approval(db, approval, approved=False, actor="op")

        assert result["status"] == "rejected"
        rows = DecisionRecordRepository.list_for_job(
            db, tenant_id=approval.tenant_id, job_id=approval.job_id,
        )
        assert any(r.record_type == "action_approval_resolution" for r in rows)
        assert not any(r.record_type == "execution_intent" for r in rows)

    def test_duplicate_reject_is_idempotent(self, approval_db):
        db, approval = _seed(approval_db, state="rejected")
        from app.main import _resolve_email_approval

        result = _resolve_email_approval(db, approval, approved=False, actor="op")
        assert result["idempotent"] is True
