"""PostgreSQL TBF campaign scenario tests."""

from __future__ import annotations

import pytest

from app.evaluation.customer_domain.actions import EvalContext
from app.evaluation.customer_domain.campaign import CampaignRun, tenant_id_for_scenario
from app.evaluation.customer_domain.db import cleanup_eval_tenants, ensure_eval_tenant, initialize_database
from app.evaluation.customer_domain.registry import load_tbf_runners
from tests.helpers.customer_domain_eval_pg import eval_engine


@pytest.fixture()
def pg_engine():
    engine = eval_engine()
    initialize_database(engine)
    cleanup_eval_tenants(engine)
    yield engine
    cleanup_eval_tenants(engine)
    engine.dispose()


def _run_tbf(pg_engine, scenario_id: str):
    from sqlalchemy.orm import sessionmaker

    campaign = CampaignRun()
    tenant_id = tenant_id_for_scenario(campaign, scenario_id)
    session = sessionmaker(bind=pg_engine)()
    try:
        ensure_eval_tenant(session, tenant_id, tenant_id.lower())
        session.commit()
    finally:
        session.close()
    ctx = EvalContext(
        engine=pg_engine,
        tenant_id=tenant_id,
        campaign=campaign,
        scenario_id=scenario_id,
    )
    return load_tbf_runners()[scenario_id](ctx)


@pytest.mark.pg_eval
@pytest.mark.parametrize("scenario_id", [f"TBF{index:02d}" for index in range(1, 11)])
def test_tbf_scenario_passes(pg_engine, scenario_id):
    result = _run_tbf(pg_engine, scenario_id)
    assert result.result == "PASS", result.failures


@pytest.mark.pg_eval
def test_tbf_campaign_cleanup(pg_engine):
    from app.evaluation.customer_domain.campaign import verify_campaign_cleanup
    from app.evaluation.customer_domain.runner import _run_tbf_campaign

    _, campaign = _run_tbf_campaign(pg_engine)
    cleanup = verify_campaign_cleanup(pg_engine, campaign)
    assert cleanup["cleanup_status"] == "restored"
