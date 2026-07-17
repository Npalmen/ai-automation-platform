#!/usr/bin/env python3
"""Write validated build-metadata.json for Docker image (Kapitel 8)."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile

SHA_PATTERN = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)
UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
FORBIDDEN_RELEASE_SUBSTRINGS = ("password", "secret", "token", "key=")


def validate_commit_sha(value: str) -> str:
    if value == "unknown":
        return value
    if not SHA_PATTERN.match(value):
        raise ValueError("commit sha must be 7-40 hex chars or 'unknown'")
    return value.lower()


def validate_build_time(value: str) -> str:
    if value == "unknown":
        return value
    if not UTC_PATTERN.match(value):
        raise ValueError("build_time must be ISO-8601 UTC ending with Z")
    return value


def validate_release_id(value: str) -> str:
    if not value:
        raise ValueError("release_id is required")
    if len(value) > 128:
        raise ValueError("release_id exceeds 128 characters")
    lowered = value.lower()
    for forbidden in FORBIDDEN_RELEASE_SUBSTRINGS:
        if forbidden in lowered:
            raise ValueError("release_id contains forbidden pattern")
    return value


def atomic_write(path: str, payload: dict) -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".build-meta-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, separators=(",", ":"))
            handle.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Write build metadata JSON")
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--build-time", required=True)
    parser.add_argument("--release-id", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload = {
        "schema_version": 1,
        "commit_sha": validate_commit_sha(args.commit_sha),
        "build_time": validate_build_time(args.build_time),
        "release_id": validate_release_id(args.release_id),
        "source": "docker_build",
    }
    atomic_write(args.output, payload)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"validation error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
