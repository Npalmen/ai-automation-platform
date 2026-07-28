"""Activate temporary lead=auto automation for automatic Gmail canary."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluation.live.campaign.tenant_automation_lifecycle import (
    activate_canary_automation,
    verify_automation_not_broadly_enabled,
    snapshot_tenant_config,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed automatic Gmail canary tenant automation")
    parser.add_argument("--tenant-id", default="TENANT_LIVE_EVAL")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    pre = snapshot_tenant_config(args.tenant_id)
    issues = verify_automation_not_broadly_enabled(pre.auto_actions)
    if not args.apply:
        print(
            json.dumps(
                {
                    "mode": "dry_run",
                    "tenant_id": args.tenant_id,
                    "pre_run_config_hash": pre.config_hash,
                    "issues": issues,
                    "would_apply": not issues,
                },
                indent=2,
            )
        )
        return 1 if issues else 0

    if issues:
        print(json.dumps({"mode": "apply", "issues": issues}, indent=2), file=sys.stderr)
        return 1

    active = activate_canary_automation(args.tenant_id)
    print(
        json.dumps(
            {
                "mode": "apply",
                "tenant_id": args.tenant_id,
                "pre_run_config_hash": pre.config_hash,
                "active_run_config_hash": active.config_hash,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
