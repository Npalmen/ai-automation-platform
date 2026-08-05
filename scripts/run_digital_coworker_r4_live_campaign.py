#!/usr/bin/env python3
"""Operator runner for R4 digital coworker live quality campaign (dry-run default)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.evaluation.profile_testbot.qualification.coworker_r4_execution import (  # noqa: E402
    run_r4_live_campaign,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (  # noqa: E402
    R4_PROFILE_ID,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="R4 live coworker-quality campaign (dry-run default; no Gmail writes)"
    )
    parser.add_argument("--expected-runtime-sha", required=True)
    parser.add_argument("--profile-id", default=R4_PROFILE_ID)
    parser.add_argument("--status-dir", default=str(ROOT / "storage" / "status"))
    parser.add_argument("--approval-file", default="")
    parser.add_argument("--human-review-file", default="")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Live execute (fail-closed until separate manual confirmation)",
    )
    args = parser.parse_args()
    mode = "execute" if args.execute else "dry_run"
    result = run_r4_live_campaign(
        mode=mode,
        expected_runtime_sha=args.expected_runtime_sha.strip(),
        profile_id=args.profile_id,
        status_dir=Path(args.status_dir),
        approval_path=Path(args.approval_file) if args.approval_file else None,
        human_review_path=Path(args.human_review_file) if args.human_review_file else None,
    )
    for path in (result.get("report_paths") or {}).values():
        print(f"wrote {path}")
    if result.get("manual_execution_confirmation"):
        print(result["manual_execution_confirmation"])
    if result.get("overall_status") == "PASS":
        return 0
    print(result.get("stop_reason") or result.get("overall_status"), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
