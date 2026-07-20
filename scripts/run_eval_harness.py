#!/usr/bin/env python3
"""CLI for Kapitel 2D deterministic evaluation harness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.evaluation.db_isolation import eval_db_session
from app.evaluation.errors import EXIT_BASELINE_REGRESSION, EXIT_FAIL_HARNESS
from app.evaluation.loader import discover_scenarios
from app.evaluation.reporting import new_run_id, render_terminal, write_json_report
from app.evaluation.runner import EvalHarnessRunner

DEFAULT_SCENARIOS = Path(__file__).resolve().parents[1] / "tests" / "evaluation" / "scenarios"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kapitel 2D evaluation harness")
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--scenario-id")
    parser.add_argument("--category")
    parser.add_argument("--tag")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--fail-on-regression", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("-q", "--quiet", action="store_true")
    args = parser.parse_args(argv)

    tag = "smoke" if args.smoke else args.tag
    items = discover_scenarios(
        args.scenarios,
        scenario_id=args.scenario_id,
        category=args.category,
        tag=tag,
    )
    if not items:
        print("No scenarios matched", file=sys.stderr)
        return EXIT_FAIL_HARNESS

    baseline = None
    if args.baseline and args.baseline.exists():
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))

    run_id = new_run_id()
    runner = EvalHarnessRunner(
        run_id=run_id,
        baseline=baseline,
        fail_on_regression=args.fail_on_regression,
    )

    results = []
    with eval_db_session() as db:
        for path, scenario in items:
            result = runner.run_scenario(db, scenario)
            results.append(result)
            if not args.quiet:
                print(f"{result.scenario_id}: {result.status}")
            if result.exit_code != 0 and args.fail_fast:
                break

    aggregate = runner.aggregate(results)
    if args.report:
        write_json_report(aggregate, args.report)
    if not args.quiet:
        print(render_terminal(aggregate))
    return aggregate.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
