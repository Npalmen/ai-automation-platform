"""Repository root resolution for live-eval harness scripts (cwd-independent)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

AUTOMATIC_CANARY_REQUIRED_SCRIPT_MISSING = "automatic_canary_required_script_missing"

REQUIRED_AUTOMATIC_CANARY_SCRIPTS: tuple[str, ...] = (
    "snapshot_live_eval_tenant_config.py",
    "seed_live_eval_automatic_canary.py",
    "pause_live_eval_automatic_canary.py",
    "restore_live_eval_automatic_canary.py",
)


@lru_cache
def resolve_repository_root() -> Path:
    """Return repository root containing both app/ and scripts/."""
    anchor = Path(__file__).resolve()
    for candidate in anchor.parents:
        if (candidate / "app").is_dir() and (candidate / "scripts").is_dir():
            return candidate
    raise RuntimeError("repository root could not be resolved")


def resolve_scripts_directory() -> Path:
    return resolve_repository_root() / "scripts"


def resolve_required_script(script_name: str) -> Path:
    """Resolve an exact harness script under repository root scripts/."""
    if not script_name or "/" in script_name or "\\" in script_name:
        raise ValueError(f"invalid script name: {script_name!r}")
    path = resolve_scripts_directory() / script_name
    if not path.is_file():
        raise FileNotFoundError(
            f"{AUTOMATIC_CANARY_REQUIRED_SCRIPT_MISSING}: {script_name}"
        )
    return path


def validate_required_scripts(
    script_names: tuple[str, ...] = REQUIRED_AUTOMATIC_CANARY_SCRIPTS,
) -> list[str]:
    """Fail-closed when any required harness script is missing."""
    issues: list[str] = []
    for script_name in script_names:
        try:
            resolve_required_script(script_name)
        except FileNotFoundError as exc:
            issues.append(str(exc))
    return issues
