#!/usr/bin/env python3
"""Read-only internal pilot readiness report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.internal_pilot.constants import PILOT_TENANT_ID
from app.internal_pilot.readiness import build_internal_pilot_readiness
from app.repositories.postgres.database import SessionLocal
from app.repositories.postgres.tenant_config_repository import TenantConfigRepository


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build internal pilot readiness report")
    parser.add_argument("--tenant-id", default=PILOT_TENANT_ID)
    parser.add_argument("--baseline-git-sha", default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        settings = TenantConfigRepository.get_settings(db, args.tenant_id)

    report = build_internal_pilot_readiness(
        tenant_id=args.tenant_id,
        settings=settings,
        baseline_git_sha=args.baseline_git_sha,
    )
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if report["overall_status"] != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
