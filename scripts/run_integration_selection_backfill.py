#!/usr/bin/env python3
"""Run integration selection backfill (Slice B) — idempotent, dry-run capable."""

from __future__ import annotations

import argparse
import json
import sys

from app.repositories.postgres.database import SessionLocal


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill settings.integrations.selections")
    parser.add_argument("--tenant-id", help="Single tenant id (default: all tenants)")
    parser.add_argument("--dry-run", action="store_true", help="Classify only, do not persist")
    parser.add_argument("--verify", action="store_true", help="Compare selections vs allowed_integrations")
    args = parser.parse_args()

    from app.admin.integrations.selection_backfill import execute_backfill_run

    db = SessionLocal()
    try:
        out = execute_backfill_run(
            db,
            tenant_id=args.tenant_id,
            dry_run=args.dry_run,
            verify=args.verify,
        )
        db.commit()
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        db.commit()
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
