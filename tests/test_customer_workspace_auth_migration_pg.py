"""PostgreSQL migration tests for customer workspace auth tables."""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.repositories.postgres.migration_runner import bootstrap_ci_postgres_schema
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
    engine = create_engine(_postgres_url())
    try:
        bootstrap_ci_postgres_schema(engine)
        ensure_runtime_schema(engine)

        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert "customer_workspace_users" in tables
        assert "customer_workspace_sessions" in tables

        user_indexes = {idx["name"] for idx in inspector.get_indexes("customer_workspace_users")}
        session_indexes = {idx["name"] for idx in inspector.get_indexes("customer_workspace_sessions")}
        assert "ux_customer_workspace_users_active_email" in user_indexes
        assert "ux_customer_workspace_sessions_token_hash" in session_indexes
        assert "ix_customer_workspace_users_tenant" in user_indexes
        assert "ix_customer_workspace_sessions_user" in session_indexes
        assert "ix_customer_workspace_sessions_tenant" in session_indexes

        Session = sessionmaker(bind=engine)
        db = Session()
        user_id = str(uuid4())
        session_id = str(uuid4())
        email = f"auth-migration-{uuid4().hex[:12]}@example.com"
        token_hash = f"hash-{uuid4().hex}"
        try:
            db.execute(
                text(
                    """
                    INSERT INTO customer_workspace_users
                    (id, tenant_id, email, password_hash, display_name, role, status, created_at, updated_at)
                    VALUES
                    (:user_id, 'T1', :email, 'hash', 'A', 'customer_viewer', 'active', NOW(), NOW())
                    """
                ),
                {"user_id": user_id, "email": email},
            )
            db.commit()
            with pytest.raises(Exception):
                db.execute(
                    text(
                        """
                        INSERT INTO customer_workspace_users
                        (id, tenant_id, email, password_hash, display_name, role, status, created_at, updated_at)
                        VALUES
                        (:user_id, 'T2', :email, 'hash', 'B', 'customer_viewer', 'active', NOW(), NOW())
                        """
                    ),
                    {"user_id": str(uuid4()), "email": email},
                )
                db.commit()
            db.rollback()

            db.execute(
                text(
                    """
                    INSERT INTO customer_workspace_sessions
                    (id, user_id, tenant_id, token_hash, expires_at, created_at)
                    VALUES
                    (:session_id, :user_id, 'T1', :token_hash, NOW() + INTERVAL '1 hour', NOW())
                    """
                ),
                {"session_id": session_id, "user_id": user_id, "token_hash": token_hash},
            )
            db.commit()
            with pytest.raises(Exception):
                db.execute(
                    text(
                        """
                        INSERT INTO customer_workspace_sessions
                        (id, user_id, tenant_id, token_hash, expires_at, created_at)
                        VALUES
                        (:session_id, :user_id, 'T1', :token_hash, NOW() + INTERVAL '1 hour', NOW())
                        """
                    ),
                    {
                        "session_id": str(uuid4()),
                        "user_id": user_id,
                        "token_hash": token_hash,
                    },
                )
                db.commit()
            db.rollback()
        finally:
            db.execute(
                text("DELETE FROM customer_workspace_sessions WHERE user_id = :user_id"),
                {"user_id": user_id},
            )
            db.execute(
                text("DELETE FROM customer_workspace_users WHERE id = :user_id"),
                {"user_id": user_id},
            )
            db.commit()
            db.close()

        ensure_runtime_schema(engine)
        assert len(_CUSTOMER_WORKSPACE_AUTH_MIGRATION_STATEMENTS) >= 6
    finally:
        engine.dispose()
