#!/usr/bin/env python3
"""CLI for Kapitel 2G batch evaluation."""

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
from app.evaluation.batch.sampler import PR_BATCH_SIZE, build_main_batch_for_eval, build_pr_batch_records
from app.evaluation.errors import EXIT_FAIL_HARNESS, EXIT_PASS
from app.evaluation.mutations.batch import MAIN_BATCH_SIZE


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run 2G hermetic batch evaluation")
    parser.add_argument("--mode", choices=["pr", "main"], required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--baseline-git-sha", default=None)
    parser.add_argument("--scenario-id")
    parser.add_argument("--skip-determinism-check", action="store_true")
    args = parser.parse_args(argv)

    if args.mode == "pr":
        batch_records = build_pr_batch_records().records
        expected = PR_BATCH_SIZE
    else:
        batch_records = build_main_batch_for_eval()
        expected = MAIN_BATCH_SIZE

    if args.scenario_id:
        batch_records = [r for r in batch_records if r.scenario.scenario_id == args.scenario_id]
        if not batch_records:
            print(f"scenario not found: {args.scenario_id}", file=sys.stderr)
            return EXIT_FAIL_HARNESS

    if len(batch_records) != expected and not args.scenario_id:
        print(f"unexpected batch size {len(batch_records)} expected {expected}", file=sys.stderr)
        return EXIT_FAIL_HARNESS

    batch = run_batch(
        batch_records,
        mode=args.mode,
        verify_determinism=not args.skip_determinism_check,
    )
    generation_manifest = build_generation_manifest_for_records(
        batch_records, baseline_git_sha=args.baseline_git_sha
    )
    batch_report = build_batch_report(
        batch,
        baseline_git_sha=args.baseline_git_sha,
        generation_manifest=generation_manifest,
    )
    failures = build_failure_corpus(batch)
    coverage = build_coverage_report(batch)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "2g_generation_manifest.json").write_text(
        json.dumps(generation_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "2g_batch_report.json").write_text(
        json.dumps(batch_report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "2g_failures.json").write_text(
        json.dumps(failures, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "2g_coverage_report.json").write_text(
        json.dumps(coverage, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "mode": args.mode,
                "scenario_count": len(batch_records),
                "overall_status": batch_report["overall_status"],
                "batch_payload_hash": batch_report["batch_payload_hash"],
            }
        )
    )
    return EXIT_PASS if batch_report["overall_status"] == "passed" else EXIT_FAIL_HARNESS


if __name__ == "__main__":
    raise SystemExit(main())
