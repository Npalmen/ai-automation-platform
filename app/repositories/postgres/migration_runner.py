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
    "016_integration_selections.sql",
    "017_live_eval_runs.sql",
    "018_live_eval_external_events.sql",
    "019_live_eval_runs_activated_at.sql",
    "020_live_eval_llm_contract.sql",
    "021_live_eval_llm_operations.sql",
)

MIGRATIONS_THROUGH_014: tuple[str, ...] = ORDERED_MIGRATION_FILES[:6]
MIGRATIONS_THROUGH_015: tuple[str, ...] = ORDERED_MIGRATION_FILES[:7]
MIGRATIONS_THROUGH_019: tuple[str, ...] = ORDERED_MIGRATION_FILES[:10]
LATEST_MIGRATION_VERSION = "021"

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
        "integration_selection_backfill_runs",
        "live_eval_runs",
        "live_eval_external_events",
        "live_eval_llm_operations",
    }
)

_CI_REQUIRED_TABLES: tuple[str, ...] = (
    "tenant_configs",
    "jobs",
    "live_eval_runs",
    "live_eval_external_events",
    "live_eval_llm_operations",
)

_CI_REQUIRED_INDEXES: tuple[tuple[str, str], ...] = (
    ("live_eval_runs", "ix_live_eval_runs_tenant_status"),
    ("live_eval_runs", "ix_live_eval_runs_expires_at"),
    ("live_eval_external_events", "ix_live_eval_external_events_run"),
    ("live_eval_external_events", "uq_live_eval_external_events_operation_succeeded"),
    ("live_eval_llm_operations", "uq_live_eval_llm_operations_operation_key"),
    ("live_eval_llm_operations", "uq_live_eval_llm_operations_run_prompt"),
    ("live_eval_llm_operations", "uq_live_eval_llm_operations_run_ordinal"),
)

_CI_REQUIRED_CONSTRAINTS: tuple[tuple[str, str], ...] = (
    ("live_eval_runs", "uq_live_eval_runs_tenant_run"),
    ("live_eval_external_events", "fk_live_eval_events_run"),
    ("live_eval_llm_operations", "fk_live_eval_llm_operations_run"),
    ("live_eval_llm_operations", "ck_live_eval_llm_operations_ordinal"),
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


def column_exists(engine: Engine, table_name: str, column_name: str) -> bool:
    from sqlalchemy import inspect

    columns = inspect(engine).get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def _index_names(engine: Engine, table_name: str) -> set[str]:
    from sqlalchemy import inspect

    return {index["name"] for index in inspect(engine).get_indexes(table_name)}


def _constraint_names(engine: Engine, table_name: str) -> set[str]:
    from sqlalchemy import inspect

    inspector = inspect(engine)
    names = {constraint.get("name") for constraint in inspector.get_unique_constraints(table_name)}
    names.update(constraint.get("name") for constraint in inspector.get_foreign_keys(table_name))
    return {name for name in names if name}


def read_migration_state(engine: Engine) -> dict[str, object]:
    """Infer migration state from schema artifacts (no separate migration ledger)."""
    missing_tables = [table for table in MIGRATION_OWNED_TABLES if not table_exists(engine, table)]
    if missing_tables:
        raise RuntimeError(
            "Migration state incomplete — missing migration-owned tables: "
            + ", ".join(sorted(missing_tables))
        )
    if not column_exists(engine, "live_eval_runs", "activated_at"):
        raise RuntimeError(
            "Migration state incomplete — live_eval_runs.activated_at missing (019)"
        )
    if not column_exists(engine, "live_eval_runs", "llm_max_calls"):
        raise RuntimeError(
            "Migration state incomplete — live_eval_runs.llm_max_calls missing (021)"
        )
    if not table_exists(engine, "live_eval_llm_operations"):
        raise RuntimeError(
            "Migration state incomplete — live_eval_llm_operations missing (021)"
        )
    return {
        "latest_version": LATEST_MIGRATION_VERSION,
        "latest_file": ORDERED_MIGRATION_FILES[-1],
        "applied_files": list(ORDERED_MIGRATION_FILES),
    }


def verify_ci_postgres_schema_provisioned(engine: Engine) -> dict[str, object]:
    """Fail closed when CI bootstrap has not provisioned the expected schema."""
    missing_tables = [table for table in _CI_REQUIRED_TABLES if not table_exists(engine, table)]
    if missing_tables:
        raise RuntimeError(
            "PostgreSQL schema is not provisioned for integration_db tests. "
            "Run: python -m scripts.ci.bootstrap_postgres_schema\n"
            "Missing tables: " + ", ".join(sorted(missing_tables))
        )

    if not column_exists(engine, "live_eval_runs", "activated_at"):
        raise RuntimeError(
            "PostgreSQL schema is not provisioned for integration_db tests. "
            "Missing column live_eval_runs.activated_at (migration 019)."
        )
    if not column_exists(engine, "live_eval_runs", "llm_max_calls"):
        raise RuntimeError(
            "PostgreSQL schema is not provisioned for integration_db tests. "
            "Missing column live_eval_runs.llm_max_calls (migration 021)."
        )
    if not table_exists(engine, "live_eval_llm_operations"):
        raise RuntimeError(
            "PostgreSQL schema is not provisioned for integration_db tests. "
            "Missing table live_eval_llm_operations (migration 021)."
        )

    for table_name, index_name in _CI_REQUIRED_INDEXES:
        if index_name not in _index_names(engine, table_name):
            raise RuntimeError(
                f"PostgreSQL schema is not provisioned for integration_db tests. "
                f"Missing index {index_name} on {table_name}."
            )

    for table_name, constraint_name in _CI_REQUIRED_CONSTRAINTS:
        if constraint_name not in _constraint_names(engine, table_name):
            raise RuntimeError(
                f"PostgreSQL schema is not provisioned for integration_db tests. "
                f"Missing constraint {constraint_name} on {table_name}."
            )

    return read_migration_state(engine)


def bootstrap_ci_postgres_schema(engine: Engine) -> dict[str, object]:
    """Bootstrap an empty dedicated PostgreSQL database for CI integration_db tests."""
    from app.repositories.postgres.schema_migrations import ensure_runtime_schema

    apply_pre_migration_baseline(engine)
    apply_versioned_sql_migrations(engine, ORDERED_MIGRATION_FILES)
    ensure_runtime_schema(engine)
    return verify_ci_postgres_schema_provisioned(engine)
