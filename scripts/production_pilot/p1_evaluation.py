#!/usr/bin/env python3
"""Evaluate production pilot P1 observe-only acceptance criteria."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.production_pilot.p1_evaluation import run_p1_evaluation


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Production pilot P1 evaluation")
    parser.add_argument("--backup-reference", default="backup-p1-evaluation-synthetic")
    parser.add_argument("--preflight-json", default="storage/status/production-pilot/p1-preflight.json")
    parser.add_argument("--output-json", default="storage/status/production-pilot/p1-evaluation.json")
    parser.add_argument("--output-md", default="storage/status/production-pilot/p1-result.md")
    args = parser.parse_args(argv)
    preflight = None
    preflight_path = Path(args.preflight_json)
    if preflight_path.is_file():
        preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    report = run_p1_evaluation(
        runtime_sha=_git_sha(),
        backup_reference=args.backup_reference,
        preflight=preflight,
    )
    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# Production pilot P1 result",
        "",
        f"- status: **{report['status']}**",
        f"- tenant: `{report['tenant_id']}`",
    ]
    for qualification in report.get("qualifications", []):
        lines.append(f"- qualification: `{qualification}`")
    Path(args.output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(report["status"])
    for qualification in report.get("qualifications", []):
        print(qualification)
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
