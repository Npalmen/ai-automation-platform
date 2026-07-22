"""Resolved storage paths for live-eval journals and CI artifacts."""

from __future__ import annotations

from pathlib import Path

from app.core.settings import get_settings


def resolved_storage_path() -> Path:
    return Path(get_settings().STORAGE_PATH).resolve()


def resolved_live_eval_root() -> Path:
    return resolved_storage_path() / "live_eval"


def resolved_run_directory(evaluation_run_id: str) -> Path:
    return resolved_live_eval_root() / "runs" / evaluation_run_id
