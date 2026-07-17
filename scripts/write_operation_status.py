#!/usr/bin/env python3
"""Atomically write backup or restore operation status JSON (Kapitel 8)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

ALLOWED_OPERATION_STATUS = frozenset({"success", "failed"})
ALLOWED_BACKUP_ERRORS = frozenset(
    {
        "pg_dump_failed",
        "gzip_invalid",
        "backup_too_small",
        "offsite_failed",
        "metadata_dir_unwritable",
    }
)
ALLOWED_RESTORE_ERRORS = frozenset(
    {
        "restore_failed",
        "verify_failed",
        "safety_refused",
    }
)
ALLOWED_VERIFICATION = frozenset({"success", "failed", "not_performed", "unknown"})


def _atomic_write(path: str, payload: dict) -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, mode=0o750, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".status-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"))
            handle.write("\n")
        os.chmod(tmp_path, 0o640)
        os.replace(tmp_path, path)
        os.chmod(path, 0o640)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _parse_backup_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write backup status metadata")
    parser.add_argument("--output", required=True)
    parser.add_argument("--backup-id", required=True)
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--completed-at", required=True)
    parser.add_argument("--status", required=True, choices=sorted(ALLOWED_OPERATION_STATUS))
    parser.add_argument("--size-bytes", type=int, default=0)
    parser.add_argument("--retention-days", type=int, default=0)
    parser.add_argument("--archive-integrity-verified", choices=("true", "false"), default="false")
    parser.add_argument("--error-code", default="")
    return parser.parse_args()


def _parse_restore_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write restore status metadata")
    parser.add_argument("--output", required=True)
    parser.add_argument("--test-id", required=True)
    parser.add_argument("--backup-id", required=True)
    parser.add_argument("--started-at", required=True)
    parser.add_argument("--completed-at", required=True)
    parser.add_argument("--status", required=True, choices=sorted(ALLOWED_OPERATION_STATUS))
    parser.add_argument("--schema-verification", required=True, choices=sorted(ALLOWED_VERIFICATION))
    parser.add_argument(
        "--application-smoke-verification",
        required=True,
        choices=sorted(ALLOWED_VERIFICATION),
    )
    parser.add_argument("--error-code", default="")
    return parser.parse_args()


def write_backup_status(args: argparse.Namespace) -> None:
    error_code = args.error_code or None
    if error_code is not None and error_code not in ALLOWED_BACKUP_ERRORS:
        raise ValueError("invalid backup error_code")
    payload = {
        "schema_version": 1,
        "backup_id": args.backup_id,
        "started_at": args.started_at,
        "completed_at": args.completed_at,
        "status": args.status,
        "size_bytes": args.size_bytes,
        "retention_days": args.retention_days,
        "archive_integrity_verified": args.archive_integrity_verified == "true",
        "error_code": error_code,
    }
    _atomic_write(args.output, payload)


def write_restore_status(args: argparse.Namespace) -> None:
    error_code = args.error_code or None
    if error_code is not None and error_code not in ALLOWED_RESTORE_ERRORS:
        raise ValueError("invalid restore error_code")
    payload = {
        "schema_version": 1,
        "test_id": args.test_id,
        "backup_id": args.backup_id,
        "started_at": args.started_at,
        "completed_at": args.completed_at,
        "status": args.status,
        "schema_verification": args.schema_verification,
        "application_smoke_verification": args.application_smoke_verification,
        "error_code": error_code,
    }
    _atomic_write(args.output, payload)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: write_operation_status.py backup|restore ...", file=sys.stderr)
        return 2
    command = sys.argv[1]
    sys.argv = [sys.argv[0], *sys.argv[2:]]
    try:
        if command == "backup":
            write_backup_status(_parse_backup_args())
        elif command == "restore":
            write_restore_status(_parse_restore_args())
        else:
            print(f"unknown command: {command}", file=sys.stderr)
            return 2
    except (ValueError, OSError) as exc:
        print(f"write failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
