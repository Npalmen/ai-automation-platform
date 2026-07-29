"""Full-function matrix evaluation runner."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import patch

from sqlalchemy.orm import sessionmaker

from app.evaluation.customer_domain.semantic_hash import semantic_hash
from app.evaluation.full_function.campaign import (
    CampaignRun,
    build_campaign_oracle,
    snapshot_campaign_state,
    tenant_id_for_scenario,
    verify_campaign_cleanup,
)
from app.evaluation.full_function.db import (
    cleanup_eval_tenants,
    count_non_eval_rows,
    create_eval_engine,
    ensure_eval_tenant,
    initialize_database,
)
from app.evaluation.full_function.guards import (
    EvalGuardError,
    ExternalSideEffectGuard,
    assert_eval_database_url,
    assert_eval_environment,
    install_external_guards,
)
from app.evaluation.full_function.matrix import matrix_status_summary, validate_matrix
from app.evaluation.full_function.registry import (
    validate_capabilities,
    validate_manifest,
    load_tbg_runners,
)
from app.evaluation.full_function.reporting import (
    build_report,
    write_json_report,
    write_markdown_report,
)
from app.evaluation.full_function.actions import EvalContext
from app.evaluation.full_function.scenarios._common import ScenarioRunResult


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _prepare_tenant(engine, tenant_id: str) -> None:
    session = sessionmaker(bind=engine)()
    try:
        ensure_eval_tenant(session, tenant_id, tenant_id.lower())
        session.commit()
    finally:
        session.close()


def _run_tbg_campaign(
    engine,
    scenario_filter: str = "all",
) -> tuple[list[ScenarioRunResult], CampaignRun]:
    campaign = CampaignRun()
    failures = validate_manifest() + validate_capabilities() + validate_matrix()
    if failures:
        blocked = ScenarioRunResult(
            scenario_id="TBG_MANIFEST",
            family="tbg",
            tenant_id="eval_ff_manifest",
            result="BLOCKED",
            failures=failures,
        )
        return [blocked], campaign

    runners = load_tbg_runners()
    results: list[ScenarioRunResult] = []
    for scenario_id, runner in runners.items():
        if scenario_filter != "all" and scenario_filter != scenario_id:
            continue
        tenant_id = tenant_id_for_scenario(campaign, scenario_id)
        campaign.register_tenant(tenant_id, scenario_id)
        _prepare_tenant(engine, tenant_id)
        ctx = EvalContext(
            engine=engine,
            tenant_id=tenant_id,
            campaign=campaign,
            scenario_id=scenario_id,
        )
        results.append(runner(ctx))
    campaign.pre_run_snapshot = {
        "normalized_hash": semantic_hash(snapshot_campaign_state(engine, campaign.registered_tenants)),
    }
    return results, campaign


def run_evaluation(
    database_url: str,
    *,
    report_json: str,
    report_markdown: str,
    keep_data: bool = False,
    scenario_filter: str = "all",
) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    assert_eval_environment()
    db_fingerprint = assert_eval_database_url(database_url)
    guard = ExternalSideEffectGuard()

    with ExitStack() as stack:
        for module, attr, replacement in install_external_guards(guard):
            stack.enter_context(patch.object(module, attr, replacement))

        engine = create_eval_engine(database_url)
        initialize_database(engine)
        non_eval_before = count_non_eval_rows(engine)

        try:
            cleanup_eval_tenants(engine)
            run1, campaign_run = _run_tbg_campaign(engine, scenario_filter)
            hashes1 = {r.scenario_id: r.to_report()["semantic_result_hash"] for r in run1}

            cleanup_eval_tenants(engine)
            run2, _ = _run_tbg_campaign(engine, scenario_filter)
            hashes2 = {r.scenario_id: r.to_report()["semantic_result_hash"] for r in run2}
            repeat_ok = hashes1 == hashes2
            cleanup_result = verify_campaign_cleanup(engine, campaign_run)
            campaign_oracle = build_campaign_oracle(
                campaign=campaign_run,
                scenario_results=[r.to_report() for r in run1],
                cleanup_result=cleanup_result,
            )
            if cleanup_result.get("cleanup_status") != "restored":
                repeat_ok = False
            non_eval_after = count_non_eval_rows(engine)
            non_eval_changed = max(0, non_eval_after - non_eval_before)
        finally:
            if not keep_data:
                cleanup_eval_tenants(engine)

    completed = datetime.now(timezone.utc)
    scenarios = [r.to_report() for r in run1]
    report = build_report(
        git_sha=_git_sha(),
        database_fingerprint=db_fingerprint,
        scenarios=scenarios,
        campaign_oracle=campaign_oracle,
        cleanup_result=cleanup_result,
        matrix_status_summary=matrix_status_summary(),
        external_side_effects=guard.count,
        repeat_run_consistent=repeat_ok,
        started_at=started,
        completed_at=completed,
    )
    if report["overall_result"] == "PASS":
        report["qualification"] = "FULL_FUNCTION_MATRIX_PASS"
    write_json_report(Path(report_json), report)
    write_markdown_report(Path(report_markdown), report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Full-function matrix evaluation")
    parser.add_argument("--database-url", required=True)
    parser.add_argument(
        "--report-json",
        default="storage/status/testbot-g-full-function-matrix.json",
    )
    parser.add_argument(
        "--report-markdown",
        default="storage/status/testbot-g-full-function-matrix.md",
    )
    parser.add_argument("--scenario", default="all")
    parser.add_argument("--keep-data", action="store_true", default=False)
    args = parser.parse_args(argv)
    os.environ.setdefault("ENV", "test")
    try:
        report = run_evaluation(
            args.database_url,
            report_json=args.report_json,
            report_markdown=args.report_markdown,
            keep_data=args.keep_data,
            scenario_filter=args.scenario,
        )
        print(report["overall_result"])
        return 0 if report["overall_result"] == "PASS" else 1
    except EvalGuardError as exc:
        print(f"BLOCKED: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
