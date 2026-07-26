"""PostgreSQL test helpers for end-customer foundation tests."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

END_CUSTOMER_FOUNDATION_TABLES: tuple[str, ...] = (
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

END_CUSTOMER_CONSTRAINT_NAMES: tuple[tuple[str, str], ...] = (
    ("end_customers", "ck_end_customers_version"),
    ("end_customer_source_facts", "ck_end_customer_source_facts_confidence"),
    ("end_customer_job_links", "ck_end_customer_job_links_confidence"),
    ("end_customer_thread_links", "ck_end_customer_thread_links_confidence"),
    ("end_customer_duplicate_candidates", "ck_end_customer_duplicate_candidates_version"),
    ("end_customer_duplicate_candidates", "ck_end_customer_duplicate_candidates_confidence"),
    ("end_customer_duplicate_candidates", "ck_end_customer_duplicate_candidates_pair_order"),
    ("end_customer_duplicate_candidates", "ck_end_customer_duplicate_candidates_pair_distinct"),
)


def postgres_database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url or "sqlite" in url:
        pytest.skip("DATABASE_URL postgres required for end-customer PostgreSQL tests")
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"PostgreSQL not reachable: {exc}")
    finally:
        engine.dispose()
    return url


def teardown_end_customer_foundation_tables(engine: Engine) -> None:
    """Reverse-order cleanup for migration rehearsal tests — not production rollback."""
    with engine.begin() as conn:
        for table_name in END_CUSTOMER_FOUNDATION_TABLES:
            conn.execute(text(f"DROP TABLE IF EXISTS {table_name} CASCADE"))
