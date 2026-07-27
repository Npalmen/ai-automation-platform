"""PostgreSQL lifecycle helpers for customer-domain evaluation."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.evaluation.customer_domain.guards import EVAL_TENANT_PREFIX
from app.repositories.postgres.migration_runner import (
    ORDERED_MIGRATION_FILES,
    apply_pre_migration_baseline,
    apply_versioned_sql_migrations,
    reset_public_schema,
)
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

END_CUSTOMER_TABLES: tuple[str, ...] = (
    "end_customer_idempotency_records",
    "end_customer_duplicate_candidates",
    "end_customer_timeline_events",
    "end_customer_thread_links",
    "end_customer_job_links",
    "end_customer_relationships",
    "end_customer_identities",
    "end_customer_source_facts",
    "end_customers",
    "end_customer_contacts",
    "end_customer_companies",
)


def create_eval_engine(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


def initialize_database(engine: Engine) -> None:
    reset_public_schema(engine)
    apply_pre_migration_baseline(engine)
    apply_versioned_sql_migrations(engine, ORDERED_MIGRATION_FILES)


def ensure_eval_tenant(db: Session, tenant_id: str, slug: str) -> None:
    TenantConfigRepository.upsert(db, tenant_id=tenant_id, name=tenant_id, slug=slug)
    db.commit()


def cleanup_eval_tenants(engine: Engine) -> None:
    pattern = f"{EVAL_TENANT_PREFIX}%"
    with engine.begin() as conn:
        for table in END_CUSTOMER_TABLES:
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
            if table == "end_customer_idempotency_records":
                result = conn.execute(
                    text(
                        f"SELECT COUNT(*) FROM {table} "
                        "WHERE tenant_id NOT LIKE :pattern"
                    ),
                    {"pattern": f"{EVAL_TENANT_PREFIX}%"},
                )
            else:
                result = conn.execute(
                    text(
                        f"SELECT COUNT(*) FROM {table} "
                        "WHERE tenant_id NOT LIKE :pattern"
                    ),
                    {"pattern": f"{EVAL_TENANT_PREFIX}%"},
                )
            total += int(result.scalar() or 0)
    return total


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    session = sessionmaker(bind=engine)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
