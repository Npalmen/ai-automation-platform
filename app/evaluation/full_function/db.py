"""PostgreSQL lifecycle helpers for full-function evaluation."""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.evaluation.customer_domain.db import (
    END_CUSTOMER_TABLES,
    create_eval_engine,
    ensure_eval_tenant,
)
from app.evaluation.full_function.guards import EVAL_TENANT_PREFIX
from app.repositories.postgres.migration_runner import (
    ORDERED_MIGRATION_FILES,
    apply_pre_migration_baseline,
    apply_versioned_sql_migrations,
    reset_public_schema,
)

CAMPAIGN_TABLES: tuple[str, ...] = (
    "decision_records",
    "action_executions",
    "approval_requests",
    "jobs",
    "audit_events",
    "integration_events",
    *END_CUSTOMER_TABLES,
)


def initialize_database(engine: Engine) -> None:
    reset_public_schema(engine)
    apply_pre_migration_baseline(engine)
    apply_versioned_sql_migrations(engine, ORDERED_MIGRATION_FILES)


def cleanup_eval_tenants(engine: Engine) -> None:
    pattern = f"{EVAL_TENANT_PREFIX}%"
    with engine.begin() as conn:
        for table in CAMPAIGN_TABLES:
            if table in {"audit_events", "integration_events"}:
                conn.execute(
                    text(f"DELETE FROM {table} WHERE tenant_id LIKE :pattern"),
                    {"pattern": pattern},
                )
                continue
            conn.execute(
                text(f"DELETE FROM {table} WHERE tenant_id LIKE :pattern"),
                {"pattern": pattern},
            )
        conn.execute(
            text("DELETE FROM tenant_configs WHERE tenant_id LIKE :pattern"),
            {"pattern": pattern},
        )


def count_non_eval_rows(engine: Engine) -> int:
    total = 0
    with engine.connect() as conn:
        for table in END_CUSTOMER_TABLES:
            result = conn.execute(
                text(
                    f"SELECT COUNT(*) FROM {table} WHERE tenant_id NOT LIKE :pattern"
                ),
                {"pattern": f"{EVAL_TENANT_PREFIX}%"},
            )
            total += int(result.scalar() or 0)
    return total


__all__ = [
    "CAMPAIGN_TABLES",
    "cleanup_eval_tenants",
    "count_non_eval_rows",
    "create_eval_engine",
    "ensure_eval_tenant",
    "initialize_database",
]
