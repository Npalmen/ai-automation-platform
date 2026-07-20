"""PostgreSQL-specific evaluation harness isolation and approval CAS tests."""

from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.settings import Settings
from app.domain.workflows.enums import JobType
from app.domain.workflows.models import Job
from app.evaluation.db_isolation import (
    TENANT_BOUND_TABLES,
    assert_tenant_purged_via_new_engine,
    count_tenant_rows_fresh,
    create_eval_pg_engine,
    eval_pg_db_session,
    provision_eval_pg_engine,
    purge_eval_tenant,
    require_eval_pg_database_url,
    unique_eval_tenant_id,
)
from app.repositories.postgres.action_execution_models import ActionExecutionRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.decision_record_models import DecisionRecordRow
from app.repositories.postgres.decision_record_repository import DecisionRecordRepository
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.job_repository import JobRepository
from app.repositories.postgres.migration_runner import (
    MIGRATIONS_THROUGH_014,
    MIGRATIONS_THROUGH_015,
    ORDERED_MIGRATION_FILES,
    apply_pre_migration_baseline,
    apply_sql_migration_file,
    apply_versioned_sql_migrations,
    reset_public_schema,
    table_exists,
)
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from app.workflows.decision_trace_readiness import verify_decision_trace_readiness

pytestmark = pytest.mark.pg_eval

EXPECTED_DECISION_RECORD_COLUMNS = {
    "decision_id",
    "tenant_id",
    "job_id",
    "event_sequence",
    "pipeline_run_id",
    "parent_pipeline_run_id",
    "stage_sequence",
    "record_type",
    "source",
    "processor_name",
    "recommendation",
    "policy_authorization",
    "policy_decision",
    "action_type",
    "action_operation_id",
    "action_fingerprint",
    "fingerprint_key_version",
    "action_authorization",
    "execution_phase",
    "execution_status",
    "confidence",
    "reason_codes",
    "tenant_config_version",
    "code_version",
    "service_profile_type",
    "prompt_name",
    "prompt_version",
    "prompt_hash",
    "model_provider",
    "model_name",
    "idempotency_key",
    "supersedes_decision_id",
    "job_status_at_record",
    "metadata",
    "created_at",
}

# Tenant-bound elsewhere but intentionally not covered by purge_eval_tenant:
# onboarding_sessions, tenant_activation_snapshots, integration tables from 010,
# oauth_credentials, tenant_api_keys, operator_alerts, integration_invitations.
# integration_events does not exist in this schema.


def _pg_configured() -> bool:
    return (
        os.environ.get("EVAL_DATABASE_URL", "").strip() != ""
        and os.environ.get("EVAL_HARNESS_PG_ALLOWED", "").strip().lower() == "yes"
    )


def _pg_engine_or_fail():
    if not _pg_configured():
        pytest.skip("EVAL_DATABASE_URL + EVAL_HARNESS_PG_ALLOWED=yes required")
    try:
        return create_eval_pg_engine()
    except Exception as exc:
        pytest.fail(f"PostgreSQL eval DB unavailable: {exc}")


@pytest.fixture(autouse=True)
def _pg_eval_required_env(monkeypatch):
    monkeypatch.setenv("ENV", "test")


@pytest.fixture()
def pg_engine():
    if not _pg_configured():
        pytest.skip("EVAL_DATABASE_URL + EVAL_HARNESS_PG_ALLOWED=yes required")
    try:
        require_eval_pg_database_url()
        engine = provision_eval_pg_engine()
    except Exception as exc:
        pytest.fail(f"PostgreSQL eval DB unavailable: {exc}")
    yield engine
    engine.dispose()


def _fresh_engine():
    engine = _pg_engine_or_fail()
    reset_public_schema(engine)
    return engine


def _assert_decision_records_schema(engine) -> None:
    assert table_exists(engine, "decision_records")
    columns = {c["name"] for c in inspect(engine).get_columns("decision_records")}
    assert EXPECTED_DECISION_RECORD_COLUMNS.issubset(columns)


def _assert_identity_sequence(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO decision_records (
                    decision_id, tenant_id, job_id, pipeline_run_id, stage_sequence,
                    record_type, source, code_version, idempotency_key, job_status_at_record
                ) VALUES (
                    :id1, :tenant, :job, :run, 1,
                    'policy_authorization', 'test', 'v1', :key1, 'running'
                )
                """
            ),
            {
                "id1": str(uuid.uuid4()),
                "tenant": "T_EVAL_IDENTITY",
                "job": str(uuid.uuid4()),
                "run": str(uuid.uuid4()),
                "key1": f"k1-{uuid.uuid4().hex}",
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO decision_records (
                    decision_id, tenant_id, job_id, pipeline_run_id, stage_sequence,
                    record_type, source, code_version, idempotency_key, job_status_at_record
                ) VALUES (
                    :id2, :tenant, :job, :run, 2,
                    'policy_authorization', 'test', 'v1', :key2, 'running'
                )
                """
            ),
            {
                "id2": str(uuid.uuid4()),
                "tenant": "T_EVAL_IDENTITY",
                "job": str(uuid.uuid4()),
                "run": str(uuid.uuid4()),
                "key2": f"k2-{uuid.uuid4().hex}",
            },
        )
        rows = conn.execute(
            text(
                "SELECT event_sequence FROM decision_records "
                "WHERE tenant_id = :tenant ORDER BY event_sequence"
            ),
            {"tenant": "T_EVAL_IDENTITY"},
        ).fetchall()
    sequences = [int(row[0]) for row in rows]
    assert len(sequences) == 2
    assert sequences[0] < sequences[1]
    with engine.connect() as conn:
        identity = conn.execute(
            text(
                "SELECT is_identity FROM information_schema.columns "
                "WHERE table_name = 'decision_records' AND column_name = 'event_sequence'"
            )
        ).scalar()
    assert identity in ("YES", True)


def _assert_unique_idempotency_index(engine) -> None:
    with engine.connect() as conn:
        index_names = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename = 'decision_records'"
                )
            ).fetchall()
        }
    assert "ux_decision_records_idempotency" in index_names

    tenant_id = unique_eval_tenant_id("uniq", uuid.uuid4().hex)
    job_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    key = f"dup-{uuid.uuid4().hex}"
    base = {
        "tenant_id": tenant_id,
        "job_id": job_id,
        "pipeline_run_id": run_id,
        "stage_sequence": 1,
        "record_type": "policy_authorization",
        "source": "test",
        "code_version": "v1",
        "idempotency_key": key,
        "job_status_at_record": "running",
    }
    session = sessionmaker(bind=engine)()
    try:
        DecisionRecordRepository.append_if_absent(
            session,
            {"decision_id": str(uuid.uuid4()), **base},
        )
        session.commit()
        with pytest.raises(IntegrityError):
            with session.begin():
                session.add(
                    DecisionRecordRow(
                        decision_id=str(uuid.uuid4()),
                        tenant_id=tenant_id,
                        job_id=job_id,
                        pipeline_run_id=run_id,
                        stage_sequence=2,
                        record_type="policy_authorization",
                        source="test",
                        code_version="v1",
                        idempotency_key=key,
                        job_status_at_record="running",
                    )
                )
                session.flush()
    finally:
        session.close()


def _assert_action_operation_index(engine) -> None:
    with engine.connect() as conn:
        index_names = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename = 'decision_records'"
                )
            ).fetchall()
        }
    assert "ix_decision_records_action_operation" in index_names


def test_pg_migration_chain_from_empty_database():
    """S-PG-01: empty database → baseline + ordered SQL migrations through 015."""
    engine = _fresh_engine()
    try:
        apply_pre_migration_baseline(engine)
        apply_versioned_sql_migrations(engine, ORDERED_MIGRATION_FILES)
        _assert_decision_records_schema(engine)
        _assert_unique_idempotency_index(engine)
        _assert_action_operation_index(engine)
        _assert_identity_sequence(engine)
        with engine.connect() as conn:
            migration_tables = {
                row[0]
                for row in conn.execute(
                    text(
                        "SELECT tablename FROM pg_tables "
                        "WHERE schemaname = 'public' AND tablename IN "
                        "('tenant_activation_snapshots', 'decision_records')"
                    )
                ).fetchall()
            }
        assert "tenant_activation_snapshots" in migration_tables
        assert "decision_records" in migration_tables
    finally:
        engine.dispose()


def test_pg_migration_014_to_015_upgrade_path():
    """S-PG-04: baseline + schema through 014 SQL files → apply 015_decision_records.sql."""
    engine = _fresh_engine()
    try:
        apply_pre_migration_baseline(engine)
        apply_versioned_sql_migrations(engine, MIGRATIONS_THROUGH_014)
        assert table_exists(engine, "tenant_activation_snapshots")
        assert not table_exists(engine, "decision_records")
        apply_sql_migration_file(engine, "015_decision_records.sql")
        _assert_decision_records_schema(engine)
        _assert_unique_idempotency_index(engine)
        _assert_action_operation_index(engine)
    finally:
        engine.dispose()


def test_pg_concurrent_append_if_absent(pg_engine):
    """S-PG-05: concurrent append_if_absent keeps one row per idempotency key."""
    tenant_id = unique_eval_tenant_id("append", uuid.uuid4().hex)
    job_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    key = f"concurrent-{uuid.uuid4().hex}"
    barrier = threading.Barrier(2)
    decision_ids: list[str] = []
    errors: list[Exception] = []

    def _worker():
        session = sessionmaker(bind=pg_engine)()
        try:
            barrier.wait(timeout=5)
            row = DecisionRecordRepository.append_if_absent(
                session,
                {
                    "decision_id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "job_id": job_id,
                    "pipeline_run_id": run_id,
                    "stage_sequence": 1,
                    "record_type": "policy_authorization",
                    "source": "test",
                    "code_version": "v1",
                    "idempotency_key": key,
                    "job_status_at_record": "running",
                },
            )
            session.commit()
            decision_ids.append(row.decision_id)
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
    assert len(decision_ids) == 2
    assert len(set(decision_ids)) == 1
    with pg_engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT COUNT(*) FROM decision_records "
                "WHERE tenant_id = :tid AND idempotency_key = :key"
            ),
            {"tid": tenant_id, "key": key},
        ).scalar()
    assert int(count or 0) == 1
    purge_eval_tenant(pg_engine, tenant_id)


def test_pg_tenant_purge_after_scenario(pg_engine):
    """S-PG-02: explicit purge removes all tenant-bound rows; verified via new engine."""
    tenant_id = unique_eval_tenant_id("pg_purge", uuid.uuid4().hex)
    other_tenant = unique_eval_tenant_id("pg_purge_other", uuid.uuid4().hex)
    now = datetime.now(timezone.utc)
    job_id = str(uuid.uuid4())
    database_url = require_eval_pg_database_url()

    with eval_pg_db_session(pg_engine) as db:
        job = Job(
            tenant_id=tenant_id,
            job_id=job_id,
            job_type=JobType.INTAKE,
            input_data={"subject": "purge probe"},
        )
        JobRepository.create_job(db, job)
        db.add(
            ApprovalRequestRecord(
                approval_id=f"appr_{uuid.uuid4().hex[:12]}",
                tenant_id=tenant_id,
                job_id=job_id,
                job_type="intake",
                state="pending",
                channel="dashboard",
                title="t",
                summary="s",
                request_payload={},
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            DecisionRecordRow(
                decision_id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                job_id=job_id,
                pipeline_run_id=str(uuid.uuid4()),
                stage_sequence=1,
                record_type="action_authorization",
                source="test",
                code_version="v1",
                idempotency_key=f"auth-{uuid.uuid4().hex}",
                job_status_at_record="running",
            )
        )
        db.add(
            ActionExecutionRecord(
                execution_id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                job_id=job_id,
                action_type="send_customer_auto_reply",
                status="completed",
                request_payload={},
                executed_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            AuditEventRecord(
                event_id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                category="test",
                action="purge_probe",
                status="ok",
                details={},
                created_at=now,
            )
        )
        db.add(
            TenantConfigRecord(
                tenant_id=tenant_id,
                status="active",
                lifecycle_status="onboarding",
                config_version=1,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            TenantConfigRecord(
                tenant_id=other_tenant,
                status="active",
                lifecycle_status="onboarding",
                config_version=1,
                created_at=now,
                updated_at=now,
            )
        )

    before = count_tenant_rows_fresh(pg_engine, tenant_id)
    for table, _column in TENANT_BOUND_TABLES:
        assert before[table] >= 1, f"expected seeded row in {table}, got {before}"

    purge_eval_tenant(pg_engine, tenant_id)
    assert_tenant_purged_via_new_engine(database_url, tenant_id)

    verify_engine = create_eval_pg_engine()
    try:
        other_counts = count_tenant_rows_fresh(verify_engine, other_tenant)
        assert other_counts["tenant_configs"] == 1
        purge_eval_tenant(verify_engine, other_tenant)
    finally:
        verify_engine.dispose()


def test_concurrent_approval_cas_single_execution(pg_engine):
    """S-PG-03: two workers, one adapter execution, full trace chain."""
    from unittest.mock import MagicMock, patch

    from app.repositories.postgres.approval_models import ApprovalRequestRecord
    from app.workflows.action_approval_resolution import resolve_per_action_approval
    from app.workflows.decision_record_service import record_action_authorization
    from app.workflows.pipeline_run_context import PipelineRunSource, create_trace_session

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
        mock = MagicMock()
        mock.execute_action.return_value = {"provider": "gmail", "message_id": "m1"}
        return mock

    setup_session = sessionmaker(bind=pg_engine)()
    try:
        now = datetime.now(timezone.utc)
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
            setup_session,
            trace,
            job,
            action,
            authorization="approval_required",
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
                    side_effect=_adapter_factory,
                ),
                patch(
                    "app.workflows.email_approval_resolution.finalize_email_approval_resolution",
                ),
            ):
                results.append(
                    resolve_per_action_approval(session, approval, approved=True, actor="w")
                )
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

    winners = [r for r in results if not r.idempotent]
    losers = [r for r in results if r.idempotent]
    assert len(winners) == 1
    assert len(losers) == 1
    assert winners[0].action_operation_id == operation_id
    assert losers[0].action_operation_id == operation_id

    verify_session = sessionmaker(bind=pg_engine)()
    try:
        rows = DecisionRecordRepository.list_for_operation(
            verify_session,
            tenant_id=tenant_id,
            action_operation_id=operation_id,
        )
        by_type: dict[str, list] = {}
        for row in rows:
            by_type.setdefault(row.record_type, []).append(row)

        assert len(by_type.get("action_authorization", [])) == 1
        assert len(by_type.get("action_approval_resolution", [])) == 1
        assert len(by_type.get("execution_intent", [])) == 1
        assert len(by_type.get("execution_outcome", [])) == 1

        for group in by_type.values():
            assert all(r.tenant_id == tenant_id for r in group)
            assert all(r.action_operation_id == operation_id for r in group)

        sibling_types = {
            row.record_type
            for row in rows
            if row.record_type
            not in {
                "action_authorization",
                "action_approval_resolution",
                "execution_intent",
                "execution_outcome",
            }
        }
        assert not sibling_types
    finally:
        verify_session.close()

    purge_eval_tenant(pg_engine, tenant_id)


def test_pg_decision_trace_readiness_with_migration_015():
    """S-PG-06: readiness PASS after migration 015 with enforcement enabled."""
    engine = _fresh_engine()
    try:
        apply_pre_migration_baseline(engine)
        apply_versioned_sql_migrations(engine, MIGRATIONS_THROUGH_015)
        verify_decision_trace_readiness(
            engine,
            Settings(DECISION_RECORD_ENFORCE_WRITES="true"),
        )
    finally:
        engine.dispose()


def test_pg_decision_trace_readiness_without_migration_015():
    """S-PG-07: readiness FAIL without migration 015 when enforcement enabled."""
    engine = _fresh_engine()
    try:
        apply_pre_migration_baseline(engine)
        apply_versioned_sql_migrations(engine, MIGRATIONS_THROUGH_014)
        assert not table_exists(engine, "decision_records")
        with pytest.raises(RuntimeError, match="decision_records table is missing"):
            verify_decision_trace_readiness(
                engine,
                Settings(DECISION_RECORD_ENFORCE_WRITES="true"),
            )
    finally:
        engine.dispose()
