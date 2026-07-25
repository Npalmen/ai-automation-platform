"""Full-system testbot campaign CLI (dry-run by default; no Gmail send without --confirm-external)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluation.live.campaign.generator import build_campaign_send_payload
from app.evaluation.live.campaign.gates import (
    campaign_enabled,
    validate_campaign_budget_config,
    validate_no_production_resources,
)
from app.evaluation.live.campaign.modes import CAMPAIGN_TYPE_DEFAULT_MODE
from app.evaluation.live.campaign.readiness import build_full_system_testbot_readiness
from app.evaluation.live.campaign.registry import list_campaign_scenarios
from app.evaluation.live.campaign.runner import run_observe_campaign
from app.evaluation.live.config import get_live_eval_config
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.registry import new_evaluation_run_id


def _list_scenarios(campaign_type: str | None) -> int:
    scenarios = list_campaign_scenarios(campaign_type=campaign_type)
    for scenario in scenarios:
        print(
            f"{scenario.scenario_id}\t{scenario.mode}\t{scenario.campaign_type}\t"
            f"{scenario.job_type}\t{scenario.content_hash[:12]}"
        )
    print(f"total: {len(scenarios)}")
    return 0


def _dry_run_campaign(campaign_type: str, tenant_id: str) -> int:
    config = get_live_eval_config()
    issues = validate_campaign_budget_config(campaign_type=campaign_type, config=config)
    if issues:
        print("budget/config issues:")
        for issue in issues:
            print(f"  - {issue}")
        return 1

    scenarios = list_campaign_scenarios(campaign_type=campaign_type)
    print(f"DRY-RUN campaign_type={campaign_type!r} mode={CAMPAIGN_TYPE_DEFAULT_MODE.get(campaign_type)!r}")
    print(f"tenant={tenant_id} scenarios={len(scenarios)}")
    for scenario in scenarios:
        run_id = new_evaluation_run_id()
        payload = build_campaign_send_payload(scenario=scenario, evaluation_run_id=run_id)
        print(f"\n--- {scenario.scenario_id} ---")
        print(f"subject: {payload['subject']}")
        print(f"sender: {payload['sender_name']} <{payload['sender_email']}>")
        preview = payload["body"][:120].encode("ascii", errors="replace").decode("ascii")
        print(f"body preview: {preview}...")
    print("\nNo Gmail send performed (dry-run).")
    return 0


def _validate_campaign(campaign_type: str, tenant_id: str, app_base_url: str) -> int:
    report = build_full_system_testbot_readiness(
        campaign_type=campaign_type,
        tenant_id=tenant_id,
        app_base_url=app_base_url,
    )
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0 if report.ready else 1


def _run_campaign(
    campaign_type: str,
    tenant_id: str,
    app_base_url: str,
    confirm_external: bool,
) -> int:
    if not confirm_external:
        print("ERROR: live campaign requires --confirm-external")
        return 2

    if not campaign_enabled():
        raise SystemExit("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED=yes required")

    base_url = (app_base_url or os.environ.get("LIVE_EVAL_APP_BASE_URL") or "").rstrip("/")
    admin_key = os.environ.get("ADMIN_API_KEY", "").strip()
    if not base_url or not admin_key:
        raise SystemExit("LIVE_EVAL_APP_BASE_URL and ADMIN_API_KEY are required")

    prod_issues = validate_no_production_resources(
        app_base_url=base_url,
        tenant_id=tenant_id,
    )
    if prod_issues:
        for issue in prod_issues:
            print(f"BLOCKED: {issue}")
        return 2

    report_path = Path("storage/status/full_system_testbot_report.json")
    result = run_observe_campaign(
        campaign_type=campaign_type,
        tenant_id=tenant_id,
        base_url=base_url,
        admin_api_key=admin_key,
        report_path=report_path,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))

    if result.safety_violations:
        print("SAFETY VIOLATIONS:", result.safety_violations, file=sys.stderr)
        return 2

    return 0 if result.overall_status == "passed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Full-system testbot campaign runner")
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list-scenarios", help="List registered campaign scenarios")
    list_parser.add_argument("--campaign-type", default=None)

    validate_parser = sub.add_parser("validate", help="Run offline readiness validation")
    validate_parser.add_argument("--campaign-type", default="transport-smoke")

    dry_parser = sub.add_parser("dry-run", help="Preview synthetic emails without sending")
    dry_parser.add_argument("--campaign-type", default="transport-smoke")

    run_parser = sub.add_parser("run", help="Run campaign (requires --confirm-external)")
    run_parser.add_argument("--campaign-type", default="transport-smoke")
    run_parser.add_argument("--confirm-external", action="store_true")

    parser.add_argument("--tenant-id", default="TENANT_LIVE_EVAL")
    parser.add_argument("--app-base-url", default="")

    args = parser.parse_args()

    if args.command == "list-scenarios":
        return _list_scenarios(args.campaign_type)
    if args.command == "validate":
        return _validate_campaign(
            getattr(args, "campaign_type", "transport-smoke"),
            args.tenant_id,
            args.app_base_url,
        )
    if args.command == "dry-run":
        return _dry_run_campaign(args.campaign_type, args.tenant_id)
    if args.command == "run":
        return _run_campaign(
            args.campaign_type,
            args.tenant_id,
            args.app_base_url,
            args.confirm_external,
        )
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LiveEvalSafetyError as exc:
        print(f"SAFETY: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
