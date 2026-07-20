"""Database isolation for evaluation harness runs."""

from __future__ import annotations

import os
import uuid
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.repositories.postgres.action_execution_models import ActionExecutionRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.database import Base
from app.repositories.postgres.decision_record_models import DecisionRecordRow
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord
from app.repositories.postgres.schema_migrations import ensure_runtime_schema
from app.tools.test_environment.guards import verify_database_fingerprint

TENANT_BOUND_TABLES: tuple[tuple[str, str], ...] = (
    ("jobs", "tenant_id"),
    ("approval_requests", "tenant_id"),
    ("decision_records", "tenant_id"),
    ("action_executions", "tenant_id"),
    ("audit_events", "tenant_id"),
    ("tenant_configs", "tenant_id"),
)


def _eval_tables():
    return [
        TenantConfigRecord.__table__,
        JobRecord.__table__,
        ApprovalRequestRecord.__table__,
        ActionExecutionRecord.__table__,
        AuditEventRecord.__table__,
        DecisionRecordRow.__table__,
    ]


def _install_sqlite_event_sequence_hook(engine) -> None:
    if "sqlite" not in str(engine.url):
        return

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


def _patch_commit_to_flush(session: Session) -> None:
    """Prevent harness DB writes from escaping outer transaction rollback."""

    def _flush_instead_of_commit():
        session.flush()

    session.commit = _flush_instead_of_commit  # type: ignore[method-assign]


@contextmanager
def eval_db_session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine, tables=_eval_tables())
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_decision_records_idempotency "
                "ON decision_records (tenant_id, idempotency_key)"
            )
        )
    _install_sqlite_event_sequence_hook(engine)

    connection = engine.connect()
    outer = connection.begin()
    session = sessionmaker(bind=connection)()
    _patch_commit_to_flush(session)
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()
        engine.dispose()


def unique_eval_tenant_id(scenario_id: str, run_id: str | None = None) -> str:
    suffix = (run_id or uuid.uuid4().hex)[:12]
    safe = scenario_id.replace("-", "_").upper()[:24]
    return f"T_EVAL_{safe}_{suffix}"


def count_tenant_rows(session: Session, tenant_id: str) -> dict[str, int]:
    return {
        "jobs": session.query(JobRecord).filter_by(tenant_id=tenant_id).count(),
        "decision_records": session.query(DecisionRecordRow).filter_by(tenant_id=tenant_id).count(),
        "approvals": session.query(ApprovalRequestRecord).filter_by(tenant_id=tenant_id).count(),
        "action_executions": session.query(ActionExecutionRecord).filter_by(tenant_id=tenant_id).count(),
    }


def assert_tenant_clean(session: Session, tenant_id: str) -> None:
    counts = count_tenant_rows(session, tenant_id)
    dirty = {k: v for k, v in counts.items() if v > 0}
    if dirty:
        raise AssertionError(f"Tenant {tenant_id} not clean after scenario: {dirty}")


def require_eval_pg_database_url() -> str:
    url = os.environ.get("EVAL_DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("EVAL_DATABASE_URL is required for PostgreSQL eval tests")
    if os.environ.get("EVAL_HARNESS_PG_ALLOWED", "").strip().lower() != "yes":
        raise RuntimeError("EVAL_HARNESS_PG_ALLOWED=yes is required for PostgreSQL eval tests")
    ok, reason = verify_database_fingerprint(url)
    if not ok:
        raise RuntimeError(f"EVAL_DATABASE_URL rejected by fingerprint guard: {reason}")
    return url


def provision_eval_pg_engine() -> Engine:
    url = require_eval_pg_database_url()
    engine = create_engine(url, pool_pre_ping=True)
    Base.metadata.create_all(bind=engine, tables=_eval_tables())
    ensure_runtime_schema(engine)
    return engine


def purge_eval_tenant(engine: Engine, tenant_id: str) -> None:
    with engine.begin() as conn:
        for table, column in TENANT_BOUND_TABLES:
            conn.execute(text(f"DELETE FROM {table} WHERE {column} = :tid"), {"tid": tenant_id})


def count_tenant_rows_fresh(engine: Engine, tenant_id: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    with engine.connect() as conn:
        for table, column in TENANT_BOUND_TABLES:
            row = conn.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE {column} = :tid"),
                {"tid": tenant_id},
            ).scalar()
            counts[table] = int(row or 0)
    return counts


def assert_tenant_purged(engine: Engine, tenant_id: str) -> None:
    counts = count_tenant_rows_fresh(engine, tenant_id)
    dirty = {k: v for k, v in counts.items() if v > 0}
    if dirty:
        raise AssertionError(f"Tenant {tenant_id} not purged: {dirty}")


@contextmanager
def eval_pg_db_session(engine: Engine | None = None) -> Iterator[Session]:
    """Production-like commit semantics for PostgreSQL eval scenarios."""
    owned_engine = engine is None
    engine = engine or provision_eval_pg_engine()
    session = sessionmaker(bind=engine)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
        if owned_engine:
            engine.dispose()
