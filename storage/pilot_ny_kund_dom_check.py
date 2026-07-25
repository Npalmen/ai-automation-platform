#!/usr/bin/env python3
"""Pilot DOM check for Ny kund button with super_admin session."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path("/opt/krowolf")
sys.path.insert(0, str(ROOT))
from scripts.k12_browser_common import load_browser_env, resolve_env_path  # noqa: E402

BASE = "https://api.krowolf.se"


def origin(url: str) -> str:
    p = urlparse(url)
    return f"{p.scheme}://{p.netloc}"


def main() -> int:
    env = load_browser_env(resolve_env_path())
    username = env.get("K12_BROWSER_USERNAME") or env.get("ADMIN_USERNAME") or "admin"
    password = env.get("K12_BROWSER_PASSWORD") or env.get("ADMIN_PASSWORD") or ""
    if not password:
        print(json.dumps({"error": "missing_password"}))
        return 1

    s = requests.Session()
    login = s.post(
        f"{BASE}/auth/admin/login",
        json={"username": username, "password": password},
        headers={"Content-Type": "application/json", "Origin": origin(BASE)},
        timeout=20,
    )
    me = s.get(f"{BASE}/auth/admin/me", timeout=20)
    me_data = me.json() if me.status_code == 200 else {}
    role = (me_data.get("operator") or {}).get("role")

    # fetch SPA shell and asset
    html = s.get(f"{BASE}/ops/customers", timeout=20)
    js_match = re.search(r"/ops/assets/(index-[^\"']+\.js)", html.text)
    js_path = js_match.group(1) if js_match else None
    js_resp = s.get(f"{BASE}/ops/assets/{js_path}", timeout=30) if js_path else None

    # check bundle strings
    js_text = js_resp.text if js_resp is not None else ""
    bundle_checks = {
        "has_ny_kund": "Ny kund" in js_text,
        "has_super_admin": "super_admin" in js_text,
        "has_customers_new": "customers/new" in js_text,
        "has_isRoleAllowed_literal": "isRoleAllowed" in js_text,
    }

    # Try CDP browser if available
    dom = {"available": False}
    try:
        from scripts.k12_browser_cdp import CdpBrowser, find_chrome_binary

        chrome = find_chrome_binary()
        if chrome:
            with CdpBrowser(chrome, headless=True) as browser:
                browser.navigate(f"{BASE}/ops/login")
                browser.wait_for_selector('input[type="password"]', timeout=10000)
                browser.fill('input[name="username"], input[autocomplete="username"]', username)
                browser.fill('input[type="password"]', password)
                browser.click('button[type="submit"]')
                browser.wait_for_navigation(timeout=15000)
                browser.navigate(f"{BASE}/ops/customers")
                browser.wait_for_selector("h1", timeout=15000)
                text = browser.evaluate("document.body.innerText")
                dom = {
                    "available": True,
                    "body_has_ny_kund": "Ny kund" in (text or ""),
                    "buttons": browser.evaluate(
                        "Array.from(document.querySelectorAll('button')).map(b => b.textContent?.trim()).filter(Boolean)"
                    ),
                    "url": browser.evaluate("location.href"),
                }
    except Exception as exc:  # noqa: BLE001
        dom = {"available": False, "error": type(exc).__name__, "detail": str(exc)[:200]}

    report = {
        "login_status": login.status_code,
        "me_status": me.status_code,
        "operator_role": role,
        "operator_id": (me_data.get("operator") or {}).get("id"),
        "authenticated": me_data.get("authenticated"),
        "html_status": html.status_code,
        "js_asset": js_path,
        "js_cache_control": js_resp.headers.get("Cache-Control") if js_resp else None,
        "html_cache_control": html.headers.get("Cache-Control"),
        "bundle_checks": bundle_checks,
        "isRoleAllowed_super_admin": role == "super_admin",
        "dom": dom,
    }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    ok = (
        role == "super_admin"
        and bundle_checks["has_ny_kund"]
        and (not dom.get("available") or dom.get("body_has_ny_kund"))
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
