#!/usr/bin/env python3
"""CLI for Kapitel 2E deterministic evaluation harness."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from app.evaluation.coverage import validate_coverage
from app.evaluation.dataset_manifest import (
    DEFAULT_MANIFEST,
    compute_manifest_hash,
    load_manifest,
    load_manifest_scenarios,
    resolve_scenarios_root,
)
from app.evaluation.db_isolation import eval_db_session
from app.evaluation.errors import EXIT_FAIL_HARNESS, EXIT_FAIL_SAFETY
from app.evaluation.reporting import HARNESS_VERSION, new_run_id, render_terminal, write_json_report
from app.evaluation.runner import EvalHarnessRunner

DEFAULT_BASELINE = (
    Path(__file__).resolve().parents[1] / "tests" / "evaluation" / "baselines" / "k2e-baseline-v1.json"
)


def _write_baseline(result, manifest_hash: str, manifest, path: Path) -> None:
    if result.exit_code != 0:
        print("Refusing baseline write: harness run did not pass", file=sys.stderr)
        raise SystemExit(EXIT_FAIL_HARNESS)
    if result.summary.get("real_external_calls", 0) != 0:
        print("Refusing baseline write: real_external_calls must be 0", file=sys.stderr)
        raise SystemExit(EXIT_FAIL_SAFETY)
    if result.summary["passed"] != result.summary["total"]:
        print("Refusing baseline write: not all scenarios passed", file=sys.stderr)
        raise SystemExit(EXIT_FAIL_HARNESS)

    metric_totals: dict[str, list[float]] = {}
    scenario_metric_scores: dict[str, dict[str, float]] = {}
    for sc in result.scenarios:
        scenario_metric_scores[sc.scenario_id] = dict(sc.normalized_metrics)
        for key, score in sc.normalized_metrics.items():
            metric_totals.setdefault(key, []).append(score)

    payload = {
        "baseline_id": manifest.baseline_id,
        "harness_version": HARNESS_VERSION,
        "dataset_version": manifest.dataset_version,
        "schema_version": manifest.schema_version,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "manifest_hash": manifest_hash,
        "scenario_status": {sc.scenario_id: sc.status for sc in result.scenarios},
        "metric_scores": {
            key: round(sum(values) / len(values), 4) for key, values in metric_totals.items()
        },
        "scenario_metric_scores": scenario_metric_scores,
        "telemetry_summary": {"real_external_calls": 0},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote baseline: {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kapitel 2E evaluation harness")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--scenario-id")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--fail-on-regression", action="store_true")
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args(argv)

    manifest_path = args.manifest.resolve()
    hash_info = compute_manifest_hash(manifest_path)
    manifest_hash = hash_info["manifest_hash"]

    manifest, root, items = load_manifest_scenarios(
        manifest_path,
        scenario_id=args.scenario_id,
        smoke_only=args.smoke,
    )
    if not items:
        print("No scenarios matched", file=sys.stderr)
        return EXIT_FAIL_HARNESS

    run_mode = "single" if args.scenario_id else ("smoke" if args.smoke else "full")

    coverage = validate_coverage(
        manifest,
        root,
        loaded_scenarios={scenario.scenario_id: scenario for _, scenario in items},
        run_mode=run_mode,
    )
    if not coverage.passed:
        print("Coverage gate FAILED:", file=sys.stderr)
        for error in coverage.errors:
            print(f"  - {error}", file=sys.stderr)
        return EXIT_FAIL_HARNESS

    baseline = None
    baseline_path = args.baseline
    if baseline_path.exists() and not args.write_baseline:
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))

    run_id = new_run_id()
    runner = EvalHarnessRunner(
        run_id=run_id,
        baseline=baseline,
        fail_on_regression=args.fail_on_regression,
    )

    results = []
    with eval_db_session() as db:
        for _path, scenario in items:
            result = runner.run_scenario(db, scenario)
            results.append(result)
            if not args.quiet:
                print(f"{result.scenario_id}: {result.status}")
            if result.exit_code != 0 and args.fail_fast:
                break

    aggregate = runner.aggregate(results)
    aggregate.baseline_id = (baseline or {}).get("baseline_id") or manifest.baseline_id
    aggregate.dataset_id = manifest.dataset_id
    aggregate.manifest_hash = manifest_hash

    if args.report:
        write_json_report(aggregate, args.report)
    if not args.quiet:
        print(render_terminal(aggregate))
        print(f"manifest_hash={manifest_hash}")

    if args.write_baseline:
        _write_baseline(aggregate, manifest_hash, manifest, baseline_path)

    return aggregate.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
