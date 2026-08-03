#!/usr/bin/env python3
"""Operator runner for R3 digital coworker live canary (dry-run default)."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "storage" / "status"
sys.path.insert(0, str(ROOT))

from app.evaluation.profile_testbot.qualification.coworker_r3_execution import (  # noqa: E402
    PROFILE_ID,
    run_r3_live_canary,
    write_execution_reports,
)


def _load_live_eval_env(*, runtime_sha: str) -> None:
    try:
        from dotenv import dotenv_values
    except ImportError:
        dotenv_values = None  # type: ignore[assignment,misc]

    for path in (ROOT / ".env", ROOT / ".env.live-eval.local"):
        if not path.is_file():
            continue
        if dotenv_values is not None:
            for key, value in dotenv_values(path).items():
                if value is not None and str(value).strip():
                    os.environ[key] = str(value).strip()
        else:
            for line in path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

    os.environ["ENV"] = "test"
    os.environ["BUILD_GIT_SHA"] = runtime_sha
    os.environ["BUILD_COMMIT_SHA"] = runtime_sha
    os.environ["GIT_COMMIT"] = runtime_sha
    os.environ["LIVE_EVAL_ALLOWED"] = "yes"
    os.environ["LIVE_GMAIL_EVAL_ALLOWED"] = "yes"
    os.environ["LIVE_LLM_EVAL_ALLOWED"] = "yes"
    os.environ["FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED"] = "yes"
    os.environ["PROFILE_TESTBOT_LIVE_SEMI_AUTO_APPROVED"] = "yes"
    os.environ["PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED"] = "yes"
    os.environ["PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED_SHA"] = runtime_sha
    os.environ["PROFILE_TESTBOT_LIVE_QUALITY_APPROVED"] = "yes"
    os.environ["PROFILE_TESTBOT_LIVE_QUALITY_RUNNER_APPROVED"] = "yes"
    os.environ["PROFILE_TESTBOT_LIVE_QUALITY_RUNNER_APPROVED_SHA"] = runtime_sha
    os.environ["R3_FROZEN_APPROVAL_BIND_ALLOWED"] = "yes"
    os.environ.pop("PROFILE_TESTBOT_OFFLINE_MAILBOX_CONTRACT", None)

    client_id = os.environ.get("LIVE_EVAL_RECIPIENT_GMAIL_CLIENT_ID", "").strip()
    client_secret = os.environ.get("LIVE_EVAL_RECIPIENT_GMAIL_CLIENT_SECRET", "").strip()
    if client_id:
        os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", client_id)
    if client_secret:
        os.environ.setdefault("GOOGLE_OAUTH_CLIENT_SECRET", client_secret)

    from app.core.settings import get_settings
    from app.evaluation.live.config import get_live_eval_config

    get_settings.cache_clear()
    get_live_eval_config.cache_clear()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="R3 digital coworker live canary operator runner (dry-run default)"
    )
    parser.add_argument(
        "--manifest",
        required=True,
        help="Path to locked R3 canary manifest JSON",
    )
    parser.add_argument(
        "--approval-file",
        required=True,
        help="Path to manual send approval artifact JSON",
    )
    parser.add_argument(
        "--expected-runtime-sha",
        required=True,
        help="Full merge SHA for API, worker and runner",
    )
    parser.add_argument(
        "--campaign-id",
        default="",
        help="Optional fixed campaign UUID",
    )
    parser.add_argument(
        "--status-dir",
        default=str(STATUS),
        help="Directory for execution reports (default: storage/status)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute live canary (default: dry-run only, no external writes)",
    )
    args = parser.parse_args()

    runtime_sha = args.expected_runtime_sha.strip()
    _load_live_eval_env(runtime_sha=runtime_sha)
    mode = "execute" if args.execute else "dry_run"

    result = run_r3_live_canary(
        mode=mode,
        manifest_path=Path(args.manifest),
        approval_path=Path(args.approval_file),
        expected_runtime_sha=runtime_sha,
        repo_root=ROOT,
        campaign_id=args.campaign_id or None,
    )
    paths = write_execution_reports(result=result, status_dir=Path(args.status_dir))
    for path in paths.values():
        print(f"wrote {path}")

    readiness = result.readiness or {}
    if result.mode == "dry_run":
        if readiness.get("r3_canary_ready_for_execution"):
            print("R3 dry-run PASS — r3_canary_ready_for_execution=true (no Gmail sent)")
            if readiness.get("manual_execution_confirmation"):
                print(readiness["manual_execution_confirmation"])
            return 0
        print("R3 dry-run BLOCKED", file=sys.stderr)
        print(result.stop_reason or readiness.get("execution_blockers"), file=sys.stderr)
        return 1

    if result.overall_status == "PASS":
        print(
            "R3 LIVE CANARY COMPLETE — 8/8 sends och 7/7 no-send verifierade; "
            "R4 kräver separat beslut"
        )
        return 0
    if result.human_render_rereview_required:
        print(
            "HUMAN RENDER RE-REVIEW REQUIRED — Granska ändrade R3-texter före Gmail-godkännande",
            file=sys.stderr,
        )
        return 2
    print("R3 LIVE CANARY STOPPED — manuell reconciliation krävs innan nytt försök", file=sys.stderr)
    print(result.stop_reason or result.overall_status, file=sys.stderr)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
