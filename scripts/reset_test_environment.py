"""CLI for local/test environment inventory, purge, prune and baseline seed."""

from __future__ import annotations

import argparse
import sys

from app.repositories.postgres.database import SessionLocal
from app.tools.test_environment.baseline_service import seed_baseline
from app.tools.test_environment.guards import GuardError, assert_execute_allowed, assert_inventory_allowed
from app.tools.test_environment.inventory import build_inventory_report, resolve_purge_tenant_ids
from app.tools.test_environment.models import OperationReport, StaleDataType
from app.tools.test_environment.prune_stale import prune_stale_data
from app.tools.test_environment.purge_tenants import purge_tenants


def _print_report(report: OperationReport) -> None:
    mode = "DRY-RUN" if report.dry_run else "EXECUTE"
    print(f"=== {report.command} ({mode}) ===")
    if not report.lines:
        print("No matching rows.")
        return
    print(f"{'table':<28} {'tenant_id':<24} {'rows':>6}  {'action':<22} note")
    print("-" * 90)
    for line in report.lines:
        note = f" {line.note}" if line.note else ""
        print(
            f"{line.table:<28} {line.tenant_id:<24} {line.rows:>6}  "
            f"{line.action.value:<22}{note}"
        )
    print(f"Total mutation rows: {report.total_mutations}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Local/test environment maintenance (never for production).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("inventory", help="List tenant-linked row counts")

    purge_parser = subparsers.add_parser(
        "purge-tenants",
        help="Remove explicit tenant(s) and orphan incidents when safe",
    )
    purge_parser.add_argument("--tenant-id", action="append", default=[])
    purge_parser.add_argument(
        "--profile",
        choices=["local-standard"],
        help="Expand to versionshanterad purge allowlist (never deletes unknown tenants)",
    )
    purge_parser.add_argument(
        "--execute",
        action="store_true",
        help="Perform deletion (default is dry-run)",
    )
    purge_parser.add_argument("--confirm", default="")

    prune_parser = subparsers.add_parser(
        "prune-stale-data",
        help="Delete stale rows for one tenant, data type and age threshold",
    )
    prune_parser.add_argument("--tenant-id", required=True)
    prune_parser.add_argument(
        "--data-type",
        required=True,
        choices=[item.value for item in StaleDataType],
    )
    prune_parser.add_argument("--older-than-days", type=int, required=True)
    prune_parser.add_argument("--execute", action="store_true")
    prune_parser.add_argument("--confirm", default="")

    seed_parser = subparsers.add_parser(
        "seed-baseline",
        help="Upsert reserved baseline tenant dataset",
    )
    seed_parser.add_argument("--execute", action="store_true")
    seed_parser.add_argument("--confirm", default="")

    args = parser.parse_args(argv)
    db = SessionLocal()
    try:
        if args.command == "inventory":
            assert_inventory_allowed()
            targets, _ = resolve_purge_tenant_ids(
                explicit_tenant_ids=getattr(args, "tenant_id", []) or [],
                profile=getattr(args, "profile", None),
            )
            target_set = set(targets) if targets else None
            report = build_inventory_report(db, target_tenant_ids=target_set)
            _print_report(report)
            return 0

        dry_run = not args.execute

        if args.command == "purge-tenants":
            if not dry_run:
                assert_execute_allowed(confirm=args.confirm)
            if not args.tenant_id and not args.profile:
                print(
                    "ERR purge-tenants requires --tenant-id and/or --profile local-standard",
                    file=sys.stderr,
                )
                return 2
            report = purge_tenants(
                db,
                explicit_tenant_ids=args.tenant_id,
                profile=args.profile,
                dry_run=dry_run,
            )
            _print_report(report)
            return 0

        if args.command == "prune-stale-data":
            if not dry_run:
                assert_execute_allowed(confirm=args.confirm)
            report = prune_stale_data(
                db,
                tenant_id=args.tenant_id,
                data_type=StaleDataType(args.data_type),
                older_than_days=args.older_than_days,
                dry_run=dry_run,
            )
            _print_report(report)
            return 0

        if args.command == "seed-baseline":
            if not dry_run:
                assert_execute_allowed(confirm=args.confirm)
            report = seed_baseline(db, dry_run=dry_run)
            _print_report(report)
            return 0

        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 2
    except GuardError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"ERR: {exc}", file=sys.stderr)
        return 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
