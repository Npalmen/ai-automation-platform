#!/usr/bin/env python3
"""Build write-free R4 candidate package (no Gmail writes)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.evaluation.profile_testbot.qualification.coworker_r4_candidates import (  # noqa: E402
    generate_r4_candidates,
    write_r4_candidate_package,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (  # noqa: E402
    R4_PROFILE_ID,
)


def _git_sha() -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return (proc.stdout or "").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build R4 write-free candidate package")
    parser.add_argument("--runtime-sha", default="")
    parser.add_argument("--profile-id", default=R4_PROFILE_ID)
    parser.add_argument("--status-dir", default=str(ROOT / "storage" / "status"))
    args = parser.parse_args()
    runtime_sha = args.runtime_sha.strip() or _git_sha()
    result = generate_r4_candidates(runtime_sha=runtime_sha, profile_id=args.profile_id)
    paths = write_r4_candidate_package(result, Path(args.status_dir))
    for path in paths.values():
        print(f"wrote {path}")
    print(f"overall_status={result.get('overall_status')}")
    if result.get("overall_status") != "PASS":
        print(result.get("blocking_failures"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
