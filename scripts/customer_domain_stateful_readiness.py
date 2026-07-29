#!/usr/bin/env python3
"""Offline readiness checks for customer-card TBF stateful evaluation."""

from __future__ import annotations

import argparse
import os
import sys

from app.core.settings import get_settings
from app.evaluation.customer_domain.guards import (
    EVAL_TENANT_PREFIX,
    REQUIRED_DB_NAME_FRAGMENT,
    assert_eval_environment,
)
from app.evaluation.customer_domain.registry import validate_manifest


def run_readiness(*, database_url: str) -> dict[str, object]:
    assert_eval_environment()
    settings = get_settings()
    failures: list[str] = []

    db_name = database_url.rsplit("/", 1)[-1].lower()
    if REQUIRED_DB_NAME_FRAGMENT not in db_name:
        failures.append(
            f"database name must contain '{REQUIRED_DB_NAME_FRAGMENT}', got '{db_name}'"
        )
    if "prod" in db_name or "production" in db_name:
        failures.append("production database signals detected")

    if not EVAL_TENANT_PREFIX:
        failures.append("eval tenant prefix missing")

    manifest_failures = validate_manifest()
    failures.extend(manifest_failures)

    if settings.END_CUSTOMER_READ_API_ENABLED:
        failures.append("END_CUSTOMER_READ_API_ENABLED must default false outside test process")
    if settings.END_CUSTOMER_WRITE_API_ENABLED:
        failures.append("END_CUSTOMER_WRITE_API_ENABLED must default false outside test process")

    return {
        "ready": not failures,
        "failures": failures,
        "database_url": database_url,
        "tenant_prefix": EVAL_TENANT_PREFIX,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Customer domain TBF readiness")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("CUSTOMER_DOMAIN_EVAL_DATABASE_URL", ""),
    )
    args = parser.parse_args(argv)
    if not args.database_url:
        print("BLOCKED: database URL required")
        return 2
    result = run_readiness(database_url=args.database_url)
    if result["ready"]:
        print("READY")
        return 0
    print("BLOCKED")
    for failure in result["failures"]:
        print(f"- {failure}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
