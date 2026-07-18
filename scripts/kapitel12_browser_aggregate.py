#!/usr/bin/env python3
"""
Aggregate per-role browser reports into scripts/kapitel12_browser_report.json.

PASS only when read_only, operations, and admin role reports are all PASS.
Never includes credentials.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.k12_browser_common import (  # noqa: E402
    ROLE_REPORT_NAMES,
    aggregate_report_path,
    aggregate_role_reports,
    write_json_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate K12 browser role reports.")
    parser.add_argument(
        "--status-dir",
        default="",
        help="Directory containing role reports (default: /opt/krowolf/storage/status or scripts/)",
    )
    args = parser.parse_args()

    if args.status_dir:
        base = Path(args.status_dir)
    else:
        base = Path("/opt/krowolf/storage/status")
        if not base.is_dir():
            base = ROOT / "scripts"

    report_paths = {role: base / name for role, name in ROLE_REPORT_NAMES.items()}
    payload = aggregate_role_reports(report_paths)
    out = aggregate_report_path() if args.status_dir == "" else base / "kapitel12_browser_report.json"
    write_json_report(out, payload, secrets=set())
    print(f"status={payload['status']}")
    print(f"report={out}")
    for role, info in payload["roles"].items():
        print(f"{role}: {info.get('status')}")
    return 0 if payload["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
