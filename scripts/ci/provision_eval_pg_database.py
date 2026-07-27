#!/usr/bin/env python3
"""Idempotently create the PostgreSQL eval database for CI."""

from __future__ import annotations

import os
import sys

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT


def main() -> int:
    admin_url = os.environ.get(
        "PG_ADMIN_URL",
        "postgresql://postgres:postgres@localhost:5432/postgres",
    )
    database_name = os.environ.get("EVAL_PG_DATABASE", "ai_platform_eval")
    extra_databases = [database_name]
    if database_name == "ai_platform_eval":
        extra_databases.append("ai_platform_customer_domain_eval")

    conn = psycopg2.connect(admin_url)
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with conn.cursor() as cur:
            for name in extra_databases:
                cur.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s",
                    (name,),
                )
                if cur.fetchone() is None:
                    cur.execute(f'CREATE DATABASE "{name}"')
                    print(f"created database {name}")
                else:
                    print(f"database {name} already exists")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
