"""Build Kapitel 2F.4B evidence manifest and final report (offline, no network)."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluation.live.final_evidence import write_final_evidence_outputs


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build 2F evidence manifest and final report from sanitized sources."
    )
    parser.add_argument(
        "--sources",
        required=True,
        type=Path,
        help="Sanitized evidence sources JSON (e.g. tests/fixtures/2f_evidence/evidence_sources_v1.json)",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="Output directory for 2f_evidence_manifest.json and 2f_final_report.json",
    )
    parser.add_argument(
        "--baseline-git-sha",
        required=True,
        help="Baseline Git SHA for closure evidence binding",
    )
    parser.add_argument(
        "--generated-at",
        default=None,
        help="Optional ISO8601 timestamp for output files (does not affect payload hash)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if not args.sources.is_file():
        print(f"evidence sources not found: {args.sources}", file=sys.stderr)
        return 2

    generated_at = None
    if args.generated_at:
        generated_at = datetime.fromisoformat(
            args.generated_at.replace("Z", "+00:00")
        ).astimezone(timezone.utc)

    try:
        result = write_final_evidence_outputs(
            sources_path=args.sources,
            output_dir=args.output_dir,
            baseline_git_sha=args.baseline_git_sha,
            generated_at=generated_at,
        )
    except (ValueError, OSError) as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        return 1

    print(result.evidence_payload_hash)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
