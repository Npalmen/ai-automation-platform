"""Resolve the canonical runtime Git commit for audit and operational evidence."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from app.admin.system_status_sources import MetadataReadOutcome, read_build_metadata
from app.core.settings import get_settings

_SHA_PATTERN = re.compile(r"^[0-9a-f]{7,40}$", re.IGNORECASE)
_ENV_KEYS = ("BUILD_COMMIT_SHA", "GIT_COMMIT", "COMMIT_SHA")


def normalize_commit_sha(value: str | None) -> str | None:
    """Return lowercase hex SHA or None when value is missing/invalid."""
    if value is None:
        return None
    cleaned = value.strip().lower()
    if not cleaned or cleaned == "unknown":
        return None
    if not _SHA_PATTERN.match(cleaned):
        return None
    return cleaned


def _from_env() -> str | None:
    for key in _ENV_KEYS:
        resolved = normalize_commit_sha(os.environ.get(key))
        if resolved:
            return resolved
    return None


def _from_build_metadata() -> str | None:
    result = read_build_metadata(get_settings())
    if result.outcome != MetadataReadOutcome.VALID or not result.data:
        return None
    return normalize_commit_sha(str(result.data.get("commit_sha") or ""))


def _from_git() -> str | None:
    env = os.environ.get("ENV", "dev").strip().lower()
    if env not in {"dev", "test"}:
        return None
    if not Path(".git").is_dir():
        return None
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return normalize_commit_sha(proc.stdout)


def resolve_canonical_commit(*, explicit: str | None = None) -> str | None:
    """Resolve runtime commit SHA for audit trails.

    Priority:
    1. explicit override (CLI/caller)
    2. runtime env (BUILD_COMMIT_SHA, GIT_COMMIT, COMMIT_SHA)
    3. build metadata file (BUILD_METADATA_PATH)
    4. git HEAD in dev/test when .git exists
    5. None
    """
    if explicit is not None:
        resolved = normalize_commit_sha(explicit)
        if resolved:
            return resolved
    for resolver in (_from_env, _from_build_metadata, _from_git):
        resolved = resolver()
        if resolved:
            return resolved
    return None
