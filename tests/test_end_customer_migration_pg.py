"""PostgreSQL migration tests for end-customer foundation (022)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect

from app.repositories.postgres.migration_runner import (
    LATEST_MIGRATION_VERSION,
    ORDERED_MIGRATION_FILES,
    apply_pre_migration_baseline,
    apply_versioned_sql_migrations,
    read_migration_state,
    reset_public_schema,
)
from tests.helpers.end_customer_pg import (
    END_CUSTOMER_CONSTRAINT_NAMES,
    END_CUSTOMER_FOUNDATION_TABLES,
    postgres_database_url,
    teardown_end_customer_foundation_tables,
)

EXPECTED_TABLES = tuple(reversed(END_CUSTOMER_FOUNDATION_TABLES))


def _postgres_url() -> str:
    return postgres_database_url()


def _constraint_names(engine, table_name: str) -> set[str]:
    inspector = inspect(engine)
    names = {c.get("name") for c in inspector.get_unique_constraints(table_name)}
    names.update(c.get("name") for c in inspector.get_check_constraints(table_name))
    names.update(c.get("name") for c in inspector.get_foreign_keys(table_name))
    return {name for name in names if name}


def test_migration_022_forward_on_empty_database():
    engine = create_engine(_postgres_url())
    try:
        reset_public_schema(engine)
        apply_pre_migration_baseline(engine)
        apply_versioned_sql_migrations(engine, ORDERED_MIGRATION_FILES)

        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        for table_name in EXPECTED_TABLES:
            assert table_name in table_names

        customer_columns = {col["name"] for col in inspector.get_columns("end_customers")}
        assert "version" in customer_columns
        assert "primary_company_id" in customer_columns

        for table_name, constraint_name in END_CUSTOMER_CONSTRAINT_NAMES:
            assert constraint_name in _constraint_names(engine, table_name)

        state = read_migration_state(engine)
        assert state["latest_version"] == LATEST_MIGRATION_VERSION
        assert ORDERED_MIGRATION_FILES[-1] == "022_end_customer_foundation.sql"
    finally:
        engine.dispose()


def test_migration_022_teardown_rehearsal_and_reforward():
    engine = create_engine(_postgres_url())
    try:
        reset_public_schema(engine)
        apply_pre_migration_baseline(engine)
        apply_versioned_sql_migrations(engine, ORDERED_MIGRATION_FILES)

        teardown_end_customer_foundation_tables(engine)
        inspector = inspect(engine)
        for table_name in EXPECTED_TABLES:
            assert table_name not in inspector.get_table_names()

        apply_versioned_sql_migrations(engine, ("022_end_customer_foundation.sql",))
        for table_name in EXPECTED_TABLES:
            assert table_name in inspect(engine).get_table_names()
    finally:
        engine.dispose()
