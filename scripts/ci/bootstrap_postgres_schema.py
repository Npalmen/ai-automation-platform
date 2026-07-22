#!/usr/bin/env python3
"""Bootstrap PostgreSQL schema for CI integration_db tests."""

from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine

from app.repositories.postgres.migration_runner import bootstrap_ci_postgres_schema


def main() -> int:
    env = os.environ.get("ENV", "").strip()
    if env != "test":
        print("ENV must be exactly 'test' for PostgreSQL bootstrap", file=sys.stderr)
        return 1

    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        print("DATABASE_URL is required for PostgreSQL bootstrap", file=sys.stderr)
        return 1

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        state = bootstrap_ci_postgres_schema(engine)
    except Exception as exc:
        print(f"PostgreSQL bootstrap failed: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    print(f"bootstrap complete: latest_migration={state['latest_version']}")
    for filename in state["applied_files"]:
        print(f"  applied: {filename}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
