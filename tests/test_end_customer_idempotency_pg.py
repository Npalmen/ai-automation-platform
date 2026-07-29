"""PostgreSQL tests for end-customer write idempotency (023)."""

from __future__ import annotations

import threading
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from app.repositories.postgres.end_customer_idempotency_repository import (
    EndCustomerIdempotencyConflictError,
    EndCustomerIdempotencyRepository,
)
from app.repositories.postgres.migration_runner import (
    LATEST_MIGRATION_VERSION,
    ORDERED_MIGRATION_FILES,
    apply_pre_migration_baseline,
    apply_versioned_sql_migrations,
    reset_public_schema,
)
from tests.helpers.end_customer_pg import (
    END_CUSTOMER_IDEMPOTENCY_TABLE,
    postgres_database_url,
    teardown_end_customer_foundation_tables,
)


def _postgres_url() -> str:
    return postgres_database_url()


@pytest.fixture()
def pg_engine():
    engine = create_engine(_postgres_url())
    reset_public_schema(engine)
    apply_pre_migration_baseline(engine)
    apply_versioned_sql_migrations(engine, ORDERED_MIGRATION_FILES)
    yield engine
    teardown_end_customer_foundation_tables(engine)
    engine.dispose()


def test_migration_023_registered():
    assert LATEST_MIGRATION_VERSION == "024"
    assert ORDERED_MIGRATION_FILES[-1] == "024_end_customer_shadow_ledger.sql"


def test_idempotency_table_exists(pg_engine):
    inspector = inspect(pg_engine)
    assert END_CUSTOMER_IDEMPOTENCY_TABLE in inspector.get_table_names()
    unique = {c["name"] for c in inspector.get_unique_constraints(END_CUSTOMER_IDEMPOTENCY_TABLE)}
    assert "uq_end_customer_idempotency_scope" in unique


def test_same_key_different_tenants_allowed(pg_engine):
    session = sessionmaker(bind=pg_engine)()
    key = f"key-{uuid4()}"
    hash_a = "hash-a"
    hash_b = "hash-b"
    id_a = EndCustomerIdempotencyRepository.acquire(session, "TENANT_A", "create_customer", key, hash_a)
    session.commit()
    id_b = EndCustomerIdempotencyRepository.acquire(session, "TENANT_B", "create_customer", key, hash_b)
    session.commit()
    assert isinstance(id_a, str)
    assert isinstance(id_b, str)
    session.close()


def test_same_key_different_operations_allowed(pg_engine):
    session = sessionmaker(bind=pg_engine)()
    key = f"key-{uuid4()}"
    id_create = EndCustomerIdempotencyRepository.acquire(
        session, "TENANT_A", "create_customer", key, "hash-1"
    )
    session.commit()
    id_update = EndCustomerIdempotencyRepository.acquire(
        session, "TENANT_A", "update_customer", key, "hash-2"
    )
    session.commit()
    assert isinstance(id_create, str)
    assert isinstance(id_update, str)
    session.close()


def test_replay_same_hash(pg_engine):
    session = sessionmaker(bind=pg_engine)()
    key = f"key-{uuid4()}"
    request_hash = "stable-hash"
    record_id = EndCustomerIdempotencyRepository.acquire(
        session, "TENANT_A", "create_customer", key, request_hash
    )
    EndCustomerIdempotencyRepository.complete(
        session,
        record_id,
        201,
        {"customer_id": "cust-1"},
        {"customer_id": "cust-1"},
    )
    session.commit()

    replay = EndCustomerIdempotencyRepository.acquire(
        session, "TENANT_A", "create_customer", key, request_hash
    )
    assert replay.response_status_code == 201
    assert replay.response_body == {"customer_id": "cust-1"}
    session.close()


def test_conflict_on_different_hash(pg_engine):
    session = sessionmaker(bind=pg_engine)()
    key = f"key-{uuid4()}"
    record_id = EndCustomerIdempotencyRepository.acquire(
        session, "TENANT_A", "create_customer", key, "hash-one"
    )
    EndCustomerIdempotencyRepository.complete(
        session, record_id, 201, {"ok": True}, {"customer_id": "c1"}
    )
    session.commit()
    with pytest.raises(EndCustomerIdempotencyConflictError):
        EndCustomerIdempotencyRepository.acquire(
            session, "TENANT_A", "create_customer", key, "hash-two"
        )
    session.close()


def test_failure_leaves_no_row(pg_engine):
    session = sessionmaker(bind=pg_engine)()
    key = f"key-{uuid4()}"
    record_id = EndCustomerIdempotencyRepository.acquire(
        session, "TENANT_A", "create_customer", key, "hash-fail"
    )
    session.rollback()
    with pg_engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT COUNT(*) FROM end_customer_idempotency_records "
                "WHERE tenant_id = :tenant AND idempotency_key = :key"
            ),
            {"tenant": "TENANT_A", "key": key},
        ).scalar_one()
    assert count == 0
    session.close()


def test_concurrent_same_payload_one_write(pg_engine):
    barrier = threading.Barrier(2)
    results: list[str | Exception] = []

    def worker():
        session = sessionmaker(bind=pg_engine)()
        key = "concurrent-key"
        request_hash = "same-hash"
        try:
            barrier.wait(timeout=10)
            acquired = EndCustomerIdempotencyRepository.acquire(
                session, "TENANT_A", "create_customer", key, request_hash
            )
            if isinstance(acquired, str):
                EndCustomerIdempotencyRepository.complete(
                    session,
                    acquired,
                    201,
                    {"customer_id": "cust-concurrent"},
                    {"customer_id": "cust-concurrent"},
                )
                session.commit()
                results.append("write")
            else:
                session.rollback()
                results.append("replay")
        except Exception as exc:
            session.rollback()
            results.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert len(results) == 2
    assert results.count("write") == 1
    assert results.count("replay") == 1
