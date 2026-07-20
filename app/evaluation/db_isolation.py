"""Database isolation for evaluation harness runs."""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.repositories.postgres.action_execution_models import ActionExecutionRecord
from app.repositories.postgres.approval_models import ApprovalRequestRecord
from app.repositories.postgres.audit_models import AuditEventRecord
from app.repositories.postgres.database import Base
from app.repositories.postgres.decision_record_models import DecisionRecordRow
from app.repositories.postgres.job_models import JobRecord
from app.repositories.postgres.tenant_config_models import TenantConfigRecord


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
