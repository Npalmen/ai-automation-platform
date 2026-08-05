#!/usr/bin/env python3
"""Build R4 human-review package from candidate package (no Gmail writes)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.evaluation.profile_testbot.qualification.coworker_r4_candidates import (  # noqa: E402
    generate_r4_candidates,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_human_review import (  # noqa: E402
    build_r4_human_review_package,
    write_r4_human_review_package,
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
    parser = argparse.ArgumentParser(description="Build R4 human-review package")
    parser.add_argument("--runtime-sha", default="")
    parser.add_argument("--candidates-json", default="")
    parser.add_argument("--profile-id", default=R4_PROFILE_ID)
    parser.add_argument("--status-dir", default=str(ROOT / "storage" / "status"))
    args = parser.parse_args()
    runtime_sha = args.runtime_sha.strip() or _git_sha()
    if args.candidates_json:
        candidates = json.loads(Path(args.candidates_json).read_text(encoding="utf-8"))
    else:
        candidates = generate_r4_candidates(runtime_sha=runtime_sha, profile_id=args.profile_id)
    package = build_r4_human_review_package(candidates, runtime_sha=runtime_sha)
    paths = write_r4_human_review_package(package, Path(args.status_dir))
    for path in paths.values():
        print(f"wrote {path}")
    print("human_review_complete=false (PENDING slots; manual review required)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
