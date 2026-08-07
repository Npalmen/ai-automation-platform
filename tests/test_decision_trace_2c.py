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
from app.workflows.decision_trace_errors import ExternalWriteBlocked, OperationConflict, ReconciliationRequired
from app.workflows.decision_trace_readiness import verify_decision_trace_readiness
from app.workflows.decision_record import DecisionRecordType, ExecutionStatus
from app.evaluation.profile_testbot.campaign.post_approval_execution import (
    assert_reply_evidence_invariants,
    build_reply_execution_evidence,
    classify_reply_execution_status,
)
from app.workflows.action_executor import _build_stub_result
from app.workflows.external_write_trace import (
    execute_external_write_with_trace,
    is_real_provider_execution_result,
)
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


def _gmail_r4_adapter_result() -> dict:
    return {
        "type": "send_customer_auto_reply",
        "status": "executed",
        "provider": "google_mail",
        "external_id": "gmail-r4-msg-1",
        "integration_result": {
            "provider": "google_mail",
            "status": "success",
            "external_id": "gmail-r4-msg-1",
            "payload": {
                "google_message_id": "gmail-r4-msg-1",
                "thread_id": "thread-r4-1",
                "rfc_message_id": "<rfc-r4@test>",
            },
        },
    }


def _observation_from_records(records) -> dict:
    return {
        "job": {
            "decision_records": [
                {
                    "record_type": row.record_type,
                    "execution_status": row.execution_status,
                    "action_operation_id": row.action_operation_id,
                    "metadata": dict(row.metadata_json or {}),
                }
                for row in records
            ],
            "result": {},
        },
        "events": [],
    }


class TestReviewedLiveExternalWritePersistence:
    def test_gmail_success_persists_provider_message_id_before_terminal_success(self, trace_db):
        job = _job(tenant_id="TENANT_LIVE_EVAL")
        trace = _trace(job, trace_db)
        action = {
            "type": "send_customer_auto_reply",
            "to": "sender@eval.test",
            "tenant_id": job.tenant_id,
            "_authorization": "execution_allowed",
        }
        op_id = record_action_authorization(
            trace_db, trace, job, action, authorization="execution_allowed"
        )
        action["_action_operation_id"] = op_id

        with patch.dict("os.environ", {"DECISION_RECORD_ENFORCE_WRITES": "true"}):
            get_settings.cache_clear()
            result = execute_external_write_with_trace(
                db=trace_db,
                trace=trace,
                job=job,
                action=action,
                adapter_fn=lambda: _gmail_r4_adapter_result(),
            )
            get_settings.cache_clear()

        assert result["external_id"] == "gmail-r4-msg-1"
        assert is_real_provider_execution_result(result)

        records = DecisionRecordRepository.list_for_operation(
            trace_db,
            tenant_id=job.tenant_id,
            action_operation_id=op_id,
        )
        intents = [r for r in records if r.record_type == "execution_intent"]
        outcomes = [r for r in records if r.record_type == "execution_outcome"]
        assert intents
        assert intents[-1].execution_status == ExecutionStatus.PENDING.value
        assert outcomes
        assert outcomes[-1].execution_status == ExecutionStatus.SUCCEEDED.value
        assert outcomes[-1].metadata_json["provider_message_id"] == "gmail-r4-msg-1"

        observation = _observation_from_records(records)
        assert classify_reply_execution_status(observation, action_operation_id=op_id) == "succeeded"
        evidence = build_reply_execution_evidence(
            observation=observation,
            action_operation_id=op_id,
            inbound_provider_message_id="inbound-r4-1",
            inbound_rfc_message_id="<inbound-r4@test>",
        )
        assert evidence.reply_provider_message_id == "gmail-r4-msg-1"
        assert_reply_evidence_invariants(evidence)

    def test_missing_provider_message_id_never_succeeded(self, trace_db):
        job = _job(tenant_id="TENANT_LIVE_EVAL")
        trace = _trace(job, trace_db)
        action = {
            "type": "send_customer_auto_reply",
            "to": "sender@eval.test",
            "tenant_id": job.tenant_id,
            "_authorization": "execution_allowed",
        }
        op_id = record_action_authorization(
            trace_db, trace, job, action, authorization="execution_allowed"
        )
        action["_action_operation_id"] = op_id
        ambiguous = {
            "type": "send_customer_auto_reply",
            "status": "executed",
            "provider": "google_mail",
            "integration_result": {
                "provider": "google_mail",
                "status": "success",
                "payload": {"thread_id": "thread-r4-1"},
            },
        }

        with patch.dict("os.environ", {"DECISION_RECORD_ENFORCE_WRITES": "true"}):
            get_settings.cache_clear()
            with pytest.raises(ReconciliationRequired):
                execute_external_write_with_trace(
                    db=trace_db,
                    trace=trace,
                    job=job,
                    action=action,
                    adapter_fn=lambda: ambiguous,
                )
            get_settings.cache_clear()

        records = DecisionRecordRepository.list_for_operation(
            trace_db,
            tenant_id=job.tenant_id,
            action_operation_id=op_id,
        )
        outcomes = [r for r in records if r.record_type == "execution_outcome"]
        assert outcomes
        assert outcomes[-1].execution_status in {
            ExecutionStatus.OUTCOME_UNKNOWN.value,
            ExecutionStatus.RECONCILIATION_REQUIRED.value,
        }
        assert outcomes[-1].metadata_json.get("reconciliation_required") is True

    def test_reviewed_live_internal_stub_never_succeeded(self, trace_db):
        job = _job(tenant_id="TENANT_LIVE_EVAL")
        trace = _trace(job, trace_db)
        action = {
            "type": "send_customer_auto_reply",
            "to": "sender@eval.test",
            "tenant_id": job.tenant_id,
            "_authorization": "execution_allowed",
        }
        op_id = record_action_authorization(
            trace_db, trace, job, action, authorization="execution_allowed"
        )
        action["_action_operation_id"] = op_id
        stub = _build_stub_result(
            "send_customer_auto_reply",
            "sender@eval.test",
            {"to": "sender@eval.test", "subject": "Re: test", "body": "body"},
            "email",
            "stub",
        )

        with (
            patch(
                "app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider.is_reviewed_live_customer_reply_context",
                return_value=True,
            ),
            patch.dict("os.environ", {"DECISION_RECORD_ENFORCE_WRITES": "true"}),
        ):
            get_settings.cache_clear()
            with pytest.raises(ExternalWriteBlocked):
                execute_external_write_with_trace(
                    db=trace_db,
                    trace=trace,
                    job=job,
                    action=action,
                    adapter_fn=lambda: stub,
                )
            get_settings.cache_clear()

        records = DecisionRecordRepository.list_for_operation(
            trace_db,
            tenant_id=job.tenant_id,
            action_operation_id=op_id,
        )
        outcomes = [r for r in records if r.record_type == "execution_outcome"]
        assert outcomes
        assert outcomes[-1].execution_status == ExecutionStatus.FAILED.value
        assert outcomes[-1].metadata_json.get("reconciliation_required") is True
