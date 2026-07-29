#!/usr/bin/env python3
"""Restore production pilot tenant baseline from snapshot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.production_pilot.config_snapshot import compute_snapshot_hash, restore_snapshot_payload, verify_snapshot_hash
from app.production_pilot.tenant_baseline import build_p0_tenant_record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Restore production pilot baseline")
    parser.add_argument(
        "--baseline",
        default="storage/status/production-pilot/pilot-tenant-baseline.json",
    )
    parser.add_argument("--execute", action="store_true", default=False)
    args = parser.parse_args(argv)
    record = build_p0_tenant_record()
    if Path(args.baseline).is_file():
        record = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    snapshot = ((record.get("settings") or {}).get("production_pilot") or {}).get("config_snapshot")
    if not snapshot or not verify_snapshot_hash(snapshot):
        print("FAIL invalid snapshot")
        return 1
    restored = restore_snapshot_payload(snapshot)
    restored_hash = compute_snapshot_hash(restored)
    if restored_hash != snapshot["snapshot_hash"]:
        print("FAIL restored hash mismatch")
        return 1
    print(json.dumps({"status": "PASS", "snapshot_hash": restored_hash[:16], "execute": args.execute}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
