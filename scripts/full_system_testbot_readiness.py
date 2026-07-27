"""Full-system testbot readiness CLI (offline, no Gmail send)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluation.live.campaign.readiness import build_full_system_testbot_readiness


def main() -> int:
    parser = argparse.ArgumentParser(description="Full-system testbot readiness (offline)")
    parser.add_argument(
        "--campaign-type",
        default="transport-smoke",
        help="Campaign type to validate (default: transport-smoke)",
    )
    parser.add_argument(
        "--tenant-id",
        default="TENANT_LIVE_EVAL",
        help="Test tenant ID (default: TENANT_LIVE_EVAL)",
    )
    parser.add_argument(
        "--app-base-url",
        default="",
        help="App base URL for production-resource check",
    )
    parser.add_argument(
        "--server-sha",
        default="",
        help="Deployed server SHA (optional)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON report to stdout",
    )
    parser.add_argument(
        "--scenario-ids",
        default="",
        help="Comma-separated campaign scenario ids for selected-scenario budget",
    )
    args = parser.parse_args()

    selected_scenario_ids = tuple(
        item.strip()
        for item in str(getattr(args, "scenario_ids", "") or "").split(",")
        if item.strip()
    ) or None

    report = build_full_system_testbot_readiness(
        campaign_type=args.campaign_type,
        tenant_id=args.tenant_id,
        app_base_url=args.app_base_url,
        server_sha=args.server_sha or None,
        selected_scenario_ids=selected_scenario_ids,
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"ready: {report.ready}")
        print(f"origin/main SHA: {report.origin_main_sha}")
        if report.server_sha:
            print(f"server SHA: {report.server_sha}")
        print(f"manifest: {report.campaign_manifest_version}")
        print(f"scenarios ({args.campaign_type}): {report.scenario_count}")
        if report.issues:
            print("issues:")
            for issue in report.issues:
                print(f"  - {issue}")
        if report.warnings:
            print("warnings:")
            for warning in report.warnings:
                print(f"  - {warning}")

    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())
