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

    from app.admin.integrations.selection_backfill import (
        backfill_tenant_selections,
        run_backfill_all_tenants,
        verify_selections_vs_allowed_integrations,
    )
    from app.repositories.postgres.tenant_config_repository import TenantConfigRepository

    db = SessionLocal()
    try:
        if args.tenant_id:
            report = backfill_tenant_selections(db, args.tenant_id, dry_run=args.dry_run)
            out = {
                "tenant_id": report.tenant_id,
                "updated": report.updated,
                "skipped": report.skipped,
                "decisions": [d.__dict__ for d in report.decisions],
                "errors": report.errors,
            }
            if args.verify:
                record = TenantConfigRepository.get(db, args.tenant_id)
                out["verification"] = verify_selections_vs_allowed_integrations(record) if record else {}
            if not args.dry_run:
                db.commit()
        else:
            out = run_backfill_all_tenants(db, dry_run=args.dry_run)
            if not args.dry_run:
                db.commit()
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        db.rollback()
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
