"""PostgreSQL TBF2 shadow campaign tests."""

from __future__ import annotations

import pytest

from app.evaluation.customer_domain.db import cleanup_eval_tenants, initialize_database
from app.evaluation.customer_domain.runner import run_evaluation
from app.evaluation.customer_domain.tbf2_registry import EXPECTED_SCENARIO_IDS
from tests.helpers.customer_domain_eval_pg import customer_domain_eval_database_url, eval_engine


@pytest.fixture()
def pg_engine():
    engine = eval_engine()
    initialize_database(engine)
    cleanup_eval_tenants(engine)
    yield engine
    cleanup_eval_tenants(engine)
    engine.dispose()


@pytest.mark.pg_eval
@pytest.mark.parametrize("scenario_id", EXPECTED_SCENARIO_IDS)
def test_tbf2_scenario_passes(pg_engine, scenario_id, tmp_path):
    report = run_evaluation(
        customer_domain_eval_database_url(),
        report_json=str(tmp_path / f"{scenario_id}.json"),
        report_markdown=str(tmp_path / f"{scenario_id}.md"),
        keep_data=False,
        scenario_filter=scenario_id,
        campaign="tbf2",
    )
    assert report["overall_result"] == "PASS", report


@pytest.mark.pg_eval
def test_tbf2_full_campaign_passes(pg_engine, tmp_path):
    report = run_evaluation(
        customer_domain_eval_database_url(),
        report_json=str(tmp_path / "tbf2.json"),
        report_markdown=str(tmp_path / "tbf2.md"),
        keep_data=False,
        campaign="tbf2",
    )
    assert report["overall_result"] == "PASS"
    assert report.get("qualification") == "CUSTOMER_CARD_SHADOW_DOMAIN_QUALIFIED"
    assert report["repeat_run_consistent"] is True


@pytest.mark.pg_eval
def test_tbf2b_pipeline_campaign_passes(pg_engine, tmp_path):
    report = run_evaluation(
        customer_domain_eval_database_url(),
        report_json=str(tmp_path / "tbf2b.json"),
        report_markdown=str(tmp_path / "tbf2b.md"),
        keep_data=False,
        campaign="tbf2b",
    )
    assert report["overall_result"] == "PASS"
    assert report.get("qualification") == "CUSTOMER_CARD_SHADOW_PIPELINE_QUALIFIED"
