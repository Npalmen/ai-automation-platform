#!/usr/bin/env python3
"""Verify runtime against production pilot release manifest."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.production_pilot.release_manifest import validate_release_manifest


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify production pilot runtime manifest")
    parser.add_argument(
        "--manifest",
        default="storage/status/production-pilot/release-manifest.json",
    )
    args = parser.parse_args(argv)
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    failures = validate_release_manifest(manifest)
    runtime_sha = _git_sha()
    if manifest.get("commit_sha") not in {runtime_sha, runtime_sha[:7]}:
        if not runtime_sha.startswith(manifest.get("commit_sha", "")):
            failures.append(f"runtime sha mismatch: {runtime_sha} vs {manifest.get('commit_sha')}")
    if failures:
        print(json.dumps({"status": "FAIL", "failures": failures}, indent=2))
        return 1
    print(json.dumps({"status": "PASS", "runtime_sha": runtime_sha}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
