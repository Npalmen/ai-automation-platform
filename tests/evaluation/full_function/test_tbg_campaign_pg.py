"""PostgreSQL TBG full-function campaign tests."""

from __future__ import annotations

import pytest

from app.evaluation.full_function.db import cleanup_eval_tenants, initialize_database
from app.evaluation.full_function.registry import EXPECTED_SCENARIO_IDS
from app.evaluation.full_function.runner import run_evaluation
from tests.helpers.full_function_eval_pg import eval_engine, full_function_eval_database_url


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
def test_tbg_scenario_passes(pg_engine, scenario_id, tmp_path):
    report = run_evaluation(
        full_function_eval_database_url(),
        report_json=str(tmp_path / f"{scenario_id}.json"),
        report_markdown=str(tmp_path / f"{scenario_id}.md"),
        keep_data=False,
        scenario_filter=scenario_id,
    )
    assert report["overall_result"] == "PASS", report


@pytest.mark.pg_eval
def test_tbg_full_campaign_passes(pg_engine, tmp_path):
    report = run_evaluation(
        full_function_eval_database_url(),
        report_json=str(tmp_path / "tbg.json"),
        report_markdown=str(tmp_path / "tbg.md"),
        keep_data=False,
    )
    assert report["overall_result"] == "PASS"
    assert report.get("qualification") == "FULL_FUNCTION_MATRIX_PASS"
    assert report["repeat_run_consistent"] is True, sorted((report.get("repeat_hash_mismatches") or {}).keys())
    assert report["new_live_external_writes"] == 0
