#!/usr/bin/env python3
"""Emit P1 daily operational report from live DB records."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.production_pilot.constants import PILOT_TENANT_ID
from app.production_pilot.observability.daily_report import (
    build_p1_daily_report,
    render_p1_daily_report_markdown,
)
from app.repositories.postgres.database import SessionLocal


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Production pilot P1 daily report")
    parser.add_argument("--tenant-id", default=PILOT_TENANT_ID)
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)
    day = date.fromisoformat(args.date)
    output = args.output or f"storage/status/production-pilot-p1-daily-{args.date}.md"
    db = SessionLocal()
    try:
        report = build_p1_daily_report(db, tenant_id=args.tenant_id, day=day)
        markdown = render_p1_daily_report_markdown(report)
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(markdown, encoding="utf-8")
        json_path = out_path.with_suffix(".json")
        json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(report["report_schema_version"])
        print(out_path)
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
