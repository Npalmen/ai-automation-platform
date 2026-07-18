"""
Shared helpers for Kapitel 12 authenticated browser matrix.

Never log or persist credentials, cookies, or customer payloads.
"""

from __future__ import annotations

import json
import os
import re
import stat
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

ALLOWED_BASE_URLS = frozenset({"https://api.krowolf.se"})
ALLOWED_ROLES = frozenset({"read_only", "operations", "admin"})

DEFAULT_ENV_PATHS = (
    Path("/opt/krowolf/.env.browser-test"),
    ROOT / "scripts" / ".env.browser-test",
)

VIEWPORTS: list[tuple[int, int]] = [
    (320, 568),
    (375, 812),
    (768, 1024),
    (1024, 768),
    (1280, 800),
    (1366, 768),
    (1440, 900),
]

ZOOM_LEVELS = (125, 150, 200)

ROLE_REPORT_NAMES = {
    "read_only": "k12_browser_read_only_report.json",
    "operations": "k12_browser_operations_report.json",
    "admin": "k12_browser_admin_report.json",
}

AGGREGATE_REPORT_NAME = "kapitel12_browser_report.json"


def resolve_env_path(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit)
    for candidate in DEFAULT_ENV_PATHS:
        if candidate.is_file():
            return candidate
    return DEFAULT_ENV_PATHS[0]


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_browser_env(env_path: Path | None = None) -> dict[str, str]:
    path = env_path or resolve_env_path()
    if not path.is_file():
        return {}
    try:
        from dotenv import dotenv_values

        values = {k: (v or "").strip() for k, v in dotenv_values(path).items()}
    except ImportError:
        values = _parse_env_file(path)
    for key, value in os.environ.items():
        if key.startswith("K12_BROWSER_") and value.strip():
            values[key] = value.strip()
    return values


def secret_values(env: dict[str, str]) -> set[str]:
    out: set[str] = set()
    for key in ("K12_BROWSER_USERNAME", "K12_BROWSER_PASSWORD"):
        value = env.get(key, "").strip()
        if value:
            out.add(value)
    return out


def redact_text(text: str, secrets: set[str]) -> str:
    redacted = text
    for value in sorted(secrets, key=len, reverse=True):
        if value:
            redacted = redacted.replace(value, "[REDACTED]")
    redacted = re.sub(
        r'"(password|token|secret|api_key|authorization)"\s*:\s*"[^"]*"',
        r'"\1":"[REDACTED]"',
        redacted,
        flags=re.IGNORECASE,
    )
    return redacted


def role_report_path(env: dict[str, str], role: str) -> Path:
    explicit = env.get("K12_BROWSER_REPORT_PATH", "").strip()
    if explicit:
        path = Path(explicit)
        if path.name == "k12_browser_pilot_report.json":
            return path.with_name(ROLE_REPORT_NAMES.get(role, path.name))
        return path
    status_dir = Path("/opt/krowolf/storage/status")
    if status_dir.is_dir():
        return status_dir / ROLE_REPORT_NAMES[role]
    return ROOT / "scripts" / ROLE_REPORT_NAMES[role]


def aggregate_report_path() -> Path:
    status_dir = Path("/opt/krowolf/storage/status")
    if status_dir.is_dir():
        return status_dir / AGGREGATE_REPORT_NAME
    return ROOT / "scripts" / AGGREGATE_REPORT_NAME


def utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def file_mode_owner(path: Path) -> tuple[int, int, int]:
    st = path.stat()
    return st.st_mode & 0o777, st.st_uid, st.st_gid


def is_secure_env_file(path: Path) -> tuple[bool, str]:
    if not path.is_file():
        return False, "missing"
    mode, uid, gid = file_mode_owner(path)
    if mode != 0o600:
        return False, f"mode_{oct(mode)}"
    if uid != 0 or gid != 0:
        return False, f"owner_{uid}:{gid}"
    return True, "ok"


def validate_base_url(url: str) -> tuple[bool, str]:
    normalized = url.rstrip("/")
    if not normalized.startswith("https://"):
        return False, "not_https"
    if normalized not in ALLOWED_BASE_URLS:
        return False, "not_allowlisted"
    return True, normalized


def validate_role(role: str) -> tuple[bool, str]:
    role = role.strip()
    if role not in ALLOWED_ROLES:
        return False, "invalid_role"
    return True, role


def required_env_keys_present(env: dict[str, str]) -> tuple[bool, list[str]]:
    missing = [
        key
        for key in (
            "K12_BROWSER_BASE_URL",
            "K12_BROWSER_USERNAME",
            "K12_BROWSER_PASSWORD",
            "K12_BROWSER_ROLE",
        )
        if not env.get(key, "").strip()
    ]
    return not missing, missing


def write_json_report(path: Path, payload: dict[str, Any], secrets: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, ensure_ascii=False)
    text = redact_text(text, secrets)
    path.write_text(text, encoding="utf-8")


def aggregate_role_reports(report_paths: dict[str, Path]) -> dict[str, Any]:
    roles: dict[str, Any] = {}
    all_pass = True
    for role, path in report_paths.items():
        if not path.is_file():
            roles[role] = {"status": "MISSING", "path": str(path)}
            all_pass = False
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        roles[role] = {
            "status": data.get("status", "UNKNOWN"),
            "path": str(path),
            "role_expected": data.get("role_expected"),
            "role_returned": data.get("role_returned"),
        }
        if data.get("status") != "PASS":
            all_pass = False
    return {
        "generated_at": utc_now_iso(),
        "status": "PASS" if all_pass else "FAIL",
        "roles": roles,
        "credentials_exposed": False,
    }
