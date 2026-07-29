#!/usr/bin/env python3
"""Evaluate P1 operational evidence for P2 readiness."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.canonical_commit import resolve_canonical_commit
from app.production_pilot.constants import PILOT_TENANT_ID
from app.production_pilot.observability.operational_evaluation import (
    evaluate_p1_operational_evidence,
    render_operational_result_markdown,
)
from app.repositories.postgres.database import SessionLocal


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Production pilot P1 operational evaluation")
    parser.add_argument("--tenant-id", default=PILOT_TENANT_ID)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    parser.add_argument("--expected-runtime-sha", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args(argv)
    run_id = f"{args.start_date}-{args.end_date}"
    output = args.output or f"storage/status/production-pilot-p1-operational-result-{run_id}.md"
    db = SessionLocal()
    try:
        report = evaluate_p1_operational_evidence(
            db,
            tenant_id=args.tenant_id,
            start_date=date.fromisoformat(args.start_date),
            end_date=date.fromisoformat(args.end_date),
            runtime_sha=resolve_canonical_commit(),
            expected_runtime_sha=args.expected_runtime_sha,
        )
        markdown = render_operational_result_markdown(report)
        out_path = Path(output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(markdown, encoding="utf-8")
        out_path.with_suffix(".json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(report["p2_readiness"])
        return 0 if report["operational_pass"] else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
