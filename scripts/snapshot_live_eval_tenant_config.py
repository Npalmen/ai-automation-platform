"""Snapshot TENANT_LIVE_EVAL auto_actions before automatic Gmail canary."""

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
    snapshot_tenant_config,
    verify_automation_not_broadly_enabled,
    write_snapshot_file,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Snapshot live-eval tenant automation config")
    parser.add_argument("--tenant-id", default="TENANT_LIVE_EVAL")
    parser.add_argument(
        "--output",
        default=os.environ.get(
            "LIVE_EVAL_AUTOMATIC_CANARY_SNAPSHOT_PATH",
            str(DEFAULT_SNAPSHOT_PATH),
        ),
    )
    args = parser.parse_args(argv)

    snapshot = snapshot_tenant_config(args.tenant_id)
    issues = verify_automation_not_broadly_enabled(snapshot.auto_actions)
    if issues:
        print(json.dumps({"ready": False, "issues": issues}, indent=2), file=sys.stderr)
        return 1

    path = write_snapshot_file(snapshot, args.output)
    print(
        json.dumps(
            {
                "tenant_id": snapshot.tenant_id,
                "pre_run_config_hash": snapshot.config_hash,
                "snapshot_path": str(path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
