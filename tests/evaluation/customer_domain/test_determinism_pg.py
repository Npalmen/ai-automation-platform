"""Repeat-run determinism tests for customer-domain stateful evaluation."""

from __future__ import annotations

import pytest

from app.evaluation.customer_domain.actions import EvalContext
from app.evaluation.customer_domain.db import cleanup_eval_tenants, initialize_database
from app.evaluation.customer_domain.scenarios.family_01_private_customer import run as run_family_01
from app.evaluation.customer_domain.scenarios.family_03_changed_information import run as run_family_03
from tests.helpers.customer_domain_eval_pg import eval_engine


@pytest.fixture()
def pg_engine():
    engine = eval_engine()
    initialize_database(engine)
    yield engine
    cleanup_eval_tenants(engine)
    engine.dispose()


def _run_twice(engine, tenant_id: str, runner):
    from sqlalchemy.orm import sessionmaker

    from app.evaluation.customer_domain.db import ensure_eval_tenant

    def once():
        session = sessionmaker(bind=engine)()
        try:
            ensure_eval_tenant(session, tenant_id, tenant_id.lower())
            session.commit()
        finally:
            session.close()
        ctx = EvalContext(engine=engine, tenant_id=tenant_id)
        return runner(ctx)

    cleanup_eval_tenants(engine)
    first = once()
    cleanup_eval_tenants(engine)
    second = once()
    return first.to_report()["semantic_result_hash"], second.to_report()["semantic_result_hash"]


@pytest.mark.pg_eval
def test_family_01_repeat_run_semantic_hash(pg_engine):
    h1, h2 = _run_twice(pg_engine, "eval_cd_det_f01", run_family_01)
    assert h1 == h2


@pytest.mark.pg_eval
def test_family_03_repeat_run_semantic_hash(pg_engine):
    h1, h2 = _run_twice(pg_engine, "eval_cd_det_f03", run_family_03)
    assert h1 == h2
