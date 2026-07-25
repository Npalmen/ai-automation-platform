#!/usr/bin/env python3
"""Finalize Kapitel 2G evidence package on main."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluation.batch.reports import (
    build_batch_report,
    build_coverage_report,
    build_failure_corpus,
    build_generation_manifest_for_records,
)
from app.evaluation.batch.runner import run_batch
from app.evaluation.batch.sampler import build_main_batch_for_eval, build_pr_batch_records
from app.evaluation.closure_2g import (
    build_closure_context,
    build_final_report,
    parse_required_check,
    verify_documentation_closure,
)
from app.evaluation.errors import EXIT_FAIL_HARNESS, EXIT_PASS


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and finalize 2G evidence package")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--baseline-git-sha", required=True)
    parser.add_argument("--finalize-closure", action="store_true")
    parser.add_argument("--ci-event", default=None)
    parser.add_argument("--ci-branch", default=None)
    parser.add_argument("--ci-run-id", default=None)
    parser.add_argument("--ci-head-sha", default=None)
    parser.add_argument("--required-check", action="append", default=[])
    parser.add_argument("--documentation-root", type=Path, default=ROOT)
    args = parser.parse_args(argv)

    pr_records = build_pr_batch_records().records
    pr_batch = run_batch(pr_records, mode="pr", verify_determinism=True)
    pr_report = build_batch_report(pr_batch, baseline_git_sha=args.baseline_git_sha)
    pr_status = pr_report["overall_status"]

    main_records = build_main_batch_for_eval()
    main_batch = run_batch(main_records, mode="main", verify_determinism=True)
    generation_manifest = build_generation_manifest_for_records(
        main_records, baseline_git_sha=args.baseline_git_sha
    )
    batch_report = build_batch_report(
        main_batch,
        baseline_git_sha=args.baseline_git_sha,
        generation_manifest=generation_manifest,
    )
    failures = build_failure_corpus(main_batch)
    coverage = build_coverage_report(main_batch)

    context = None
    documentation_status = None
    if args.finalize_closure:
        if not args.ci_event or not args.ci_branch or not args.ci_run_id:
            print("finalize closure requires ci context", file=sys.stderr)
            return EXIT_FAIL_HARNESS
        required_checks = dict(parse_required_check(item) for item in args.required_check)
        context = build_closure_context(
            baseline_git_sha=args.baseline_git_sha,
            ci_event=args.ci_event,
            ci_branch=args.ci_branch,
            ci_run_id=args.ci_run_id,
            ci_head_sha=args.ci_head_sha or args.baseline_git_sha,
            required_checks=required_checks,
            documentation_root=args.documentation_root,
        )
        documentation_status = verify_documentation_closure(args.documentation_root)

    final_report = build_final_report(
        batch_report=batch_report,
        generation_manifest=generation_manifest,
        failures=failures,
        coverage=coverage,
        context=context,
        documentation_status=documentation_status,
        pr_batch_status=pr_status,
    )

    if pr_status != "passed" or batch_report["overall_status"] != "passed":
        print("batch evaluation did not pass", file=sys.stderr)
        return EXIT_FAIL_HARNESS

    _write_json(args.output_dir / "2g_generation_manifest.json", generation_manifest)
    _write_json(args.output_dir / "2g_batch_report.json", batch_report)
    _write_json(args.output_dir / "2g_failures.json", failures)
    _write_json(args.output_dir / "2g_coverage_report.json", coverage)
    _write_json(args.output_dir / "2g_final_report.json", final_report)

    if args.finalize_closure and final_report["overall_status"] != "passed":
        print("final report overall_status is not passed", file=sys.stderr)
        return EXIT_FAIL_HARNESS

    print(batch_report["batch_payload_hash"])
    return EXIT_PASS


if __name__ == "__main__":
    raise SystemExit(main())
