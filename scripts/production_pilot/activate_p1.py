#!/usr/bin/env python3
"""Activate production pilot P1 observe-only configuration (config only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.production_pilot.p1_activation import build_p1_tenant_record, validate_p1_tenant_record
from app.production_pilot.p1_readiness import build_p1_readiness


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Activate production pilot P1 observe-only config")
    parser.add_argument("--backup-reference", default="backup-p1-activation")
    parser.add_argument("--mailbox", default="")
    parser.add_argument(
        "--output",
        default="storage/status/production-pilot/p1-activation.json",
    )
    args = parser.parse_args(argv)
    readiness = build_p1_readiness(backup_reference=args.backup_reference)
    if readiness.get("blockers"):
        print("FAIL", readiness["blockers"])
        return 1
    record = build_p1_tenant_record(mailbox=args.mailbox)
    failures = validate_p1_tenant_record(record)
    if failures:
        print("FAIL", failures)
        return 1
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"readiness": readiness, "tenant": record}, indent=2), encoding="utf-8")
    print("P1", record["config_hash"][:16])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
