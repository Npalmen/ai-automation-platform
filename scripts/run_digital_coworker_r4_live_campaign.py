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
from app.evaluation.profile_testbot.qualification.coworker_r4_live_backend import (  # noqa: E402
    build_r4_live_executor,
    describe_r4_live_backend_wiring,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (  # noqa: E402
    R4_LOCKED_CANDIDATE_RUNTIME_SHA,
    R4_PROFILE_ID,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="R4 live coworker-quality campaign (dry-run default; no Gmail writes)"
    )
    parser.add_argument("--candidate-runtime-sha", default=R4_LOCKED_CANDIDATE_RUNTIME_SHA)
    parser.add_argument("--expected-executor-sha", default="")
    parser.add_argument("--expected-runtime-sha", default="", help="Deprecated alias for executor SHA")
    parser.add_argument("--profile-id", default=R4_PROFILE_ID)
    parser.add_argument("--status-dir", default=str(ROOT / "storage" / "status"))
    parser.add_argument("--manifest", default="")
    parser.add_argument("--candidates-json", default="")
    parser.add_argument("--human-review-file", default="")
    parser.add_argument("--approval-file", default="")
    parser.add_argument("--campaign-id", default="")
    parser.add_argument(
        "--full-jit",
        action="store_true",
        help="Run full read-only live JIT (no Gmail writes)",
    )
    parser.add_argument(
        "--mailbox-baseline",
        action="store_true",
        help="Write read-only mailbox baseline artifact",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Live execute (requires signed approval + full JIT; fail-closed)",
    )
    args = parser.parse_args()

    executor_sha = (
        args.expected_executor_sha.strip()
        or args.expected_runtime_sha.strip()
    )
    if not executor_sha:
        print("ERROR: --expected-executor-sha is required", file=sys.stderr)
        return 1

    live_executor = None
    live_executor_factory = None
    if args.execute:
        missing = []
        if not args.approval_file:
            missing.append("--approval-file")
        if not args.candidates_json:
            missing.append("--candidates-json")
        if not args.human_review_file:
            missing.append("--human-review-file")
        if not args.manifest:
            missing.append("--manifest")
        if missing:
            print(f"ERROR: --execute requires {', '.join(missing)}", file=sys.stderr)
            return 1
        mode = "execute"
        # Factory is invoked by the runner only after approval + full JIT + baseline PASS.
        live_executor_factory = build_r4_live_executor
    elif args.full_jit:
        mode = "full_jit"
    elif args.mailbox_baseline:
        mode = "mailbox_baseline"
    else:
        mode = "dry_run"

    wiring = describe_r4_live_backend_wiring()
    result = run_r4_live_campaign(
        mode=mode,
        candidate_runtime_sha=args.candidate_runtime_sha.strip(),
        expected_executor_sha=executor_sha,
        profile_id=args.profile_id,
        status_dir=Path(args.status_dir),
        approval_path=Path(args.approval_file) if args.approval_file else None,
        human_review_path=Path(args.human_review_file) if args.human_review_file else None,
        candidates_path=Path(args.candidates_json) if args.candidates_json else None,
        manifest_path=Path(args.manifest) if args.manifest else None,
        campaign_id=args.campaign_id.strip() or None,
        live_executor=live_executor,
        live_executor_factory=live_executor_factory,
    )
    # Non-execute modes must never hold an active executor callback.
    if mode != "execute":
        result.setdefault("backend_wired", wiring["backend_wired"])
        result.setdefault("execute_backend_type", wiring["execute_backend_type"])
        result.setdefault("execute_callback_available", wiring["execute_callback_available"])
        result["live_executor_injected"] = False
    else:
        result["live_executor_injected"] = bool(
            result.get("live_executor_wired_after_gates")
        )
    for path in (result.get("report_paths") or {}).values():
        print(f"wrote {path}")
    print(f"mode={result.get('mode')}")
    print(f"candidate_runtime_sha={result.get('candidate_runtime_sha')}")
    print(f"executor_runtime_sha={result.get('executor_runtime_sha')}")
    print(f"backend_wired={result.get('backend_wired')}")
    print(f"execute_backend_type={result.get('execute_backend_type')}")
    print(f"execute_callback_available={result.get('execute_callback_available')}")
    print(f"overall_status={result.get('overall_status')}")
    if result.get("manual_execution_confirmation"):
        print(result["manual_execution_confirmation"])
    if result.get("overall_status") == "PASS":
        return 0
    print(result.get("stop_reason") or result.get("overall_status"), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
