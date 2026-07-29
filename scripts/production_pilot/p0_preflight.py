#!/usr/bin/env python3
"""Run hermetic production pilot P0 preflight."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.production_pilot.preflight import run_p0_preflight


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Production pilot P0 preflight")
    parser.add_argument("--backup-reference", default="backup-preflight-synthetic")
    parser.add_argument(
        "--output-json",
        default="storage/status/production-pilot/p0-preflight.json",
    )
    parser.add_argument(
        "--output-md",
        default="storage/status/production-pilot/p0-preflight.md",
    )
    args = parser.parse_args(argv)
    report = run_p0_preflight(
        runtime_sha=_git_sha(),
        backup_reference=args.backup_reference,
    )
    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# Production pilot P0 preflight",
        "",
        f"- status: **{report['status']}**",
        f"- tenant: `{report['tenant_id']}`",
        f"- synthetic inbound: {report['synthetic_inbound_count']}",
        f"- gmail replies: {report['gmail_replies']}",
        f"- non-gmail writes: {report['non_gmail_writes']}",
    ]
    if report.get("qualification"):
        lines.append(f"- qualification: `{report['qualification']}`")
    Path(args.output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(report["status"])
    if report.get("qualification"):
        print(report["qualification"])
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
