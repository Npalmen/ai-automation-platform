"""PostgreSQL migration test for shadow ledger."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.evaluation.customer_domain.db import initialize_database
from app.repositories.postgres.migration_runner import LATEST_MIGRATION_VERSION
from tests.helpers.customer_domain_eval_pg import eval_engine


@pytest.mark.pg_eval
def test_shadow_tables_exist_after_migration_chain():
    engine = eval_engine()
    initialize_database(engine)
    try:
        with engine.connect() as conn:
            for table in (
                "end_customer_shadow_observations",
                "end_customer_shadow_identity_signals",
                "end_customer_shadow_fact_proposals",
                "end_customer_shadow_match_proposals",
            ):
                exists = conn.execute(
                    text("SELECT to_regclass(:name)"),
                    {"name": f"public.{table}"},
                ).scalar()
                assert exists is not None, table
        assert LATEST_MIGRATION_VERSION == "024"
    finally:
        engine.dispose()
