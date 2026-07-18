#!/usr/bin/env python3
"""Copy a verified local backup to an offsite destination (Kapitel 12 RB-01).

Designed as OFFSITE_BACKUP_COMMAND — receives the local backup path as argv[1].

Required env:
  OFFSITE_BACKUP_DEST_DIR — destination directory (must not equal BACKUP_DIR)

Optional env:
  OFFSITE_STATUS_FILE — separate offsite metadata JSON path
  BACKUP_DIR — used only to write a local .offsite_verified marker

Exit 0 on success; non-zero on copy/checksum/verification failure.
Never logs or prints secrets.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".offsite-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"))
            handle.write("\n")
        os.replace(tmp, path)
        os.chmod(path, 0o640)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: offsite_backup_upload.py <backup_file>", file=sys.stderr)
        return 2

    src = Path(sys.argv[1]).resolve()
    if not src.is_file():
        print("[offsite] source file missing", file=sys.stderr)
        return 1

    dest_root = os.environ.get("OFFSITE_BACKUP_DEST_DIR", "").strip()
    if not dest_root:
        print("[offsite] OFFSITE_BACKUP_DEST_DIR is required", file=sys.stderr)
        return 1

    backup_dir = os.environ.get("BACKUP_DIR", "").strip()
    if backup_dir:
        try:
            if src.parent.resolve() == Path(dest_root).resolve():
                print("[offsite] destination must differ from BACKUP_DIR", file=sys.stderr)
                return 1
        except OSError:
            pass

    dest_dir = Path(dest_root)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / src.name

    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    src_hash = _sha256_file(src)
    try:
        shutil.copy2(src, dest_file)
    except OSError as exc:
        print(f"[offsite] copy failed: {type(exc).__name__}", file=sys.stderr)
        return 1

    dest_hash = _sha256_file(dest_file)
    if src_hash != dest_hash:
        try:
            dest_file.unlink(missing_ok=True)
        except OSError:
            pass
        print("[offsite] checksum mismatch after copy", file=sys.stderr)
        return 1

    sidecar = dest_dir / f"{src.name}.sha256"
    sidecar.write_text(f"{dest_hash}  {src.name}\n", encoding="utf-8")

    marker = src.parent / f"{src.name}.offsite_verified"
    marker.write_text(
        json.dumps({"sha256": dest_hash, "offsite_file": dest_file.name}),
        encoding="utf-8",
    )

    completed = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    backup_id = src.name.removesuffix(".sql.gz").removesuffix(".sql")
    status_payload = {
        "schema_version": 1,
        "backup_id": backup_id,
        "status": "success",
        "checksum_sha256": dest_hash,
        "size_bytes": dest_file.stat().st_size,
        "started_at": started,
        "completed_at": completed,
        "verified": True,
    }
    status_file = os.environ.get("OFFSITE_STATUS_FILE", "").strip()
    if status_file:
        try:
            _atomic_write_json(Path(status_file), status_payload)
        except OSError as exc:
            print(f"[offsite] status write failed: {type(exc).__name__}", file=sys.stderr)
            return 1

    print(f"[offsite] upload verified: {dest_file.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
