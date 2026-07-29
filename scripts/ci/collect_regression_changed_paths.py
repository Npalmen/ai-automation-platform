"""CI helper to emit changed paths for regression impact selection."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


def collect_changed_paths(base_ref: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
    lines = [line.strip() for line in (result.stdout or "").splitlines() if line.strip()]
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect changed paths for regression impact")
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    paths = collect_changed_paths(args.base_ref)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump(paths, handle)
    print(len(paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
