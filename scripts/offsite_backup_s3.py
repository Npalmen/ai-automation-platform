#!/usr/bin/env python3
"""Upload verified backup to S3-compatible object storage (Kapitel 12 RB-01).

Use as OFFSITE_BACKUP_COMMAND. Receives local backup path as argv[1].

Required env (never logged):
  OFFSITE_S3_ENDPOINT — e.g. https://hel1.your-objectstorage.com
  OFFSITE_S3_BUCKET
  OFFSITE_S3_ACCESS_KEY_ID
  OFFSITE_S3_SECRET_ACCESS_KEY

Optional:
  OFFSITE_S3_PREFIX — key prefix (default: krowolf-backups)
  OFFSITE_S3_REGION — default us-east-1
  OFFSITE_STATUS_FILE — JSON status path
  BACKUP_DIR — for local .offsite_verified marker

Exit 0 on verified upload; non-zero on failure.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

try:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:
    boto3 = None  # type: ignore


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
    if boto3 is None:
        print("[offsite-s3] boto3 not installed", file=sys.stderr)
        return 2
    if len(sys.argv) < 2:
        print("usage: offsite_backup_s3.py <backup_file>", file=sys.stderr)
        return 2

    src = Path(sys.argv[1]).resolve()
    if not src.is_file():
        print("[offsite-s3] source file missing", file=sys.stderr)
        return 1

    endpoint = os.environ.get("OFFSITE_S3_ENDPOINT", "").strip()
    bucket = os.environ.get("OFFSITE_S3_BUCKET", "").strip()
    access_key = os.environ.get("OFFSITE_S3_ACCESS_KEY_ID", "").strip()
    secret_key = os.environ.get("OFFSITE_S3_SECRET_ACCESS_KEY", "").strip()
    prefix = os.environ.get("OFFSITE_S3_PREFIX", "krowolf-backups").strip().strip("/")
    region = os.environ.get("OFFSITE_S3_REGION", "us-east-1").strip()

    missing = [
        name
        for name, val in (
            ("OFFSITE_S3_ENDPOINT", endpoint),
            ("OFFSITE_S3_BUCKET", bucket),
            ("OFFSITE_S3_ACCESS_KEY_ID", access_key),
            ("OFFSITE_S3_SECRET_ACCESS_KEY", secret_key),
        )
        if not val
    ]
    if missing:
        print(f"[offsite-s3] missing env: {', '.join(missing)}", file=sys.stderr)
        return 1

    started = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    src_hash = _sha256_file(src)
    key = f"{prefix}/{src.name}" if prefix else src.name

    parsed = urlparse(endpoint if "://" in endpoint else f"https://{endpoint}")
    endpoint_url = f"{parsed.scheme}://{parsed.netloc}"

    client = boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )

    try:
        client.upload_file(str(src), bucket, key)
        head = client.head_object(Bucket=bucket, Key=key)
        remote_size = int(head.get("ContentLength", 0))
    except (BotoCoreError, ClientError) as exc:
        print(f"[offsite-s3] upload failed: {type(exc).__name__}", file=sys.stderr)
        return 1

    if remote_size != src.stat().st_size:
        print("[offsite-s3] remote size mismatch", file=sys.stderr)
        try:
            client.delete_object(Bucket=bucket, Key=key)
        except (BotoCoreError, ClientError):
            pass
        return 1

    # Download to temp and verify checksum (end-to-end integrity)
    with tempfile.NamedTemporaryFile(delete=True) as tmp:
        try:
            client.download_file(bucket, key, tmp.name)
        except (BotoCoreError, ClientError) as exc:
            print(f"[offsite-s3] verify download failed: {type(exc).__name__}", file=sys.stderr)
            return 1
        verify_hash = _sha256_file(Path(tmp.name))
        if verify_hash != src_hash:
            print("[offsite-s3] checksum mismatch after round-trip", file=sys.stderr)
            return 1

    sidecar_key = f"{key}.sha256"
    sidecar_body = f"{src_hash}  {src.name}\n"
    try:
        client.put_object(Bucket=bucket, Key=sidecar_key, Body=sidecar_body.encode("utf-8"))
    except (BotoCoreError, ClientError) as exc:
        print(f"[offsite-s3] sidecar upload failed: {type(exc).__name__}", file=sys.stderr)
        return 1

    marker = src.parent / f"{src.name}.offsite_verified"
    marker.write_text(
        json.dumps({"sha256": src_hash, "offsite_key": key, "destination_type": "s3"}),
        encoding="utf-8",
    )

    completed = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    backup_id = src.name.removesuffix(".sql.gz").removesuffix(".sql")
    status_payload = {
        "schema_version": 1,
        "backup_id": backup_id,
        "status": "success",
        "destination_type": "s3",
        "checksum_sha256": src_hash,
        "size_bytes": src.stat().st_size,
        "started_at": started,
        "completed_at": completed,
        "verified": True,
    }
    status_file = os.environ.get("OFFSITE_STATUS_FILE", "").strip()
    if status_file:
        try:
            _atomic_write_json(Path(status_file), status_payload)
        except OSError as exc:
            print(f"[offsite-s3] status write failed: {type(exc).__name__}", file=sys.stderr)
            return 1

    print(f"[offsite-s3] upload verified: s3://{bucket}/{key}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
