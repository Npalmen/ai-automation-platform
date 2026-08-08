"""PostgreSQL migration tests for customer workspace auth tables."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.repositories.postgres.schema_migrations import (
    _CUSTOMER_WORKSPACE_AUTH_MIGRATION_STATEMENTS,
    ensure_runtime_schema,
)

pytestmark = pytest.mark.integration_db


def _postgres_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url or "sqlite" in url:
        pytest.skip("DATABASE_URL postgres required for integration_db migration tests")
    return url


def test_customer_workspace_auth_tables_and_indexes():
    engine = create_engine(_postgres_url(), isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    ensure_runtime_schema(engine)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "customer_workspace_users" in tables
    assert "customer_workspace_sessions" in tables

    user_indexes = {idx["name"] for idx in inspector.get_indexes("customer_workspace_users")}
    session_indexes = {idx["name"] for idx in inspector.get_indexes("customer_workspace_sessions")}
    assert "ux_customer_workspace_users_active_email" in user_indexes
    assert "ux_customer_workspace_sessions_token_hash" in session_indexes

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        db.execute(
            text(
                """
                INSERT INTO customer_workspace_users
                (id, tenant_id, email, password_hash, display_name, role, status, created_at, updated_at)
                VALUES
                ('u1', 'T1', 'a@example.com', 'hash', 'A', 'customer_viewer', 'active', NOW(), NOW())
                """
            )
        )
        db.commit()
        with pytest.raises(Exception):
            db.execute(
                text(
                    """
                    INSERT INTO customer_workspace_users
                    (id, tenant_id, email, password_hash, display_name, role, status, created_at, updated_at)
                    VALUES
                    ('u2', 'T2', 'a@example.com', 'hash', 'B', 'customer_viewer', 'active', NOW(), NOW())
                    """
                )
            )
            db.commit()
        db.rollback()
    finally:
        db.close()
        engine.dispose()

    assert len(_CUSTOMER_WORKSPACE_AUTH_MIGRATION_STATEMENTS) >= 6
