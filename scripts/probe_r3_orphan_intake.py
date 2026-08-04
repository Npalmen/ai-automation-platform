#!/usr/bin/env python3
"""Read-only orphan exact-message intake probe for R3 live canary."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _load_env() -> None:
    try:
        from dotenv import dotenv_values
    except ImportError:
        dotenv_values = None  # type: ignore[assignment,misc]

    for path in (ROOT / ".env", ROOT / ".env.live-eval.local"):
        if not path.is_file():
            continue
        if dotenv_values is not None:
            for key, value in dotenv_values(path).items():
                if value is not None and str(value).strip():
                    os.environ[key] = str(value).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="R3 orphan intake read-only probe")
    parser.add_argument(
        "--evaluation-run-id",
        default="ccd9916f-c4b7-4b1c-aabc-fb2da09f89cf",
        help="Evaluation run ID for orphan attempt 4",
    )
    parser.add_argument(
        "--tenant-id",
        default="TENANT_LIVE_EVAL",
        help="Tenant ID",
    )
    parser.add_argument(
        "--classification",
        default="orphaned_attempt_4_intake_probe_verified",
        help="Probe classification (not counted as approved reply)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional JSON output path under storage/status",
    )
    args = parser.parse_args()

    _load_env()
    os.environ.setdefault("LIVE_EVAL_ALLOWED", "yes")
    os.environ.setdefault("LIVE_GMAIL_EVAL_ALLOWED", "yes")

    from app.repositories.postgres.database import SessionLocal
    from app.repositories.postgres.live_eval_repository import LiveEvalRunRepository
    from app.evaluation.live.delivery_mailbox_reader import probe_orphan_intake_observation

    db = SessionLocal()
    try:
        row = LiveEvalRunRepository.get_run(
            db, args.evaluation_run_id, tenant_id=args.tenant_id
        )
        if row is None:
            print(json.dumps({"error": "run not found"}, indent=2))
            return 1
        result = probe_orphan_intake_observation(
            db,
            row=row,
            classification=args.classification,
        )
        payload = result.to_dict()
        payload["orphaned_attempt_4_intake_probe_verified"] = (
            result.verified
            and args.classification == "orphaned_attempt_4_intake_probe_verified"
        )
        print(json.dumps(payload, indent=2))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return 0 if result.verified else 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
