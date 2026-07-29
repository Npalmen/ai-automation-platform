#!/usr/bin/env python3
"""Register production pilot P1 operational readiness after observability fix."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.production_pilot.constants import PRODUCTION_PILOT_P1_OBSERVE_QUALIFIED
from app.production_pilot.p1_readiness import build_p1_readiness
from app.production_pilot.status import (
    PRODUCTION_PILOT_ACTIVE,
    PRODUCTION_PILOT_P1_OPERATIONAL_READY,
    evaluate_operational_ready_status,
)
from app.repositories.postgres.database import SessionLocal
from app.production_pilot.observability.runtime_readiness import build_p1_runtime_readiness


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Production pilot P1 operational ready registration")
    parser.add_argument("--backup-reference", default="backup-p1-operational-ready")
    parser.add_argument(
        "--output-json",
        default="storage/status/production-pilot/p1-operational-ready.json",
    )
    args = parser.parse_args(argv)
    runtime_sha = _git_sha()
    readiness = build_p1_readiness(runtime_sha=runtime_sha, backup_reference=args.backup_reference)
    db = SessionLocal()
    try:
        runtime_readiness = build_p1_runtime_readiness(
            db,
            tenant_id=readiness["tenant_id"],
            expected_runtime_sha=runtime_sha,
            backup_reference=args.backup_reference,
        )
    finally:
        db.close()
    status = evaluate_operational_ready_status(readiness=readiness, runtime_readiness=runtime_readiness)
    report = {
        "runtime_sha": runtime_sha,
        "readiness": readiness,
        "runtime_readiness": runtime_readiness,
        "status": status,
        "qualifications": [
            PRODUCTION_PILOT_P1_OBSERVE_QUALIFIED,
            PRODUCTION_PILOT_ACTIVE,
        ],
    }
    if PRODUCTION_PILOT_P1_OPERATIONAL_READY in status.get("registered", []):
        report["qualifications"].append(PRODUCTION_PILOT_P1_OPERATIONAL_READY)
    output = Path(args.output_json)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    for qualification in report["qualifications"]:
        print(qualification)
    return 0 if PRODUCTION_PILOT_P1_OPERATIONAL_READY in report["qualifications"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
