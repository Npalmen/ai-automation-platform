#!/usr/bin/env python3
"""Super-admin pilot smoke — API session checks only. No external writes."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path("/opt/krowolf")
sys.path.insert(0, str(ROOT))
from scripts.k12_browser_common import load_browser_env, resolve_env_path  # noqa: E402

BASE = "https://api.krowolf.se"
TENANT = "T_NIKLAS_DEMO_001"
REPORT = ROOT / "storage/status/super_admin_role_fix_smoke.json"


def origin(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def login(username: str, password: str) -> requests.Session:
    s = requests.Session()
    r = s.post(
        f"{BASE}/auth/admin/login",
        json={"username": username, "password": password},
        headers={"Content-Type": "application/json", "Origin": origin(BASE)},
        timeout=20,
    )
    if r.status_code != 200:
        raise RuntimeError(f"login_{r.status_code}")
    return s


def get_json(s: requests.Session, path: str) -> tuple[int, dict]:
    r = s.get(f"{BASE}{path}", timeout=20)
    try:
        return r.status_code, r.json()
    except ValueError:
        return r.status_code, {}


def main() -> int:
    env = load_browser_env(resolve_env_path())
    username = env.get("K12_BROWSER_USERNAME") or env.get("ADMIN_USERNAME") or "admin"
    password = env.get("K12_BROWSER_PASSWORD") or env.get("ADMIN_PASSWORD") or ""
    if not password:
        print("FAIL missing browser password")
        return 1

    checks: list[dict] = []
    sess = login(username, password)

    code, me = get_json(sess, "/auth/admin/me")
    role = ((me.get("operator") or {}).get("role"))
    checks.append({"name": "me_super_admin", "pass": code == 200 and role == "super_admin", "detail": f"http={code} role={role}"})

    code, usage = get_json(sess, "/admin/usage/overview")
    checks.append({"name": "usage_overview", "pass": code == 200 and "summary" in usage, "detail": f"http={code}"})

    code, system = get_json(sess, "/admin/system/status")
    sha = (((system.get("runtime") or {}).get("api") or {}).get("details") or {}).get("commit_sha")
    checks.append({"name": "system_status", "pass": code == 200 and sha == "b196132ff683", "detail": f"http={code} sha={sha}"})

    code, detail = get_json(sess, f"/admin/tenants/{TENANT}/overview")
    actions = detail.get("available_actions") if isinstance(detail, dict) else None
    has_actions = isinstance(actions, list) and len(actions) > 0
    forbidden = any((a or {}).get("status") == "forbidden" for a in (actions or []) if isinstance(a, dict))
    checks.append({"name": "tenant_overview_actions", "pass": code == 200 and has_actions and not forbidden, "detail": f"http={code} actions={len(actions or [])} forbidden={forbidden}"})

    code, reg = get_json(sess, "/admin/onboarding/registries")
    checks.append({"name": "onboarding_registries", "pass": code == 200, "detail": f"http={code}"})

    code, oauth = get_json(sess, f"/admin/tenants/{TENANT}/google-oauth/status")
    checks.append({"name": "google_oauth_status", "pass": code in (200, 404), "detail": f"http={code}"})

    # idempotent fail-closed: pause automation when already paused should not 403
    r = sess.post(
        f"{BASE}/admin/tenants/{TENANT}/actions/pause",
        json={"reason": "super-admin smoke idempotent check", "idempotency_key": "super-admin-smoke-pause"},
        headers={"Content-Type": "application/json", "Origin": origin(BASE)},
        timeout=20,
    )
    checks.append({"name": "operator_pause_not_403", "pass": r.status_code != 403, "detail": f"http={r.status_code}"})

    report = {"checks": checks, "all_pass": all(c["pass"] for c in checks)}
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    for c in checks:
        print(("PASS" if c["pass"] else "FAIL"), c["name"], c["detail"])
    print("report", REPORT)
    return 0 if report["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
