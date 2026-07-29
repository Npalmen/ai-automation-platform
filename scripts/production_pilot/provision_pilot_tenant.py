#!/usr/bin/env python3
"""Emit production pilot P0 tenant baseline (config only, no DB writes)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.production_pilot.tenant_baseline import build_p0_tenant_record, validate_pilot_tenant_record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build production pilot tenant baseline")
    parser.add_argument("--pilot-owner", default="operator")
    parser.add_argument("--mailbox", default="")
    parser.add_argument(
        "--output",
        default="storage/status/production-pilot/pilot-tenant-baseline.json",
    )
    args = parser.parse_args(argv)
    record = build_p0_tenant_record(pilot_owner=args.pilot_owner, mailbox=args.mailbox)
    failures = validate_pilot_tenant_record(record)
    if failures:
        print("FAIL", failures)
        return 1
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
    print(record["tenant_id"], record["config_hash"][:16])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
