"""PostgreSQL-specific evaluation harness isolation and approval CAS tests."""

from __future__ import annotations

import os
import threading
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.evaluation.db_isolation import (
    assert_tenant_purged,
    count_tenant_rows_fresh,
    eval_pg_db_session,
    provision_eval_pg_engine,
    purge_eval_tenant,
    require_eval_pg_database_url,
    unique_eval_tenant_id,
)
from app.repositories.postgres.database import Base
from app.repositories.postgres.decision_record_models import DecisionRecordRow
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.migration_runner import apply_sql_migration_file, table_exists
from app.repositories.postgres.schema_migrations import ensure_runtime_schema
from app.repositories.postgres.job_repository import JobRepository

pytestmark = pytest.mark.pg_eval


def _pg_enabled() -> bool:
    return (
        os.environ.get("EVAL_DATABASE_URL", "").strip() != ""
        and os.environ.get("EVAL_HARNESS_PG_ALLOWED", "").strip().lower() == "yes"
    )


@pytest.fixture(scope="module")
def pg_engine():
    if not _pg_enabled():
        pytest.skip("EVAL_DATABASE_URL + EVAL_HARNESS_PG_ALLOWED=yes required")
    try:
        require_eval_pg_database_url()
        engine = provision_eval_pg_engine()
    except Exception as exc:
        pytest.skip(f"PostgreSQL eval DB unavailable: {exc}")
    yield engine
    engine.dispose()


def _pg_engine_or_skip():
    if not _pg_enabled():
        pytest.skip("EVAL_DATABASE_URL + EVAL_HARNESS_PG_ALLOWED=yes required")
    try:
        require_eval_pg_database_url()
        return create_engine(require_eval_pg_database_url(), pool_pre_ping=True)
    except Exception as exc:
        pytest.skip(f"PostgreSQL eval DB unavailable: {exc}")


def test_pg_migration_015_from_empty(pg_engine):
    """S-PG-01: empty database + deployment migration path creates decision_records."""
    assert table_exists(pg_engine, "decision_records")
    columns = {c["name"] for c in inspect(pg_engine).get_columns("decision_records")}
    assert "event_sequence" in columns
    assert "idempotency_key" in columns


def test_pg_migration_014_to_015_upgrade():
    """Representative 014 schema without decision_records, then apply migrations/015."""
    engine = _pg_engine_or_skip()
    try:
        Base.metadata.create_all(bind=engine, tables=[JobRecord.__table__])
        ensure_runtime_schema(engine)
        if table_exists(engine, "decision_records"):
            with engine.begin() as conn:
                conn.execute(text("DROP TABLE IF EXISTS decision_records CASCADE"))
        assert not table_exists(engine, "decision_records")
        apply_sql_migration_file(engine, "015_decision_records.sql")
        assert table_exists(engine, "decision_records")
    finally:
        engine.dispose()


def test_pg_tenant_purge_after_scenario(pg_engine):
    """S-PG-02: commit-semantics scenario leaves no tenant rows after explicit purge."""
    tenant_id = unique_eval_tenant_id("pg_purge", uuid.uuid4().hex)
    with eval_pg_db_session(pg_engine) as db:
        job = Job(
            tenant_id=tenant_id,
            job_id=str(uuid.uuid4()),
            job_type=JobType.INTAKE,
            input_data={"subject": "purge probe"},
        )
        JobRepository.create_job(db, job)
    assert count_tenant_rows_fresh(pg_engine, tenant_id)["jobs"] == 1
    purge_eval_tenant(pg_engine, tenant_id)
    assert_tenant_purged(pg_engine, tenant_id)


def test_concurrent_approval_cas_single_execution(pg_engine):
    """S-PG-03: two workers, one adapter execution, loser idempotent."""
    if not _pg_enabled():
        pytest.skip("EVAL_DATABASE_URL + EVAL_HARNESS_PG_ALLOWED=yes required")

    from app.repositories.postgres.approval_models import ApprovalRequestRecord
    from app.workflows.action_approval_resolution import resolve_per_action_approval
    from app.workflows.decision_record_service import record_action_authorization
    from app.workflows.pipeline_run_context import PipelineRunSource, create_trace_session
    from unittest.mock import MagicMock, patch

    tenant_id = unique_eval_tenant_id("pg_cas", uuid.uuid4().hex)
    job_id = str(uuid.uuid4())
    operation_id = str(uuid.uuid4())
    delivery = {
        "type": "send_customer_auto_reply",
        "to": "c@example.com",
        "subject": "Hej",
        "body": "Tack",
        "tenant_id": tenant_id,
    }
    adapter_calls = {"n": 0}
    barrier = threading.Barrier(2)
    results: list = []
    errors: list = []

    def _adapter_factory(*_a, **_k):
        adapter_calls["n"] += 1
        return MagicMock(send_message=MagicMock(return_value={"message_id": "m1"}))

    setup_session = sessionmaker(bind=pg_engine)()
    try:
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
        setup_session.add(
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
        trace = create_trace_session(job, source=PipelineRunSource.INTAKE, db=setup_session)
        action = dict(delivery)
        action["_action_operation_id"] = operation_id
        record_action_authorization(
            setup_session, trace, job, action, authorization="approval_required",
        )
        approval_id = f"act_{uuid.uuid4().hex[:12]}"
        setup_session.add(
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
        setup_session.commit()
    finally:
        setup_session.close()

    def _worker():
        session = sessionmaker(bind=pg_engine)()
        try:
            barrier.wait(timeout=5)
            approval = session.get(ApprovalRequestRecord, approval_id)
            with patch("app.workflows.action_executor.get_integration_adapter", side_effect=_adapter_factory):
                results.append(resolve_per_action_approval(session, approval, approved=True, actor="w"))
        except Exception as exc:
            errors.append(exc)
        finally:
            session.close()

    t1 = threading.Thread(target=_worker)
    t2 = threading.Thread(target=_worker)
    t1.start()
    t2.start()
    t1.join(timeout=30)
    t2.join(timeout=30)
    assert not errors, errors
    assert len(results) == 2
    assert adapter_calls["n"] == 1
    assert any(r.idempotent for r in results)
    purge_eval_tenant(pg_engine, tenant_id)
