#!/usr/bin/env python3
"""Operator-only internal pilot live activation helper."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.internal_pilot.constants import (
    MAX_PILOT_BATCH_EMAILS,
    MIN_PILOT_FIRST_BATCH_EMAILS,
    PILOT_GMAIL_QUERY,
    PILOT_TENANT_ID,
)
from app.internal_pilot.gates import build_pilot_activation_snapshot
from app.internal_pilot.readiness import build_internal_pilot_readiness
from app.repositories.postgres.database import SessionLocal
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository


def _enable_live_settings(settings: dict) -> dict:
    updated = dict(settings or {})
    internal_pilot = dict(updated.get("internal_pilot") or {})
    internal_pilot["live_scan_enabled"] = True
    updated["internal_pilot"] = internal_pilot

    scheduler = dict(updated.get("scheduler") or {})
    scheduler["run_mode"] = "manual"
    updated["scheduler"] = scheduler

    automation = dict(updated.get("automation") or {})
    automation["demo_mode"] = False
    automation["automatic_gmail_replies"] = False
    updated["automation"] = automation

    operations = dict(updated.get("operations") or {})
    operations["paused"] = False
    updated["operations"] = operations
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Activate internal pilot live scan gate")
    parser.add_argument("--tenant-id", default=PILOT_TENANT_ID)
    parser.add_argument("--baseline-git-sha", default=None)
    parser.add_argument("--enable-live", action="store_true")
    parser.add_argument("--confirm-operator", action="store_true")
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        settings = TenantConfigRepository.get_settings(db, args.tenant_id)
        readiness = build_internal_pilot_readiness(
            tenant_id=args.tenant_id,
            settings=settings,
            baseline_git_sha=args.baseline_git_sha,
        )
        snapshot = build_pilot_activation_snapshot(
            tenant_id=args.tenant_id,
            settings=settings,
        )
        report = {
            "operator_action_required": not (args.enable_live and args.confirm_operator),
            "readiness": readiness,
            "activation_snapshot": snapshot,
            "pilot_tenant": args.tenant_id,
            "gmail_query": PILOT_GMAIL_QUERY,
            "max_batch_emails": MAX_PILOT_BATCH_EMAILS,
            "min_first_batch_emails": MIN_PILOT_FIRST_BATCH_EMAILS,
            "blocked_external_writes": True,
            "automatic_gmail_replies": False,
            "first_scan_command": "python scripts/ops/pilot_gmail_soak_first_scan.py 3",
            "pause_command": "python scripts/internal_pilot_pause.py --execute",
        }

        if args.enable_live:
            if not args.confirm_operator:
                print(
                    "Refusing --enable-live without --confirm-operator",
                    file=sys.stderr,
                )
                return 2
            if readiness["overall_status"] == "fail":
                print("Readiness FAIL — cannot enable live scan", file=sys.stderr)
                print(json.dumps(readiness, indent=2), file=sys.stderr)
                return 1
            target = _enable_live_settings(settings)
            TenantConfigRepository.update_settings(db, args.tenant_id, target)
            db.commit()
            report["live_scan_enabled"] = True

        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
