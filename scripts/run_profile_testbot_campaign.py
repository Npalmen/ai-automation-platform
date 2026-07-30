#!/usr/bin/env python3
"""Profile-driven live testbot campaign CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluation.live.registry import new_evaluation_run_id
from app.evaluation.profile_testbot.campaign.hermetic_runner import run_hermetic_profile_campaign
from app.evaluation.profile_testbot.campaign.live_runners import (
    materialize_campaign_scenarios,
    plan_automatic_canary_campaign,
    plan_automatic_core_campaign,
    plan_semi_auto_live_campaign,
)
from app.evaluation.profile_testbot.campaign.readiness import (
    build_profile_testbot_readiness,
    require_live_semi_auto_approval,
    validate_profile_testbot_tenant,
)
from app.evaluation.profile_testbot.campaign.report import write_profile_testbot_report
from app.evaluation.profile_testbot.constants import (
    OPERATOR_STOP_AUTOMATIC,
    OPERATOR_STOP_SEMI_AUTO,
)


def _emit_stop(message: str) -> None:
    sys.stdout.buffer.write((message + "\n").encode("utf-8"))


def _run_hermetic(args: argparse.Namespace) -> int:
    result = run_hermetic_profile_campaign(profile_id=args.profile_id, seed=args.seed)
    run_id = new_evaluation_run_id()
    payload = result.to_dict()
    payload["profile_id"] = args.profile_id
    write_profile_testbot_report(phase="hermetic", run_id=run_id, payload=payload)
    print(result.overall_status)
    print(json.dumps(payload, indent=2))
    return 0 if result.overall_status == "PASS" else 1


def _run_semi_auto(args: argparse.Namespace) -> int:
    plan = plan_semi_auto_live_campaign(profile_id=args.profile_id, seed=args.seed)
    if plan.blocked_reason:
        _emit_stop(plan.blocked_reason)
        return 2
    payload = plan.to_dict()
    payload["campaign_scenarios"] = len(materialize_campaign_scenarios(plan))
    run_id = new_evaluation_run_id()
    write_profile_testbot_report(phase="semi-auto-live", run_id=run_id, payload=payload)
    print("READY_FOR_LIVE_SEMI_AUTO")
    return 0


def _run_automatic(args: argparse.Namespace) -> int:
    canary = plan_automatic_canary_campaign(profile_id=args.profile_id, seed=args.seed)
    if canary.blocked_reason:
        _emit_stop(canary.blocked_reason)
        return 2
    core = plan_automatic_core_campaign(profile_id=args.profile_id, seed=args.seed)
    payload = {
        "canary": canary.to_dict(),
        "core": core.to_dict(),
    }
    run_id = new_evaluation_run_id()
    write_profile_testbot_report(phase="automatic-live", run_id=run_id, payload=payload)
    print("READY_FOR_AUTOMATIC")
    return 0


def _write_readiness_report(report: dict) -> Path:
    run_id = new_evaluation_run_id()
    path = Path("storage/status") / f"profile-testbot-semi-auto-live-readiness-{run_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Profile testbot semi-auto live readiness",
        "",
        f"- runtime_sha: `{report.get('runtime_sha')}`",
        f"- profile_id: `{report.get('profile_id')}`",
        f"- profile_snapshot_hash: `{report.get('profile_snapshot_hash')}`",
        f"- eval_tenant: `{report.get('eval_tenant')}`",
        f"- ready_for_live_semi_auto: **{report.get('ready_for_live_semi_auto')}**",
        f"- single_active_consumer: **{report.get('single_active_consumer')}**",
        "",
        "## Mailbox hashes (redacted)",
        "",
        f"- sender_mailbox_hash: `{report.get('sender_mailbox_hash')}`",
        f"- recipient_mailbox_hash: `{report.get('recipient_mailbox_hash')}`",
        f"- sender_provider_verified: **{report.get('sender_provider_verified')}**",
        f"- recipient_deliverability_verified: **{report.get('recipient_deliverability_verified')}**",
        "",
        "## Safety assertions",
        "",
    ]
    assertions = report.get("safety_assertions") or []
    if assertions:
        lines.extend(f"- {item}" for item in assertions)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Semi-auto manifest",
            "",
            "```json",
            json.dumps(report.get("semi_auto_manifest", {}), indent=2, ensure_ascii=False),
            "```",
            "",
            "## Blocking failures",
            "",
        ]
    )
    blockers = report.get("blocking_failures") or []
    if blockers:
        lines.extend(f"- {item}" for item in blockers)
    else:
        lines.append("- none")
    if report.get("operator_stop"):
        lines.extend(["", "## Operator stop", "", report["operator_stop"]])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Profile-driven live testbot campaigns")
    parser.add_argument("--profile-id", default="pilot-service-company-v1")
    parser.add_argument("--seed", type=int, default=0)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("readiness", help="Build profile testbot readiness report")
    sub.add_parser("hermetic", help="Run 120-scenario hermetic profile campaign")
    semi = sub.add_parser("semi-auto-live", help="Plan live semi-auto campaign (requires approval)")
    semi.add_argument("--confirm-operator", action="store_true")
    auto = sub.add_parser("automatic-live", help="Plan automatic campaigns (requires approval)")
    auto.add_argument("--confirm-operator", action="store_true")

    args = parser.parse_args(argv)
    if args.command == "readiness":
        report = build_profile_testbot_readiness(profile_id=args.profile_id)
        report_path = _write_readiness_report(report)
        sys.stdout.buffer.write(json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8"))
        sys.stdout.buffer.write(f"\nreport={report_path}\n".encode("utf-8"))
        return 0 if report.get("ready_for_live_semi_auto") else 1
    if args.command == "hermetic":
        return _run_hermetic(args)
    if args.command == "semi-auto-live":
        if not args.confirm_operator:
            _emit_stop(OPERATOR_STOP_SEMI_AUTO)
            return 2
        return _run_semi_auto(args)
    if args.command == "automatic-live":
        if not args.confirm_operator:
            _emit_stop(OPERATOR_STOP_AUTOMATIC)
            return 2
        return _run_automatic(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
