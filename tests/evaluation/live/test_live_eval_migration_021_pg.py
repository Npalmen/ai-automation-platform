"""PostgreSQL migration tests for live eval 020/021."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, inspect, text

from app.repositories.postgres.migration_runner import (
    ORDERED_MIGRATION_FILES,
    apply_pre_migration_baseline,
    apply_versioned_sql_migrations,
    bootstrap_ci_postgres_schema,
    reset_public_schema,
)

pytestmark = pytest.mark.integration_db


def _postgres_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url or "sqlite" in url:
        pytest.skip("DATABASE_URL postgres required for integration_db migration tests")
    return url


def _constraint_names(engine, table_name: str) -> set[str]:
    inspector = inspect(engine)
    names = {c.get("name") for c in inspector.get_unique_constraints(table_name)}
    names.update(c.get("name") for c in inspector.get_check_constraints(table_name))
    names.update(c.get("name") for c in inspector.get_foreign_keys(table_name))
    return {name for name in names if name}


def test_migration_021_on_empty_database():
    engine = create_engine(_postgres_url())
    try:
        reset_public_schema(engine)
        apply_pre_migration_baseline(engine)
        apply_versioned_sql_migrations(engine, ORDERED_MIGRATION_FILES)
        inspector = inspect(engine)
        assert "live_eval_llm_operations" in inspector.get_table_names()
        columns = {col["name"] for col in inspector.get_columns("live_eval_runs")}
        assert "llm_provider" in columns
        assert "llm_requested_model" in columns
        assert "llm_max_calls" in columns
        constraints = _constraint_names(engine, "live_eval_llm_operations")
        assert "uq_live_eval_llm_operations_operation_key" in constraints
        assert "uq_live_eval_llm_operations_run_prompt" in constraints
        assert "uq_live_eval_llm_operations_run_ordinal" in constraints
        assert "ck_live_eval_llm_operations_ordinal" in constraints
        assert "fk_live_eval_llm_operations_run" in constraints
    finally:
        engine.dispose()


def test_migration_021_idempotent_on_existing_live_eval_schema():
    engine = create_engine(_postgres_url())
    try:
        bootstrap_ci_postgres_schema(engine)
        with engine.begin() as conn:
            conn.execute(text("SELECT 1 FROM live_eval_llm_operations LIMIT 1"))
        bootstrap_ci_postgres_schema(engine)
        inspector = inspect(engine)
        assert "live_eval_llm_operations" in inspector.get_table_names()
    finally:
        engine.dispose()
