"""Restore TENANT_LIVE_EVAL automation config after automatic Gmail core."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.evaluation.live.campaign.tenant_automation_lifecycle import (
    DEFAULT_SNAPSHOT_PATH,
    run_lifecycle_cleanup,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restore live-eval tenant automation config (core)")
    parser.add_argument("--tenant-id", default="TENANT_LIVE_EVAL")
    parser.add_argument(
        "--snapshot",
        default=os.environ.get(
            "LIVE_EVAL_AUTOMATIC_CORE_SNAPSHOT_PATH",
            os.environ.get(
                "LIVE_EVAL_AUTOMATIC_CANARY_SNAPSHOT_PATH",
                str(DEFAULT_SNAPSHOT_PATH),
            ),
        ),
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)

    if not args.apply:
        print(
            json.dumps(
                {
                    "mode": "dry_run",
                    "tenant_id": args.tenant_id,
                    "snapshot": args.snapshot,
                },
                indent=2,
            )
        )
        return 0

    report = run_lifecycle_cleanup(args.snapshot, tenant_id=args.tenant_id)
    payload = report.to_dict()
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("restoration_status") == "restored" else 1


if __name__ == "__main__":
    raise SystemExit(main())
