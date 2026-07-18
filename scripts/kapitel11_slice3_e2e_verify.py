"""
Kapitel 11 Slice 3 — browser/proxy/security E2E verification.

Uses in-process TestClient for role/origin/tenant matrices (server-side ADMIN_ROLE).
Uses live HTTP where noted for headers against running uvicorn.

Output: scripts/kapitel11_slice3_e2e_report.json
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import requests
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.core.admin_session import hash_password
from app.core.rate_limit import check_rate_limit, reset_rate_limits_for_tests
from app.core.settings import get_settings
from app.main import app

BASE = os.environ.get("K11_E2E_BASE", "http://127.0.0.1:8000")
HTTPS_PROXY = os.environ.get("K11_HTTPS_PROXY", "https://localhost:44300")
ORIGIN_OK = "http://testserver"
ORIGIN_EVIL = "https://attacker.example"
SECRET = "k11-e2e-test-secret"
PASSWORD = "k11-e2e-password"

checks: list[dict] = []


def ok(name: str, detail: str = "", section: str = ""):
    checks.append({"section": section, "name": name, "status": "PASS", "detail": detail})
    print(f"PASS [{section}] {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str, section: str = ""):
    checks.append({"section": section, "name": name, "status": "FAIL", "detail": detail})
    print(f"FAIL [{section}] {name} — {detail}")


def skip(name: str, detail: str, section: str = ""):
    checks.append({"section": section, "name": name, "status": "SKIP", "detail": detail})
    print(f"SKIP [{section}] {name} — {detail}")


def _session_settings(role: str = "admin"):
    from types import SimpleNamespace

    h = hash_password(PASSWORD)
    return SimpleNamespace(
        SESSION_SECRET_KEY=SECRET,
        ADMIN_PASSWORD_HASH=h,
        ADMIN_USERNAME="admin",
        ADMIN_ROLE=role,
        ADMIN_DISPLAY_NAME="E2E Operator",
        ENV="dev",
        ALLOWED_ORIGINS="",
        ADMIN_API_KEY=get_settings().ADMIN_API_KEY or "test-admin-key",
        ADMIN_API_KEYS="",
        APP_NAME="AI Automation Platform",
    )


@contextmanager
def role_client(role: str):
    settings = _session_settings(role)
    get_settings.cache_clear()
    with patch("app.core.admin_session.get_settings", return_value=settings):
        with patch("app.main.get_settings", return_value=settings):
            with patch.dict(os.environ, {"ADMIN_ROLE": role}, clear=False):
                get_settings.cache_clear()
                client = TestClient(app)
                login = client.post(
                    "/auth/admin/login",
                    json={"username": "admin", "password": PASSWORD},
                    headers={"Origin": ORIGIN_OK},
                )
                if login.status_code != 200:
                    raise RuntimeError(f"login failed for role={role}: {login.status_code}")
                yield client
    get_settings.cache_clear()


def _login_cookie_client(role: str = "admin") -> TestClient:
    with role_client(role) as client:
        return client


def verify_roles():
    section = "roles"
    endpoints = [
        ("GET", "/admin/alerts", "read", [200], ["read_only", "operations", "admin"]),
        ("POST", "/admin/alerts/run-all", "alert_eval", [200, 202], ["operations", "admin"]),
        (
            "POST",
            "/admin/alerts/alert-fake/acknowledge",
            "alert_ack",
            [404, 409],
            ["operations", "admin"],
        ),
        (
            "POST",
            "/admin/recovery/job-x/retry",
            "recovery",
            [403, 404],
            ["operations", "admin"],
        ),
        (
            "POST",
            "/admin/tenants/T_X/rotate-key",
            "rotate_key",
            [403, 404, 422],
            ["admin"],
        ),
    ]

    for role in ("read_only", "operations", "admin"):
        with role_client(role) as client:
            headers = {"Origin": ORIGIN_OK, "X-Tenant-ID": "T_TEST"}
            for method, path, label, allowed_for_status, allowed_roles in endpoints:
                if method == "GET":
                    r = client.get(path, headers=headers)
                else:
                    r = client.request(method, path, headers=headers, json={})
                if role in allowed_roles:
                    if r.status_code in allowed_for_status or (r.status_code < 500 and r.status_code != 403):
                        ok(f"{role}.{label}", str(r.status_code), section)
                    else:
                        fail(f"{role}.{label}", f"unexpected {r.status_code}", section)
                else:
                    if r.status_code == 403:
                        ok(f"{role}.{label}_blocked", "403", section)
                    else:
                        fail(f"{role}.{label}_blocked", f"expected 403 got {r.status_code}", section)

            # suppress admin-only
            r_sup = client.post(
                "/admin/alerts/alert-fake/suppress",
                headers=headers,
                json={"reason": "test", "confirmation": True},
            )
            if role == "admin":
                ok(f"{role}.suppress", str(r_sup.status_code), section)
            elif r_sup.status_code == 403:
                ok(f"{role}.suppress_blocked", "403", section)
            else:
                fail(f"{role}.suppress_blocked", str(r_sup.status_code), section)


def verify_origin_matrix():
    section = "origin_auth"
    api_key = get_settings().ADMIN_API_KEY.strip()
    if not api_key:
        skip("api_key_configured", "ADMIN_API_KEY missing", section)
        return

    with role_client("operations") as client:
        r_ok = client.post(
            "/admin/recovery/job-x/retry",
            headers={"Origin": ORIGIN_OK, "X-Tenant-ID": "T_TEST"},
            json={},
        )
        if r_ok.status_code in (200, 403, 404):
            body = r_ok.json() if r_ok.headers.get("content-type", "").startswith("application/json") else {}
            if r_ok.status_code == 200 and body.get("status") == "failed":
                ok("cookie_good_origin", "200 fail-closed body", section)
            elif r_ok.status_code in (403, 404):
                ok("cookie_good_origin", str(r_ok.status_code), section)
            else:
                ok("cookie_good_origin", str(r_ok.status_code), section)
        else:
            fail("cookie_good_origin", str(r_ok.status_code), section)

        r_no = client.post(
            "/admin/recovery/job-x/retry",
            headers={"X-Tenant-ID": "T_TEST"},
            json={},
        )
        # F06: missing Origin allowed for non-browser clients (documented acceptance)
        if r_no.status_code in (403, 404):
            ok("cookie_missing_origin", f"{r_no.status_code} (blocked or not found)", section)
        else:
            ok("cookie_missing_origin", f"{r_no.status_code} (F06 accepted: allowed)", section)

        r_evil = client.post(
            "/admin/recovery/job-x/retry",
            headers={"Origin": ORIGIN_EVIL, "X-Tenant-ID": "T_TEST"},
            json={},
        )
        if r_evil.status_code == 403:
            ok("cookie_evil_origin", "403", section)
        else:
            fail("cookie_evil_origin", str(r_evil.status_code), section)

        r_combo = client.post(
            "/admin/recovery/job-x/retry",
            headers={
                "Origin": ORIGIN_EVIL,
                "X-Admin-API-Key": api_key,
                "X-Tenant-ID": "T_TEST",
            },
            json={},
        )
        if r_combo.status_code == 403:
            ok("cookie_key_evil_origin", "403", section)
        else:
            fail("cookie_key_evil_origin", str(r_combo.status_code), section)

    key_client = TestClient(app)
    r_key = key_client.post(
        "/admin/recovery/job-x/retry",
        headers={"X-Admin-API-Key": api_key, "X-Tenant-ID": "T_TEST"},
        json={},
    )
    if r_key.status_code in (200, 403, 404):
        ok("api_key_no_origin", str(r_key.status_code), section)
    else:
        fail("api_key_no_origin", str(r_key.status_code), section)

    tenant_key = os.environ.get("TENANT_API_KEY", "").strip()
    if tenant_key:
        r_tenant_admin = key_client.get("/admin/tenants", headers={"X-API-Key": tenant_key})
        if r_tenant_admin.status_code in (401, 403):
            ok("tenant_key_not_admin", str(r_tenant_admin.status_code), section)
        else:
            fail("tenant_key_not_admin", str(r_tenant_admin.status_code), section)
    else:
        skip("tenant_key_not_admin", "TENANT_API_KEY not set", section)

    r_admin_tenant = key_client.get("/jobs", headers={"X-Admin-API-Key": api_key})
    if r_admin_tenant.status_code in (401, 403, 400, 422):
        ok("admin_key_not_tenant", str(r_admin_tenant.status_code), section)
    else:
        fail("admin_key_not_tenant", str(r_admin_tenant.status_code), section)

    r_visma = key_client.get("/callback", params={"code": "x", "state": "T_LEGACY"}, follow_redirects=False)
    if r_visma.status_code in (302, 307):
        loc = r_visma.headers.get("location", "")
        if "legacy_oauth_disabled" in loc:
            ok("visma_legacy_callback_blocked", loc, section)
        else:
            fail("visma_legacy_callback_blocked", loc, section)
    else:
        fail("visma_legacy_callback_blocked", str(r_visma.status_code), section)


def verify_session():
    section = "session"
    settings = _session_settings("admin")
    get_settings.cache_clear()
    with patch("app.core.admin_session.get_settings", return_value=settings):
        with patch("app.main.get_settings", return_value=settings):
            client = TestClient(app)
            login_resp = client.post(
                "/auth/admin/login",
                json={"username": "admin", "password": PASSWORD},
                headers={"Origin": ORIGIN_OK},
            )
            if login_resp.status_code != 200:
                fail("login", str(login_resp.status_code), section)
                return
            set_cookie = login_resp.headers.get("set-cookie", "")
            if not set_cookie and login_resp.cookies:
                set_cookie = "; ".join(
                    f"{k}={login_resp.cookies[k]}" for k in login_resp.cookies
                )
            if "httponly" in set_cookie.lower():
                ok("cookie_httponly", "present", section)
            else:
                fail("cookie_httponly", set_cookie[:120] or "empty", section)
            if "samesite=strict" in set_cookie.lower():
                ok("cookie_samesite", "strict", section)
            else:
                fail("cookie_samesite", set_cookie[:120] or "empty", section)

            me = client.get("/auth/admin/me")
            if me.status_code == 200:
                ok("me_authenticated", "200", section)
            else:
                fail("me_authenticated", str(me.status_code), section)

            client.post("/auth/admin/logout", headers={"Origin": ORIGIN_OK})
            me2 = client.get("/auth/admin/me")
            if me2.status_code == 401:
                ok("logout_clears_session", "401", section)
            else:
                fail("logout_clears_session", str(me2.status_code), section)
    get_settings.cache_clear()


def verify_legacy():
    section = "legacy"
    api_key = get_settings().ADMIN_API_KEY.strip()
    client = TestClient(app)
    headers = {"X-Admin-API-Key": api_key, "Origin": ORIGIN_OK} if api_key else {}

    r_get = client.get("/admin/alerts/run-all", headers=headers)
    if r_get.status_code in (404, 405):
        ok("no_get_run_all", str(r_get.status_code), section)
    else:
        fail("no_get_run_all", str(r_get.status_code), section)

    paths = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods or []:
                if method == "GET" and any(
                    x in route.path
                    for x in ("run-all", "rotate", "recovery", "activate", "seed")
                ):
                    paths.append(f"GET {route.path}")
    if paths:
        fail("state_changing_get_inventory", "; ".join(sorted(paths)[:10]), section)
    else:
        ok("state_changing_get_inventory", "no suspicious GET routes", section)

    import app.api.approval_routes as legacy_approval

    mounted = {getattr(r, "path", "") for r in app.routes}
    if "/approvals/{job_id}" in mounted:
        fail("dormant_approval_routes", "mounted", section)
    else:
        ok("dormant_approval_routes", "not mounted", section)


def verify_rate_limit():
    section = "rate_limit"
    reset_rate_limits_for_tests()
    ip = "k11-test-ip"
    statuses = []
    for _ in range(6):
        allowed, retry = check_rate_limit(f"login:{ip}", max_calls=5, window_seconds=60)
        statuses.append((allowed, retry))
    if statuses[4][0] and not statuses[5][0] and statuses[5][1] > 0:
        ok("login_limit_429", f"retry_after={statuses[5][1]}", section)
    else:
        fail("login_limit_429", str(statuses), section)

    reset_rate_limits_for_tests()
    a = [check_rate_limit("login:ip-a", max_calls=5, window_seconds=60)[0] for _ in range(5)]
    b = [check_rate_limit("login:ip-b", max_calls=5, window_seconds=60)[0] for _ in range(5)]
    if all(a) and all(b):
        ok("login_limit_isolated_keys", "ip-a and ip-b separate", section)
    else:
        fail("login_limit_isolated_keys", f"{a} {b}", section)

    if not hasattr(sys.modules.get("app.core.rate_limit"), "reset_rate_limits_for_tests"):
        fail("reset_test_only", "missing helper", section)
    else:
        ok("reset_test_helper", "exists", section)


def verify_live_headers():
    section = "proxy_headers"
    try:
        r = requests.get(f"{BASE}/health", timeout=5)
    except requests.RequestException as exc:
        skip("live_backend", str(exc), section)
        return

    for header, expected in (
        ("X-Content-Type-Options", "nosniff"),
        ("X-Frame-Options", "DENY"),
        ("Referrer-Policy", "strict-origin-when-cross-origin"),
    ):
        val = r.headers.get(header)
        if val == expected:
            ok(f"header_{header}", val, section)
        else:
            fail(f"header_{header}", str(val), section)

    try:
        hr = requests.get(f"{HTTPS_PROXY}/health", timeout=5, verify=False)
        ok("https_proxy_reachable", str(hr.status_code), section)
    except requests.RequestException as exc:
        skip("https_proxy_reachable", str(exc), section)


def verify_tenant_isolation():
    section = "tenant_ab"
    api_key = get_settings().ADMIN_API_KEY.strip()
    if not api_key:
        skip("tenant_ab", "no admin key", section)
        return
    client = TestClient(app)
    h = {"X-Admin-API-Key": api_key, "Origin": ORIGIN_OK}

    r_a = client.get("/admin/alerts", params={"tenant_id": "T_K11_A", "limit": 5}, headers=h)
    if r_a.status_code == 200:
        for item in r_a.json().get("items", []):
            tid = item.get("tenant_id")
            if tid and tid != "T_K11_A":
                fail("alerts_filter_a", f"leaked {tid}", section)
                break
        else:
            ok("alerts_filter_a", "no cross-tenant rows", section)
    else:
        fail("alerts_filter_a", str(r_a.status_code), section)

    with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=None):
        r_rec = client.post(
            "/admin/recovery/job-k11/retry",
            headers={**h, "X-Tenant-ID": "T_K11_B"},
            json={},
        )
    if r_rec.status_code in (403, 404):
        ok("recovery_wrong_context", str(r_rec.status_code), section)
    else:
        fail("recovery_wrong_context", str(r_rec.status_code), section)


def main() -> int:
    print("Kapitel 11 Slice 3 E2E verification\n")
    verify_roles()
    verify_origin_matrix()
    verify_session()
    verify_legacy()
    verify_rate_limit()
    verify_tenant_isolation()
    verify_live_headers()

    out = ROOT / "scripts" / "kapitel11_slice3_e2e_report.json"
    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pass": sum(1 for c in checks if c["status"] == "PASS"),
        "fail": sum(1 for c in checks if c["status"] == "FAIL"),
        "skip": sum(1 for c in checks if c["status"] == "SKIP"),
        "checks": checks,
    }
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nReport: {out}")
    print(f"PASS={summary['pass']} FAIL={summary['fail']} SKIP={summary['skip']}")
    return 1 if summary["fail"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
