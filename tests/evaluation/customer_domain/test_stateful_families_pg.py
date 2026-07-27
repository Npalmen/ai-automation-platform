"""Stateful PostgreSQL scenario family tests."""

from __future__ import annotations

import pytest

from app.evaluation.customer_domain.actions import EvalContext
from app.evaluation.customer_domain.db import cleanup_eval_tenants, initialize_database
from app.evaluation.customer_domain.scenarios.family_01_private_customer import run as run_family_01
from app.evaluation.customer_domain.scenarios.family_02_returning_customer import run as run_family_02
from app.evaluation.customer_domain.scenarios.family_03_changed_information import run as run_family_03
from app.evaluation.customer_domain.scenarios.family_04_company_contacts import run as run_family_04
from app.evaluation.customer_domain.scenarios.family_05_ambiguous_identity import run as run_family_05
from tests.helpers.customer_domain_eval_pg import eval_engine


@pytest.fixture()
def pg_engine():
    engine = eval_engine()
    initialize_database(engine)
    cleanup_eval_tenants(engine)
    yield engine
    cleanup_eval_tenants(engine)
    engine.dispose()


def _run_family(engine, tenant_suffix: str, runner):
    tenant_id = f"eval_cd_pg_{tenant_suffix}"
    from sqlalchemy.orm import sessionmaker

    from app.evaluation.customer_domain.db import ensure_eval_tenant

    session = sessionmaker(bind=engine)()
    try:
        ensure_eval_tenant(session, tenant_id, tenant_id.lower())
        session.commit()
    finally:
        session.close()
    ctx = EvalContext(engine=engine, tenant_id=tenant_id)
    return runner(ctx)


@pytest.mark.pg_eval
def test_family_01_private_customer(pg_engine):
    result = _run_family(pg_engine, "f01", run_family_01)
    assert result.result == "PASS", result.failures


@pytest.mark.pg_eval
def test_family_02_returning_customer(pg_engine):
    result = _run_family(pg_engine, "f02", run_family_02)
    assert result.result == "PASS", result.failures


@pytest.mark.pg_eval
def test_family_03_changed_information(pg_engine):
    result = _run_family(pg_engine, "f03", run_family_03)
    assert result.result == "PASS", result.failures


@pytest.mark.pg_eval
def test_family_04_company_contacts(pg_engine):
    result = _run_family(pg_engine, "f04", run_family_04)
    assert result.result == "PASS", result.failures


@pytest.mark.pg_eval
def test_family_05_ambiguous_identity(pg_engine):
    result = _run_family(pg_engine, "f05", run_family_05)
    assert result.result == "PASS", result.failures
