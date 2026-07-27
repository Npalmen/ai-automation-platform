"""PostgreSQL helpers for customer-domain stateful evaluation tests."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from app.evaluation.customer_domain.guards import REQUIRED_DB_NAME_FRAGMENT

DEFAULT_EVAL_DB_NAME = "ai_platform_customer_domain_eval"


def _base_postgres_url(url: str) -> str:
    return url.rsplit("/", 1)[0]


def resolve_customer_domain_eval_database_url() -> str:
    explicit = os.environ.get("CUSTOMER_DOMAIN_EVAL_DATABASE_URL", "").strip()
    if explicit:
        return explicit
    eval_url = os.environ.get("EVAL_DATABASE_URL", "").strip()
    if eval_url:
        return f"{_base_postgres_url(eval_url)}/{DEFAULT_EVAL_DB_NAME}"
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url and "sqlite" not in database_url:
        return f"{_base_postgres_url(database_url)}/{DEFAULT_EVAL_DB_NAME}"
    return ""


def customer_domain_eval_database_url() -> str:
    url = resolve_customer_domain_eval_database_url()
    if not url or "sqlite" in url:
        pytest.skip("PostgreSQL eval URL required for customer-domain eval tests")
    db_name = url.rsplit("/", 1)[-1].lower()
    if REQUIRED_DB_NAME_FRAGMENT not in db_name:
        pytest.skip(
            f"database name must contain '{REQUIRED_DB_NAME_FRAGMENT}' (got '{db_name}')"
        )
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL not reachable: {exc}")
    finally:
        engine.dispose()
    return url


def eval_engine() -> Engine:
    return create_engine(customer_domain_eval_database_url(), pool_pre_ping=True)
