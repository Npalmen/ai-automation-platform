#!/usr/bin/env python3
"""Read-only production runtime readiness for P1 operational restart."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.production_pilot.constants import PILOT_TENANT_ID
from app.production_pilot.observability.runtime_readiness import build_p1_runtime_readiness
from app.repositories.postgres.database import SessionLocal


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Production pilot P1 runtime readiness")
    parser.add_argument("--tenant-id", default=PILOT_TENANT_ID)
    parser.add_argument("--expected-runtime-sha", required=True)
    parser.add_argument("--backup-reference", default=None)
    parser.add_argument(
        "--output",
        default="storage/status/production-pilot/p1-runtime-readiness.json",
    )
    args = parser.parse_args(argv)
    db = SessionLocal()
    try:
        report = build_p1_runtime_readiness(
            db,
            tenant_id=args.tenant_id,
            expected_runtime_sha=args.expected_runtime_sha,
            backup_reference=args.backup_reference,
        )
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(report["overall_status"])
        if report.get("oauth_token_exposed"):
            return 2
        return 0 if not report.get("blockers") else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
