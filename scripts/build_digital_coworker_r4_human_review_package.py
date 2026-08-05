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

from app.evaluation.profile_testbot.qualification.coworker_r4_human_review import (  # noqa: E402
    build_r4_human_review_package,
    evaluate_r4_human_review_authorization,
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
    parser.add_argument("--candidates-json", required=True)
    parser.add_argument("--profile-id", default=R4_PROFILE_ID)
    parser.add_argument("--status-dir", default=str(ROOT / "storage" / "status"))
    args = parser.parse_args()
    _ = args.profile_id
    runtime_sha = args.runtime_sha.strip() or _git_sha()
    candidates = json.loads(Path(args.candidates_json).read_text(encoding="utf-8"))
    auth = evaluate_r4_human_review_authorization(candidates)
    package = build_r4_human_review_package(candidates, runtime_sha=runtime_sha)
    paths = write_r4_human_review_package(package, Path(args.status_dir))
    for path in paths.values():
        print(f"wrote {path}")
    print(f"human_review_authorized={package.get('human_review_authorized')}")
    print(f"qualification_status={package.get('qualification_status')}")
    print(f"send_review_count={package.get('send_review_count')}")
    if not auth.get("human_review_authorized"):
        print(f"authorization_blockers={auth.get('blockers')}", file=sys.stderr)
        print("diagnostic package only; no PENDING review slots")
        return 1
    print("human_review_complete=false (PENDING slots; manual review required)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
