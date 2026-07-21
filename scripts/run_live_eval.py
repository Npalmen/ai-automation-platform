"""Kapitel 2F.1 live-eval CLI — validate-config and offline dry-run only."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluation.live.config import get_live_eval_config
from app.evaluation.live.constants import PYTEST_MARKER_EXPR, REPORT_SCHEMA_VERSION
from app.evaluation.live.journal import append_transition, load_transitions, write_report_atomic
from app.evaluation.live.readiness import run_offline_readiness_checks
from app.evaluation.live.registry import new_evaluation_run_id
from app.evaluation.live.schemas import LiveEvalReport
from app.evaluation.live.subject_parser import build_subject_with_token, parse_subject_token


def cmd_validate_config(args: argparse.Namespace) -> int:
    if args.gmail_readiness:
        if not args.confirm_read_only:
            print(
                json.dumps(
                    {
                        "ready": False,
                        "issues": ["--confirm-read-only is required for Gmail readiness"],
                    },
                    indent=2,
                )
            )
            return 1
        if not args.tenant_id:
            print(
                json.dumps(
                    {"ready": False, "issues": ["--tenant-id is required"]},
                    indent=2,
                )
            )
            return 1
        base = (args.app_base_url or os.environ.get("LIVE_EVAL_APP_BASE_URL") or "").rstrip("/")
        admin_key = os.environ.get("ADMIN_API_KEY", "").strip()
        if not base or not admin_key:
            print(
                json.dumps(
                    {
                        "ready": False,
                        "issues": [
                            "LIVE_EVAL_APP_BASE_URL and ADMIN_API_KEY required for Gmail readiness"
                        ],
                    },
                    indent=2,
                )
            )
            return 1
        import httpx

        response = httpx.post(
            f"{base}/admin/live-eval/gmail-readiness",
            headers={"X-Admin-API-Key": admin_key},
            json={"tenant_id": args.tenant_id},
            timeout=30.0,
        )
        payload = response.json()
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if response.status_code == 200 and payload.get("ready") else 1

    report = run_offline_readiness_checks()
    payload = {
        "ready": report.ready,
        "issues": report.issues,
        "checks": report.checks,
        "pytest_marker_expr": PYTEST_MARKER_EXPR,
        "mode": "offline",
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if report.ready else 1


def cmd_dry_run(args: argparse.Namespace) -> int:
    """Offline dry-run: subject parser + journal/report validation (no Gmail/LLM)."""
    config = get_live_eval_config()
    run_id = args.evaluation_run_id or new_evaluation_run_id()
    scenario_id = args.scenario_id or "S01_lead_laddbox_quality"
    attempt_id = args.attempt_id or 1
    subject = build_subject_with_token(
        evaluation_run_id=run_id,
        scenario_id=scenario_id,
        attempt_id=attempt_id,
        base_subject="Dry-run probe",
    )
    parsed = parse_subject_token(subject)
    if parsed is None:
        print("Subject parser failed", file=sys.stderr)
        return 1

    append_transition(
        run_id,
        {
            "state": "dry_run_started",
            "scenario_id": scenario_id,
            "attempt_id": attempt_id,
            "transport_mode": "offline",
        },
    )
    append_transition(
        run_id,
        {
            "state": "subject_parsed",
            "evaluation_run_id": parsed.evaluation_run_id,
            "scenario_id": parsed.scenario_id,
            "attempt_id": parsed.attempt_id,
        },
    )

    transitions = load_transitions(run_id)
    report = LiveEvalReport(
        evaluation_run_id=run_id,
        scenario_id=scenario_id,
        transport_mode="offline",
        ai_mode="fixture_ai",
        result="dry_run",
        state_transitions=transitions,
    )
    report_path = write_report_atomic(run_id, report)
    payload = {
        "evaluation_run_id": run_id,
        "subject": subject,
        "parsed": {
            "evaluation_run_id": parsed.evaluation_run_id,
            "scenario_id": parsed.scenario_id,
            "attempt_id": parsed.attempt_id,
        },
        "report_schema_version": REPORT_SCHEMA_VERSION,
        "report_path": str(report_path),
        "storage_root": config.storage_root,
        "env_fingerprint": config.env_fingerprint,
        "transition_count": len(transitions),
    }
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Live evaluation foundation CLI (2F.1)")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate-config", help="Verify gates and readiness")
    validate.add_argument("--offline", action="store_true", default=True)
    validate.add_argument("--gmail-readiness", action="store_true")
    validate.add_argument("--confirm-read-only", action="store_true")
    validate.add_argument("--tenant-id", default=None)
    validate.add_argument("--app-base-url", default=None)
    validate.set_defaults(func=cmd_validate_config)

    dry_run = sub.add_parser("dry-run", help="Offline journal/report dry-run")
    dry_run.add_argument("--evaluation-run-id", default=None)
    dry_run.add_argument("--scenario-id", default=None)
    dry_run.add_argument("--attempt-id", type=int, default=None)
    dry_run.set_defaults(func=cmd_dry_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
