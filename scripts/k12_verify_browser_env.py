#!/usr/bin/env python3
"""
Verify /opt/krowolf/.env.browser-test without printing secrets.

Reports only: file exists, owner/mode, required vars set, HTTPS allowlist, role valid.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.k12_browser_common import (  # noqa: E402
    ALLOWED_ROLES,
    is_secure_env_file,
    load_browser_env,
    required_env_keys_present,
    resolve_env_path,
    validate_base_url,
    validate_role,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify browser-test env file (no secrets printed).")
    parser.add_argument(
        "--env-file",
        default="",
        help="Path to env file (default: /opt/krowolf/.env.browser-test)",
    )
    args = parser.parse_args()

    env_path = resolve_env_path(args.env_file or None)
    checks: list[tuple[str, str, str]] = []

    if not env_path.is_file():
        checks.append(("env_file_exists", "FAIL", "missing"))
        _print_report(env_path, checks)
        return 1
    checks.append(("env_file_exists", "PASS", str(env_path)))

    secure, secure_detail = is_secure_env_file(env_path)
    checks.append(("env_file_permissions", "PASS" if secure else "FAIL", secure_detail))

    env = load_browser_env(env_path)
    present, missing = required_env_keys_present(env)
    checks.append(
        (
            "required_variables",
            "PASS" if present else "FAIL",
            "all_set" if present else f"missing:{','.join(missing)}",
        )
    )

    base_url = env.get("K12_BROWSER_BASE_URL", "")
    base_ok, base_detail = validate_base_url(base_url)
    checks.append(("base_url_https_allowlist", "PASS" if base_ok else "FAIL", base_detail))

    role = env.get("K12_BROWSER_ROLE", "")
    role_ok, role_detail = validate_role(role)
    checks.append(("role_value", "PASS" if role_ok else "FAIL", role_detail))

    headless = env.get("K12_BROWSER_HEADLESS", "true").strip().lower()
    if headless in {"true", "false", "1", "0", "yes", "no"}:
        checks.append(("headless_flag", "PASS", headless))
    else:
        checks.append(("headless_flag", "FAIL", "invalid"))

    report_path = env.get("K12_BROWSER_REPORT_PATH", "").strip()
    if report_path:
        checks.append(("report_path_set", "PASS", "configured"))
    else:
        checks.append(("report_path_set", "FAIL", "missing"))

    status = "PASS" if all(item[1] == "PASS" for item in checks) else "FAIL"
    _print_report(env_path, checks, status=status)
    return 0 if status == "PASS" else 1


def _print_report(env_path: Path, checks: list[tuple[str, str, str]], status: str = "FAIL") -> None:
    print(f"env_path={env_path}")
    print(f"allowed_roles={','.join(sorted(ALLOWED_ROLES))}")
    for name, result, detail in checks:
        print(f"{result} {name} — {detail}")
    print(f"OVERALL {status}")


if __name__ == "__main__":
    raise SystemExit(main())
