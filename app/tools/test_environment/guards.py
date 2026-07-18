from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from app.core.settings import get_settings

_ALLOWED_ENVS = frozenset({"local", "dev", "development", "test", "testing"})
_CONFIRM_PHRASE = "LOCAL_TEST_RESET"
_FINGERPRINTS_PATH = Path(__file__).with_name("allowed_database_fingerprints.json")


class GuardError(RuntimeError):
    pass


def _load_fingerprints() -> dict:
    with _FINGERPRINTS_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _normalized_env() -> str:
    settings = get_settings()
    return str(getattr(settings, "ENV", "") or "").strip().lower()


def is_env_allowed() -> bool:
    return _normalized_env() in _ALLOWED_ENVS


def is_reset_flag_allowed() -> bool:
    return os.environ.get("RESET_TEST_ENVIRONMENT_ALLOWED", "").strip().lower() == "yes"


def verify_database_fingerprint(database_url: str) -> tuple[bool, str]:
    """Positive allowlist check. Unknown databases are rejected."""
    if not database_url.strip():
        return False, "DATABASE_URL is empty"

    fingerprints = _load_fingerprints()
    parsed = urlparse(database_url)
    dialect = (parsed.scheme or "").split("+", 1)[0].lower()
    if dialect not in fingerprints["allowed_dialects"]:
        return False, f"dialect '{dialect}' is not allowlisted"

    host = (parsed.hostname or "").lower()
    if host not in fingerprints["allowed_hosts"]:
        return False, f"host '{host or '(empty)'}' is not allowlisted"

    if dialect == "sqlite":
        db_path = unquote(parsed.path or "")
        prefixes = fingerprints["allowed_sqlite_path_prefixes"]
        if db_path == ":memory:" or any(
            db_path.startswith(prefix) for prefix in prefixes
        ):
            return True, "sqlite path allowlisted"
        return False, f"sqlite path '{db_path}' is not allowlisted"

    database_name = (parsed.path or "").lstrip("/").lower()
    allowed_names = {name.lower() for name in fingerprints["allowed_database_names"]}
    suffixes = fingerprints["allowed_database_suffixes"]
    if database_name in allowed_names:
        return True, "database name allowlisted"
    if any(database_name.endswith(suffix) for suffix in suffixes):
        return True, "database name suffix allowlisted"
    return False, f"database name '{database_name}' is not allowlisted"


def assert_execute_allowed(*, confirm: str | None) -> None:
    """Fail closed unless ENV, reset flag, DB fingerprint and confirm phrase match."""
    if not is_env_allowed():
        raise GuardError(
            f"ENV '{_normalized_env()}' is not allowlisted for destructive test-environment operations."
        )
    if not is_reset_flag_allowed():
        raise GuardError(
            "RESET_TEST_ENVIRONMENT_ALLOWED must be set to 'yes' for execute operations."
        )
    settings = get_settings()
    allowed, reason = verify_database_fingerprint(settings.DATABASE_URL)
    if not allowed:
        raise GuardError(f"DATABASE_URL failed positive fingerprint check: {reason}")
    if (confirm or "").strip() != _CONFIRM_PHRASE:
        raise GuardError(
            f"Missing or invalid --confirm phrase (expected '{_CONFIRM_PHRASE}')."
        )


def assert_inventory_allowed() -> None:
    """Inventory is read-only but still blocked in production-like ENV."""
    if not is_env_allowed():
        raise GuardError(
            f"ENV '{_normalized_env()}' is not allowlisted for test-environment inventory."
        )
