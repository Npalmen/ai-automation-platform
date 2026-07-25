#!/usr/bin/env python3
"""Pause / rollback internal pilot to safe state (no Gmail scan)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.internal_pilot.constants import PILOT_TENANT_ID
from app.repositories.postgres.database import SessionLocal
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository


def _pause_settings(settings: dict) -> dict:
    updated = dict(settings or {})
    internal_pilot = dict(updated.get("internal_pilot") or {})
    internal_pilot["live_scan_enabled"] = False
    updated["internal_pilot"] = internal_pilot

    scheduler = dict(updated.get("scheduler") or {})
    scheduler["run_mode"] = "paused"
    updated["scheduler"] = scheduler

    automation = dict(updated.get("automation") or {})
    automation["demo_mode"] = True
    automation["automatic_gmail_replies"] = False
    updated["automation"] = automation

    operations = dict(updated.get("operations") or {})
    operations["paused"] = True
    updated["operations"] = operations
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pause internal pilot tenant safely")
    parser.add_argument("--tenant-id", default=PILOT_TENANT_ID)
    parser.add_argument("--execute", action="store_true", help="Apply DB settings changes")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        current = TenantConfigRepository.get_settings(db, args.tenant_id)
        target = _pause_settings(current)
        result = {
            "tenant_id": args.tenant_id,
            "executed": args.execute,
            "before": {
                "live_scan_enabled": (current.get("internal_pilot") or {}).get("live_scan_enabled"),
                "scheduler_run_mode": (current.get("scheduler") or {}).get("run_mode"),
                "demo_mode": (current.get("automation") or {}).get("demo_mode"),
            },
            "after": {
                "live_scan_enabled": False,
                "scheduler_run_mode": "paused",
                "demo_mode": True,
                "operations_paused": True,
            },
        }
        if args.execute:
            TenantConfigRepository.update_settings(db, args.tenant_id, target)
            db.commit()
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
