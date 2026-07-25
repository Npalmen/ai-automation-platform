"""Run Kapitel 2F.4C offline replay and optional 2F.4D final closure."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluation.live.closure import (
    build_closure_context,
    finalize_offline_replay_result,
    parse_required_check,
)
from app.evaluation.live.final_evidence import write_json_atomic
from app.evaluation.live.replay_verifier import run_offline_replay


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build evidence manifest, offline replay report, and final report."
    )
    parser.add_argument("--evidence-sources", required=True, type=Path)
    parser.add_argument("--replay-sources", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--baseline-git-sha", required=True)
    parser.add_argument(
        "--generated-at",
        default=None,
        help="Optional ISO8601 timestamp (does not affect replay payload hash)",
    )
    parser.add_argument(
        "--finalize-closure",
        action="store_true",
        help="Apply final closure context and require overall_status=passed",
    )
    parser.add_argument("--ci-event", default=None)
    parser.add_argument("--ci-branch", default=None)
    parser.add_argument("--ci-run-id", default=None)
    parser.add_argument("--ci-head-sha", default=None)
    parser.add_argument(
        "--required-check",
        action="append",
        default=[],
        help="Required upstream check in name=status form (repeatable)",
    )
    parser.add_argument(
        "--documentation-root",
        type=Path,
        default=ROOT,
        help="Repository root used to verify documentation closure",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if not args.evidence_sources.is_file():
        print(f"evidence sources not found: {args.evidence_sources}", file=sys.stderr)
        return 2
    if not args.replay_sources.is_file():
        print(f"replay sources not found: {args.replay_sources}", file=sys.stderr)
        return 2

    generated_at = None
    if args.generated_at:
        generated_at = datetime.fromisoformat(
            args.generated_at.replace("Z", "+00:00")
        ).astimezone(timezone.utc)

    try:
        result = run_offline_replay(
            evidence_sources_path=args.evidence_sources,
            replay_sources_path=args.replay_sources,
            baseline_git_sha=args.baseline_git_sha,
            generated_at=generated_at,
        )
        if args.finalize_closure:
            if not args.ci_event or not args.ci_branch or not args.ci_run_id:
                raise ValueError(
                    "finalize closure requires --ci-event, --ci-branch, and --ci-run-id"
                )
            ci_head_sha = args.ci_head_sha or args.baseline_git_sha
            required_checks = dict(parse_required_check(item) for item in args.required_check)
            context = build_closure_context(
                baseline_git_sha=args.baseline_git_sha,
                ci_event=args.ci_event,
                ci_branch=args.ci_branch,
                ci_run_id=args.ci_run_id,
                ci_head_sha=ci_head_sha,
                required_checks=required_checks,
                documentation_root=args.documentation_root,
            )
            result = finalize_offline_replay_result(result, context)
    except (ValueError, OSError) as exc:
        print(f"offline replay failed: {exc}", file=sys.stderr)
        return 1

    write_json_atomic(args.output_dir / "2f_evidence_manifest.json", result.manifest)
    write_json_atomic(args.output_dir / "2f_replay_report.json", result.replay_report)
    write_json_atomic(args.output_dir / "2f_final_report.json", result.final_report)

    if result.replay_report.get("overall_status") != "passed":
        print("replay overall_status is not passed", file=sys.stderr)
        return 1

    if args.finalize_closure:
        if result.final_report.get("overall_status") != "passed":
            print("final report overall_status is not passed", file=sys.stderr)
            return 1
    elif result.final_report.get("overall_status") != "pending_closure":
        print("candidate final report overall_status is not pending_closure", file=sys.stderr)
        return 1

    print(result.replay_payload_hash)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
