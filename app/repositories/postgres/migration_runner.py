"""Apply versioned SQL migrations from migrations/ using deployment semantics."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

_MIGRATIONS_ROOT = Path(__file__).resolve().parents[3] / "migrations"

ORDERED_MIGRATION_FILES: tuple[str, ...] = (
    "009_onboarding_sessions.sql",
    "010_slice2b_integrations.sql",
    "011_operator_alerts.sql",
    "012_tenant_lifecycle.sql",
    "013_integration_invitations.sql",
    "014_tenant_activation_snapshots.sql",
    "015_decision_records.sql",
)

MIGRATIONS_THROUGH_014: tuple[str, ...] = ORDERED_MIGRATION_FILES[:-1]
MIGRATIONS_THROUGH_015: tuple[str, ...] = ORDERED_MIGRATION_FILES

# Tables created exclusively by migrations/009-015 SQL files (not create_tables.py baseline).
MIGRATION_OWNED_TABLES: frozenset[str] = frozenset(
    {
        "onboarding_sessions",
        "onboarding_step_states",
        "onboarding_step_drafts",
        "onboarding_oauth_states",
        "onboarding_integration_verifications",
        "tenant_resource_bindings",
        "operator_alerts",
        "alert_evaluation_runs",
        "operator_digests",
        "notification_deliveries",
        "integration_invitations",
        "tenant_activation_snapshots",
        "decision_records",
    }
)


def migration_sql_path(filename: str) -> Path:
    path = _MIGRATIONS_ROOT / filename
    if not path.exists():
        raise FileNotFoundError(f"Migration file not found: {path}")
    return path


def apply_sql_migration_file(engine: Engine, filename: str) -> None:
    """Execute a migrations/*.sql file in a single transaction."""
    sql = migration_sql_path(filename).read_text(encoding="utf-8")
    with engine.begin() as conn:
        conn.execute(text(sql))


def apply_migrations_in_order(engine: Engine, filenames: tuple[str, ...] | list[str]) -> None:
    """Apply migrations/*.sql files in order, one transaction per file."""
    for filename in filenames:
        apply_sql_migration_file(engine, filename)


def reset_public_schema(engine: Engine) -> None:
    """Drop and recreate public schema for an isolated empty-database migration test."""
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO CURRENT_USER"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO public"))


def apply_pre_migration_baseline(engine: Engine) -> None:
    """Bootstrap core tables that predate migrations/009 (scripts/create_tables.py equivalent).

    Versioned SQL migrations 009-015 are additive and assume this baseline exists.
    """
    from app.repositories.postgres.database import Base
    from app.repositories.postgres import (  # noqa: F401
        action_execution_models,
        approval_models,
        audit_models,
        job_models,
        oauth_credential_models,
        tenant_api_key_models,
        tenant_config_models,
    )
    from app.domain.integrations import models as integration_models  # noqa: F401

    tables = [
        table
        for table in Base.metadata.sorted_tables
        if table.name not in MIGRATION_OWNED_TABLES
    ]
    Base.metadata.create_all(bind=engine, tables=tables)


def apply_versioned_sql_migrations(
    engine: Engine,
    filenames: tuple[str, ...] | list[str],
) -> None:
    """Apply migrations/*.sql after the pre-009 baseline."""
    apply_migrations_in_order(engine, filenames)


def table_exists(engine: Engine, table_name: str) -> bool:
    from sqlalchemy import inspect

    return table_name in inspect(engine).get_table_names()
