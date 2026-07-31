"""Read-only pipeline worker build identity for live eval runtime evidence."""

from __future__ import annotations

import os

from app.core.canonical_commit import normalize_commit_sha

FULL_GIT_SHA_LENGTH = 40

_PIPELINE_IMPORT_BUILD_SHA = normalize_commit_sha(os.environ.get("BUILD_GIT_SHA"))
_LAST_PIPELINE_EXECUTION_SHA: str | None = None


def require_full_git_sha(value: str | None) -> str | None:
    """Return a normalized 40-char git SHA or None when missing/short/invalid."""
    cleaned = normalize_commit_sha(value)
    if not cleaned or len(cleaned) != FULL_GIT_SHA_LENGTH:
        return None
    return cleaned


def resolve_api_build_git_sha() -> str | None:
    return require_full_git_sha(os.environ.get("BUILD_GIT_SHA"))


def record_pipeline_execution_build_sha() -> str | None:
    """Record the build SHA used by the pipeline executor for the latest intake."""
    global _LAST_PIPELINE_EXECUTION_SHA
    sha = resolve_api_build_git_sha()
    _LAST_PIPELINE_EXECUTION_SHA = sha
    return sha


def resolve_worker_build_git_sha() -> str | None:
    """Worker SHA: last pipeline execution when known, else current pipeline binding."""
    if _LAST_PIPELINE_EXECUTION_SHA:
        return _LAST_PIPELINE_EXECUTION_SHA
    current = resolve_api_build_git_sha()
    if current:
        return current
    return _PIPELINE_IMPORT_BUILD_SHA
