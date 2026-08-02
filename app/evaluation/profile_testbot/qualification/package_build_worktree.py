"""Worktree cleanliness checks for official coworker package builds."""

from __future__ import annotations

import subprocess
from pathlib import Path

ALLOWED_UNTRACKED_PREFIX = "storage/status/"


def classify_porcelain_lines(lines: list[str]) -> tuple[bool, list[str]]:
    """Return (is_clean, blocked_lines). Only storage/status/** may be dirty."""
    blocked: list[str] = []
    for raw in lines:
        ln = raw.rstrip("\n")
        if not ln.strip():
            continue
        path = ln[3:].strip() if len(ln) > 3 else ln.strip()
        norm = path.replace("\\", "/")
        if norm.startswith(ALLOWED_UNTRACKED_PREFIX):
            continue
        blocked.append(ln)
    return (len(blocked) == 0, blocked)


def git_porcelain_lines(repo_root: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return [ln for ln in (proc.stdout or "").splitlines() if ln.strip()]


def verify_clean_worktree(repo_root: Path) -> None:
    is_clean, blocked = classify_porcelain_lines(git_porcelain_lines(repo_root))
    if not is_clean:
        raise RuntimeError(
            "dirty worktree — commit, stash, or remove changes before building qualification package: "
            + "; ".join(blocked[:8])
        )
