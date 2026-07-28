"""Pause all automatic actions for TENANT_LIVE_EVAL after canary."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluation.live.campaign.tenant_automation_lifecycle import pause_automation


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pause live-eval automatic Gmail canary automation")
    parser.add_argument("--tenant-id", default="TENANT_LIVE_EVAL")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    if not args.apply:
        print(json.dumps({"mode": "dry_run", "tenant_id": args.tenant_id}, indent=2))
        return 0

    paused = pause_automation(args.tenant_id)
    print(
        json.dumps(
            {
                "mode": "apply",
                "tenant_id": args.tenant_id,
                "pause_status": "paused",
                "post_pause_config_hash": paused.config_hash,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
