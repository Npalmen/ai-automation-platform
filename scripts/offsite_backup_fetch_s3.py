#!/usr/bin/env python3
"""Fetch latest backup + sha256 sidecar from S3 for offsite restore rehearsal."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

try:
    import boto3
    from botocore.config import Config
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:
    boto3 = None  # type: ignore


def main() -> int:
    if boto3 is None:
        print("[offsite-fetch] boto3 not installed", file=sys.stderr)
        return 2
    if len(sys.argv) < 2:
        print("usage: offsite_backup_fetch_s3.py <dest_dir>", file=sys.stderr)
        return 2

    dest = Path(sys.argv[1])
    dest.mkdir(parents=True, exist_ok=True)

    endpoint = os.environ.get("OFFSITE_S3_ENDPOINT", "").strip()
    bucket = os.environ.get("OFFSITE_S3_BUCKET", "").strip()
    access_key = os.environ.get("OFFSITE_S3_ACCESS_KEY_ID", "").strip()
    secret_key = os.environ.get("OFFSITE_S3_SECRET_ACCESS_KEY", "").strip()
    prefix = os.environ.get("OFFSITE_S3_PREFIX", "krowolf-backups").strip().strip("/")
    db = os.environ.get("POSTGRES_DB", "ai_platform")

    parsed = urlparse(endpoint if "://" in endpoint else f"https://{endpoint}")
    client = boto3.client(
        "s3",
        endpoint_url=f"{parsed.scheme}://{parsed.netloc}",
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=os.environ.get("OFFSITE_S3_REGION", "us-east-1"),
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )

    try:
        resp = client.list_objects_v2(Bucket=bucket, Prefix=f"{prefix}/{db}_" if prefix else f"{db}_")
        contents = resp.get("Contents") or []
        backups = [o for o in contents if str(o["Key"]).endswith(".sql.gz")]
        if not backups:
            print("[offsite-fetch] no backups found", file=sys.stderr)
            return 1
        latest = sorted(backups, key=lambda o: o["Key"])[-1]
        key = latest["Key"]
        name = Path(key).name
        local = dest / name
        client.download_file(bucket, key, str(local))
        sidecar_key = f"{key}.sha256"
        try:
            sidecar_local = dest / f"{name}.sha256"
            client.download_file(bucket, sidecar_key, str(sidecar_local))
        except (BotoCoreError, ClientError):
            pass
    except (BotoCoreError, ClientError) as exc:
        print(f"[offsite-fetch] failed: {type(exc).__name__}", file=sys.stderr)
        return 1

    print(f"[offsite-fetch] fetched {local.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
