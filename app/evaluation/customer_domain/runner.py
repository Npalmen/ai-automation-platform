"""Customer domain stateful evaluation runner."""

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

from app.evaluation.customer_domain.controls import (
    run_concurrency_controls,
    run_feature_flag_controls,
    run_security_controls,
    run_tenant_controls,
    tenant_control_ids,
)
from app.evaluation.customer_domain.db import (
    cleanup_eval_tenants,
    count_non_eval_rows,
    create_eval_engine,
    ensure_eval_tenant,
    initialize_database,
)
from app.evaluation.customer_domain.guards import (
    EVAL_TENANT_PREFIX,
    EvalGuardError,
    ExternalSideEffectGuard,
    assert_eval_database_url,
    assert_eval_environment,
    install_external_guards,
)
from app.evaluation.customer_domain.reporting import (
    build_report,
    write_json_report,
    write_markdown_report,
)
from app.evaluation.customer_domain.scenarios.family_01_private_customer import run as run_family_01
from app.evaluation.customer_domain.scenarios.family_02_returning_customer import run as run_family_02
from app.evaluation.customer_domain.scenarios.family_03_changed_information import run as run_family_03
from app.evaluation.customer_domain.scenarios.family_04_company_contacts import run as run_family_04
from app.evaluation.customer_domain.scenarios.family_05_ambiguous_identity import run as run_family_05
from app.evaluation.customer_domain.scenarios._common import ScenarioRunResult
from app.evaluation.customer_domain.actions import EvalContext
from app.evaluation.customer_domain.registry import load_tbf_runners, validate_manifest
from app.evaluation.customer_domain.tbf2_registry import load_tbf2_runners, validate_manifest as validate_tbf2_manifest
from app.evaluation.customer_domain.semantic_hash import semantic_hash
from app.evaluation.customer_domain.campaign import (
    CampaignRun,
    build_campaign_oracle,
    snapshot_campaign_state,
    tenant_id_for_scenario,
    verify_campaign_cleanup,
)


DEFERRED_CAPABILITIES = [
    "operator add-contact route (repository arrange)",
    "operator thread-link route (repository arrange)",
    "operator duplicate-candidate create route (repository arrange)",
    "automatic matching/linking/merge",
]

FAMILY_RUNNERS = {
    "family_01": run_family_01,
    "family_02": run_family_02,
    "family_03": run_family_03,
    "family_04": run_family_04,
    "family_05": run_family_05,
    "all": None,
}


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def _tenant_id(scenario_suffix: str) -> str:
    return f"{EVAL_TENANT_PREFIX}{scenario_suffix}"


def _prepare_tenant(engine, tenant_id: str) -> None:
    session = sessionmaker(bind=engine)()
    try:
        ensure_eval_tenant(session, tenant_id, tenant_id.lower())
        session.commit()
    finally:
        session.close()


def _run_tbf_campaign(engine, scenario_filter: str = "all") -> tuple[list[ScenarioRunResult], CampaignRun]:
    campaign = CampaignRun()
    runners = load_tbf_runners()
    manifest_failures = validate_manifest()
    if manifest_failures:
        blocked = ScenarioRunResult(
            scenario_id="TBF_MANIFEST",
            family="tbf",
            tenant_id="eval_cd_manifest",
            result="BLOCKED",
            failures=manifest_failures,
        )
        return [blocked], campaign

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


def _run_tbf2_campaign(
    engine,
    scenario_filter: str = "all",
    *,
    pipeline_mode: bool = False,
) -> tuple[list[ScenarioRunResult], CampaignRun]:
    campaign = CampaignRun()
    runners = load_tbf2_runners()
    manifest_failures = validate_tbf2_manifest()
    if manifest_failures:
        blocked = ScenarioRunResult(
            scenario_id="TBF2_MANIFEST",
            family="tbf2",
            tenant_id="eval_cd_manifest",
            result="BLOCKED",
            failures=manifest_failures,
        )
        return [blocked], campaign

    results: list[ScenarioRunResult] = []
    for scenario_id, runner in runners.items():
        if scenario_filter != "all" and scenario_filter != scenario_id:
            continue
        tenant_id = tenant_id_for_scenario(campaign, scenario_id.replace("-", "").lower())
        campaign.register_tenant(tenant_id, scenario_id)
        _prepare_tenant(engine, tenant_id)
        ctx = EvalContext(
            engine=engine,
            tenant_id=tenant_id,
            campaign=campaign,
            scenario_id=scenario_id,
            pipeline_mode=pipeline_mode,
        )
        results.append(runner(ctx))
    campaign.pre_run_snapshot = {
        "normalized_hash": semantic_hash(snapshot_campaign_state(engine, campaign.registered_tenants)),
    }
    return results, campaign


def _run_families(engine, scenario_filter: str = "all") -> list[ScenarioRunResult]:
    runners = [
        (run_family_01, _tenant_id("family01"), "family_01"),
        (run_family_02, _tenant_id("family02"), "family_02"),
        (run_family_03, _tenant_id("family03"), "family_03"),
        (run_family_04, _tenant_id("family04"), "family_04"),
        (run_family_05, _tenant_id("family05"), "family_05"),
    ]
    results: list[ScenarioRunResult] = []
    for runner, tenant_id, key in runners:
        if scenario_filter != "all" and scenario_filter != key:
            continue
        _prepare_tenant(engine, tenant_id)
        ctx = EvalContext(engine=engine, tenant_id=tenant_id)
        results.append(runner(ctx))
    return results


def run_evaluation(
    database_url: str,
    *,
    report_json: str,
    report_markdown: str,
    keep_data: bool = False,
    scenario_filter: str = "all",
    campaign: str = "families",
) -> dict[str, Any]:
    started = datetime.now(timezone.utc)
    assert_eval_environment()
    db_fingerprint = assert_eval_database_url(database_url)
    guard = ExternalSideEffectGuard()

    campaign_oracle: dict[str, Any] | None = None
    cleanup_result: dict[str, Any] | None = None
    run1: list[ScenarioRunResult] = []

    with ExitStack() as stack:
        for module, attr, replacement in install_external_guards(guard):
            stack.enter_context(patch.object(module, attr, replacement))

        engine = create_eval_engine(database_url)
        initialize_database(engine)
        non_eval_before = count_non_eval_rows(engine)

        try:
            cleanup_eval_tenants(engine)
            if campaign == "tbf":
                run1, campaign_run = _run_tbf_campaign(engine, scenario_filter)
                hashes1 = {r.scenario_id: r.to_report()["semantic_result_hash"] for r in run1}

                cleanup_eval_tenants(engine)
                run2, _ = _run_tbf_campaign(engine, scenario_filter)
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
            elif campaign in {"tbf2", "tbf2b"}:
                pipeline_mode = campaign == "tbf2b"
                run1, campaign_run = _run_tbf2_campaign(
                    engine, scenario_filter, pipeline_mode=pipeline_mode
                )
                hashes1 = {r.scenario_id: r.to_report()["semantic_result_hash"] for r in run1}

                cleanup_eval_tenants(engine)
                run2, _ = _run_tbf2_campaign(
                    engine, scenario_filter, pipeline_mode=pipeline_mode
                )
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
            else:
                campaign_run = None
                campaign_oracle = None
                cleanup_result = None
                run1 = _run_families(engine, scenario_filter)
                hashes1 = {r.scenario_id: r.to_report()["semantic_result_hash"] for r in run1}

                cleanup_eval_tenants(engine)
                run2 = _run_families(engine, scenario_filter)
                hashes2 = {r.scenario_id: r.to_report()["semantic_result_hash"] for r in run2}
                repeat_ok = hashes1 == hashes2

            tenant_a, tenant_b = tenant_control_ids("iso")
            tenant_controls = run_tenant_controls(engine, tenant_a, tenant_b)
            concurrency_controls = run_concurrency_controls(engine, _tenant_id("concurrency"))
            feature_flag_controls = run_feature_flag_controls()
            security_controls = run_security_controls(engine, _tenant_id("security"))

            non_eval_after = count_non_eval_rows(engine)
            non_eval_changed = max(0, non_eval_after - non_eval_before)
        finally:
            if not keep_data:
                cleanup_eval_tenants(engine)

    completed = datetime.now(timezone.utc)
    scenarios = [r.to_report() for r in run1]
    report = build_report(
        git_sha=_git_sha(),
        database_kind="postgresql",
        database_fingerprint=db_fingerprint,
        scenarios=scenarios,
        tenant_controls=tenant_controls,
        concurrency_controls=concurrency_controls,
        security_controls=security_controls,
        feature_flag_controls=feature_flag_controls,
        external_side_effects=guard.count,
        non_eval_rows_changed=non_eval_changed,
        repeat_run_consistent=repeat_ok,
        deferred_capabilities=DEFERRED_CAPABILITIES,
        h_gap_findings=[],
        started_at=started,
        completed_at=completed,
        campaign_type=campaign,
        campaign_oracle=campaign_oracle,
        cleanup_result=cleanup_result,
    )
    if campaign == "tbf" and report["overall_result"] == "PASS":
        report["qualification"] = "CUSTOMER_CARD_STATEFUL_DIRECT_QUALIFIED"
    if campaign == "tbf2" and report["overall_result"] == "PASS":
        report["qualification"] = "CUSTOMER_CARD_SHADOW_DOMAIN_QUALIFIED"
    if campaign == "tbf2b" and report["overall_result"] == "PASS":
        report["qualification"] = "CUSTOMER_CARD_SHADOW_PIPELINE_QUALIFIED"
    write_json_report(Path(report_json), report)
    write_markdown_report(Path(report_markdown), report)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Customer domain stateful evaluation")
    parser.add_argument("--database-url", required=True)
    parser.add_argument(
        "--report-json",
        default="storage/status/customer-domain-stateful-eval.json",
    )
    parser.add_argument(
        "--report-markdown",
        default="storage/status/customer-domain-stateful-eval.md",
    )
    parser.add_argument("--scenario", default="all")
    parser.add_argument("--campaign", default="families", choices=["families", "tbf", "tbf2", "tbf2b"])
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
            campaign=args.campaign,
        )
        print(report["overall_result"])
        return 0 if report["overall_result"] == "PASS" else 1
    except EvalGuardError as exc:
        print(f"BLOCKED: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
