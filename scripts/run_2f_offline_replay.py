"""Run Kapitel 2F.4C offline replay smoke (no network, no database)."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluation.live.final_evidence import write_json_atomic
from app.evaluation.live.replay_verifier import run_offline_replay


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build evidence manifest, offline replay report, and updated final report."
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
    except (ValueError, OSError) as exc:
        print(f"offline replay failed: {exc}", file=sys.stderr)
        return 1

    write_json_atomic(args.output_dir / "2f_evidence_manifest.json", result.manifest)
    write_json_atomic(args.output_dir / "2f_replay_report.json", result.replay_report)
    write_json_atomic(args.output_dir / "2f_final_report.json", result.final_report)

    if result.replay_report.get("overall_status") != "passed":
        print("replay overall_status is not passed", file=sys.stderr)
        return 1

    print(result.replay_payload_hash)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
