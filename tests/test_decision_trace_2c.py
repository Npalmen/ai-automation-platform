"""Kapitel 2C decision trace tests."""

from __future__ import annotations

import threading
import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.settings import Settings, get_settings, validate_decision_record_settings
from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.repositories.postgres.database import Base
from app.repositories.postgres.decision_record_models import DecisionRecordRow
from app.repositories.postgres.decision_record_repository import DecisionRecordRepository
from app.workflows.action_fingerprint import FINGERPRINT_KEY_VERSION, compute_action_fingerprint
from app.workflows.decision_record import validate_metadata
from app.workflows.decision_record_service import (
    allocate_action_operation_id,
    append_record,
    record_action_authorization,
    record_execution_intent,
)
from app.workflows.decision_trace_errors import OperationConflict, ReconciliationRequired
from app.workflows.decision_trace_readiness import verify_decision_trace_readiness
from app.workflows.decision_record import DecisionRecordType, ExecutionStatus
from app.workflows.external_write_trace import execute_external_write_with_trace
from app.workflows.pipeline_run_context import (
    DecisionTraceSession,
    PipelineRunSource,
    create_trace_session,
)


@pytest.fixture()
def trace_db():
    from sqlalchemy import text

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    DecisionRecordRow.__table__.create(engine, checkfirst=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_decision_records_idempotency "
                "ON decision_records (tenant_id, idempotency_key)"
            )
        )
    # SQLite lacks PG identity — emulate monotonic event_sequence
    if "sqlite" in str(engine.url):
        from sqlalchemy import event

        @event.listens_for(DecisionRecordRow, "before_insert")
        def _assign_event_sequence(mapper, connection, target):
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


def _job(tenant_id: str = "TENANT_A") -> Job:
    return Job(
        job_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        job_type=JobType.LEAD,
        input_data={"subject": "Test", "message_text": "Hej"},
    )


def _trace(job: Job, db, source=PipelineRunSource.INTAKE) -> DecisionTraceSession:
    return create_trace_session(job, source=source, db=db)


class TestMetadataAllowlist:
    def test_rejects_raw_email_key(self):
        with pytest.raises(ValueError):
            validate_metadata({"body": "secret"})

    def test_accepts_allowlisted_keys(self):
        meta = validate_metadata({"approval_id": "appr_1", "action_operation_id": str(uuid.uuid4())})
        assert "approval_id" in meta


class TestActionOperationId:
    def test_new_operation_gets_uuid(self, trace_db):
        job = _job()
        action = {"type": "send_customer_auto_reply", "to": "a@example.com", "tenant_id": job.tenant_id}
        op_id, _, _ = allocate_action_operation_id(trace_db, tenant_id=job.tenant_id, job_id=job.job_id, action=action)
        assert op_id
        uuid.UUID(op_id)

    def test_reuses_existing_operation_id(self, trace_db):
        job = _job()
        action = {"type": "send_customer_auto_reply", "to": "a@example.com", "tenant_id": job.tenant_id}
        existing = str(uuid.uuid4())
        with patch.dict("os.environ", {"DECISION_RECORD_HMAC_KEY": "test-secret-key"}):
            get_settings.cache_clear()
            op1, fp, _ = allocate_action_operation_id(
                trace_db, tenant_id=job.tenant_id, job_id=job.job_id, action=action, existing_operation_id=existing
            )
            op2, _, _ = allocate_action_operation_id(
                trace_db, tenant_id=job.tenant_id, job_id=job.job_id, action=action, existing_operation_id=existing
            )
            assert op1 == op2 == existing
            assert fp is not None
            get_settings.cache_clear()

    def test_fingerprint_mismatch_raises_conflict(self, trace_db):
        job = _job()
        action_a = {"type": "send_email", "to": "a@example.com", "tenant_id": job.tenant_id}
        action_b = {"type": "send_email", "to": "b@example.com", "tenant_id": job.tenant_id}
        with patch.dict("os.environ", {"DECISION_RECORD_HMAC_KEY": "test-secret-key"}):
            get_settings.cache_clear()
            trace = _trace(job, trace_db)
            op_id = record_action_authorization(trace_db, trace, job, action_a, authorization="execution_allowed")
            with pytest.raises(OperationConflict):
                allocate_action_operation_id(
                    trace_db,
                    tenant_id=job.tenant_id,
                    job_id=job.job_id,
                    action=action_b,
                    existing_operation_id=op_id,
                )
            get_settings.cache_clear()


class TestHmacFingerprintRotation:
    def test_operation_id_independent_of_hmac_key(self, trace_db):
        job = _job()
        action = {"type": "create_monday_item", "item_name": "Lead", "tenant_id": job.tenant_id}
        op_id = str(uuid.uuid4())
        with patch.dict("os.environ", {"DECISION_RECORD_HMAC_KEY": "key-one"}):
            get_settings.cache_clear()
            fp1, ver1 = compute_action_fingerprint(action)
            get_settings.cache_clear()
        with patch.dict("os.environ", {"DECISION_RECORD_HMAC_KEY": "key-two"}):
            get_settings.cache_clear()
            fp2, ver2 = compute_action_fingerprint(action)
            get_settings.cache_clear()
        assert fp1 != fp2
        assert ver1 == ver2 == FINGERPRINT_KEY_VERSION
        reused, _, _ = allocate_action_operation_id(
            trace_db,
            tenant_id=job.tenant_id,
            job_id=job.job_id,
            action=action,
            existing_operation_id=op_id,
        )
        assert reused == op_id

    def test_missing_hmac_key_yields_null_fingerprint(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("DECISION_RECORD_HMAC_KEY", None)
            get_settings.cache_clear()
            fp, ver = compute_action_fingerprint({"type": "send_email", "to": "a@b.com", "tenant_id": "T1"})
            assert fp is None and ver is None
            get_settings.cache_clear()


class TestExternalWriteTwoPhase:
    def test_pending_intent_blocks_auto_retry(self, trace_db):
        job = _job()
        trace = _trace(job, trace_db)
        action = {
            "type": "send_customer_auto_reply",
            "to": "c@example.com",
            "tenant_id": job.tenant_id,
            "_authorization": "execution_allowed",
        }
        op_id = record_action_authorization(trace_db, trace, job, action, authorization="execution_allowed")
        action["_action_operation_id"] = op_id
        record_execution_intent(
            trace_db, trace, job, action,
            operation_id=op_id, fingerprint=None, key_version=None,
        )
        with patch.dict("os.environ", {"DECISION_RECORD_ENFORCE_WRITES": "true"}):
            get_settings.cache_clear()
            with pytest.raises(ReconciliationRequired):
                execute_external_write_with_trace(
                    db=trace_db,
                    trace=trace,
                    job=job,
                    action=action,
                    adapter_fn=lambda: {"type": action["type"], "status": "executed"},
                )
            get_settings.cache_clear()

    def test_same_operation_id_on_resume(self, trace_db):
        job = _job()
        trace = _trace(job, trace_db)
        action = {
            "type": "send_internal_handoff",
            "to": "ops@example.com",
            "tenant_id": job.tenant_id,
        }
        op_id = record_action_authorization(trace_db, trace, job, action, authorization="approval_required")
        resumed_op, _, _ = allocate_action_operation_id(
            trace_db,
            tenant_id=job.tenant_id,
            job_id=job.job_id,
            action=action,
            existing_operation_id=op_id,
        )
        assert resumed_op == op_id


class TestPipelineRunContextIsolation:
    def test_parallel_runs_do_not_mix_context(self):
        results: list[tuple[str, str]] = []

        def worker(tenant_id: str):
            job = _job(tenant_id=tenant_id)
            trace = create_trace_session(job, source=PipelineRunSource.INTAKE, db=None)
            return (trace.pipeline_run.tenant_id, trace.pipeline_run.pipeline_run_id)

        t1 = threading.Thread(target=lambda: results.append(worker("TENANT_A")))
        t2 = threading.Thread(target=lambda: results.append(worker("TENANT_B")))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(results) == 2
        tenants = {tenant for tenant, _ in results}
        run_ids = {run_id for _, run_id in results}
        assert tenants == {"TENANT_A", "TENANT_B"}
        assert len(run_ids) == 2


class TestReadiness:
    def test_production_rejects_enforce_false(self):
        with pytest.raises(ValueError):
            validate_decision_record_settings(
                Settings(ENV="production", DECISION_RECORD_ENFORCE_WRITES="false")
            )

    def test_invalid_enforce_value_fails_closed(self):
        with patch.dict("os.environ", {"DECISION_RECORD_ENFORCE_WRITES": "maybe"}):
            get_settings.cache_clear()
            from app.core.settings import resolve_decision_record_enforce_writes

            assert resolve_decision_record_enforce_writes() is True
            get_settings.cache_clear()

    def test_readiness_requires_table_when_enforce_on(self):
        engine = create_engine("sqlite:///:memory:")
        verify_decision_trace_readiness(engine, Settings(DECISION_RECORD_ENFORCE_WRITES="false"))
        with pytest.raises(RuntimeError):
            verify_decision_trace_readiness(engine, Settings(DECISION_RECORD_ENFORCE_WRITES="true"))
        DecisionRecordRow.__table__.create(engine, checkfirst=True)
        verify_decision_trace_readiness(engine, Settings(DECISION_RECORD_ENFORCE_WRITES="true"))


class TestIdempotency:
    def test_append_if_absent_is_idempotent(self, trace_db):
        job = _job()
        trace = _trace(job, trace_db)
        key = f"policy:{trace.pipeline_run.pipeline_run_id}"
        append_record(
            trace_db, trace, job,
            record_type=DecisionRecordType.POLICY_AUTHORIZATION,
            idempotency_key=key,
            policy_authorization="approval_required",
        )
        append_record(
            trace_db, trace, job,
            record_type=DecisionRecordType.POLICY_AUTHORIZATION,
            idempotency_key=key,
            policy_authorization="approval_required",
        )
        rows = DecisionRecordRepository.list_for_job(trace_db, tenant_id=job.tenant_id, job_id=job.job_id)
        assert len(rows) == 1
