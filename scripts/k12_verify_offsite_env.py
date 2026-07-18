#!/usr/bin/env python3
"""Verify /opt/krowolf/.env.offsite exists and is configured — never print secret values."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

PATH = Path("/opt/krowolf/.env.offsite")
REQUIRED = (
    "OFFSITE_S3_ENDPOINT",
    "OFFSITE_S3_BUCKET",
    "OFFSITE_S3_ACCESS_KEY_ID",
    "OFFSITE_S3_SECRET_ACCESS_KEY",
)


def main() -> int:
    if not PATH.is_file():
        print("FAIL offsite_env: file missing")
        return 1
    st = PATH.stat()
    mode = stat.S_IMODE(st.st_mode)
    if mode != 0o600:
        print(f"FAIL offsite_env: mode={oct(mode)} expected 0o600")
        return 1
    if PATH.owner() != "root":
        print(f"FAIL offsite_env: owner={PATH.owner()} expected root")
        return 1
  # Parse keys only
    keys_present: set[str] = set()
    for line in PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if val:
            keys_present.add(key)
    missing = [k for k in REQUIRED if k not in keys_present]
    if missing:
        print(f"FAIL offsite_env: missing keys: {', '.join(missing)}")
        return 1
    print("PASS offsite_env: file present, mode 600, root-owned, required keys set")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
