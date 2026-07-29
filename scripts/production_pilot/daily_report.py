#!/usr/bin/env python3
"""Emit daily production pilot operator report."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.production_pilot.constants import PILOT_TENANT_ID
from app.production_pilot.daily_report import build_daily_pilot_report
from app.production_pilot.tenant_baseline import build_p0_tenant_record


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Production pilot daily operator report")
    parser.add_argument(
        "--output",
        default="storage/status/production-pilot/daily-report.json",
    )
    args = parser.parse_args(argv)
    record = build_p0_tenant_record()
    report = build_daily_pilot_report(
        tenant_id=PILOT_TENANT_ID,
        settings=record["settings"],
        runtime_sha=_git_sha(),
        ops_state={},
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(report["report_schema_version"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
