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

        cleanup_eval_tenants(engine)
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
    )
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
    parser.add_argument("--scenario", default="all", choices=list(FAMILY_RUNNERS.keys()))
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
