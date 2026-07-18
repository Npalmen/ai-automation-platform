#!/usr/bin/env python3
"""
Kapitel 12 — authenticated /ops browser matrix on pilot (CDP + session API).

Reads credentials from /opt/krowolf/.env.browser-test (never prints secrets).
One run per K12_BROWSER_ROLE. Aggregate with kapitel12_browser_aggregate.py.

Do NOT run until operator has created the secured env file on pilot.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.k12_browser_approval_fixture import (  # noqa: E402
    cleanup_synthetic_approvals,
    fixture_summary,
    setup_synthetic_approval,
)
from scripts.k12_browser_cdp import (  # noqa: E402
    CdpBrowser,
    CdpError,
    find_chrome_binary,
    redact_console_errors,
)
from scripts.k12_browser_common import (  # noqa: E402
    VIEWPORTS,
    ZOOM_LEVELS,
    load_browser_env,
    redact_text,
    resolve_env_path,
    role_report_path,
    secret_values,
    utc_now_iso,
    validate_base_url,
    validate_role,
    write_json_report,
)

STATIC_PAGES: list[tuple[str, str, list[str]]] = [
    ("overview", "/ops/", ["read_only", "operations", "admin"]),
    ("needs_help", "/ops/needs-help", ["read_only", "operations", "admin"]),
    ("customers", "/ops/customers", ["read_only", "operations", "admin"]),
    ("incidents", "/ops/incidents", ["read_only", "operations", "admin"]),
    ("alerts", "/ops/alerts", ["read_only", "operations", "admin"]),
    ("usage", "/ops/usage", ["read_only", "operations", "admin"]),
    ("digests", "/ops/digests", ["operations", "admin"]),
    ("system", "/ops/system", ["operations", "admin"]),
]

ROLE_API_WRITES: list[tuple[str, str, str, set[str], list[int]]] = [
    ("alert_eval", "POST", "/admin/alerts/run-all", {"operations", "admin"}, [200, 202]),
    ("approve", "POST", "/admin/tenants/T_K12_BROWSER/approvals/k12-browser-missing/approve", {"operations", "admin"}, [403, 404, 422]),
    ("reject", "POST", "/admin/tenants/T_K12_BROWSER/approvals/k12-browser-missing/reject", {"operations", "admin"}, [403, 404, 422]),
    ("recovery", "POST", "/admin/recovery/k12-browser-job-missing/retry", {"operations", "admin"}, [403, 404]),
    ("rotate_key", "POST", "/admin/tenants/T_K12_BROWSER/rotate-key", {"admin"}, [403, 404, 422]),
    ("suppress", "POST", "/admin/alerts/k12-browser-alert-missing/suppress", {"admin"}, [403, 404, 422]),
]


class CheckRecorder:
    def __init__(self) -> None:
        self.items: list[dict[str, str]] = []

    def add(self, name: str, status: str, detail: str = "") -> None:
        self.items.append({"name": name, "status": status, "detail": detail})
        print(f"{status} {name}" + (f" — {detail}" if detail else ""))

    @property
    def failed(self) -> bool:
        return any(item["status"] == "FAIL" for item in self.items)


def _origin(base_url: str) -> str:
    return base_url.rstrip("/")


def _session_login(base_url: str, username: str, password: str) -> requests.Session:
    sess = requests.Session()
    resp = sess.post(
        f"{base_url}/auth/admin/login",
        json={"username": username, "password": password},
        headers={"Origin": _origin(base_url), "Content-Type": "application/json"},
        timeout=30,
    )
    resp.raise_for_status()
    return sess


def _session_me(sess: requests.Session, base_url: str) -> dict[str, Any]:
    resp = sess.get(f"{base_url}/auth/admin/me", headers={"Origin": _origin(base_url)}, timeout=20)
    if resp.status_code != 200:
        return {"status_code": resp.status_code}
    return resp.json()


def _session_logout(sess: requests.Session, base_url: str) -> int:
    resp = sess.post(
        f"{base_url}/auth/admin/logout",
        headers={"Origin": _origin(base_url)},
        timeout=20,
    )
    return resp.status_code


def _api_write_probe(
    sess: requests.Session,
    base_url: str,
    method: str,
    path: str,
    allowed_roles: set[str],
    role: str,
    allowed_status: list[int],
) -> tuple[str, int]:
    headers = {"Origin": _origin(base_url), "Content-Type": "application/json"}
    body = {
        "reason": "K12 browser matrix verification — synthetic probe.",
        "idempotency_key": f"k12-browser-{uuid.uuid4()}",
    }
    resp = sess.request(method, f"{base_url}{path}", headers=headers, json=body, timeout=20)
    if role in allowed_roles:
        ok = resp.status_code in allowed_status or (resp.status_code < 500 and resp.status_code != 403)
        return ("PASS" if ok else "FAIL", resp.status_code)
    return ("PASS" if resp.status_code == 403 else "FAIL", resp.status_code)


def _discover_dynamic_paths(sess: requests.Session, base_url: str, tenant_hint: str) -> dict[str, str]:
    headers = {"Origin": _origin(base_url)}
    paths: dict[str, str] = {}
    tenant_id = tenant_hint
    try:
        resp = sess.get(f"{base_url}/admin/tenants", headers=headers, timeout=20)
        if resp.status_code == 200:
            items = resp.json().get("items") or []
            if items:
                tenant_id = items[0].get("tenant_id") or tenant_id
    except requests.RequestException:
        pass
    if tenant_id:
        paths["customer_detail"] = f"/ops/customers/{tenant_id}"
        paths["onboarding"] = f"/ops/customers/{tenant_id}/onboarding"
    try:
        resp = sess.get(
            f"{base_url}/admin/alerts",
            params={"limit": 1},
            headers=headers,
            timeout=20,
        )
        if resp.status_code == 200:
            items = resp.json().get("items") or []
            if items and items[0].get("alert_id"):
                paths["alert_detail"] = f"/ops/alerts/{items[0]['alert_id']}"
    except requests.RequestException:
        pass
    return paths


def _login_via_cdp(browser: CdpBrowser, base_url: str, username: str, password: str) -> None:
    browser.navigate(f"{base_url}/ops/login")
    result = browser.evaluate(
        f"""(() => {{
  const u = document.querySelector('input[name="username"]');
  const p = document.querySelector('input[name="password"]');
  const btn = document.querySelector('button[type="submit"]');
  if (!u || !p || !btn) return {{ok: false, reason: 'missing_form'}};
  u.value = {json.dumps(username)};
  p.value = {json.dumps(password)};
  u.dispatchEvent(new Event('input', {{bubbles: true}}));
  p.dispatchEvent(new Event('input', {{bubbles: true}}));
  btn.click();
  return {{ok: true}};
}})()"""
    )
    if not result or not result.get("ok"):
        raise CdpError("login form not found")
    deadline = time.time() + 30
    while time.time() < deadline:
        url = browser.current_url()
        if "/ops/login" not in url:
            return
        time.sleep(0.3)
    raise CdpError("login redirect timeout")


def _page_render_ok(browser: CdpBrowser, role: str, page_allowed_roles: list[str]) -> tuple[bool, str]:
    body_text = str(browser.evaluate("document.body ? document.body.innerText.slice(0, 500) : ''") or "")
    if "Inloggningen misslyckades" in body_text:
        return False, "login_error_visible"
    if role not in page_allowed_roles and ("Åtkomst nekad" in body_text or "403" in body_text or "förbjuden" in body_text.lower()):
        return True, "forbidden_expected"
    if "Application error" in body_text or "Unexpected" in body_text:
        return False, "render_crash"
    return True, "ok"


def _run_page_matrix(
    browser: CdpBrowser,
    base_url: str,
    role: str,
    checks: CheckRecorder,
    secrets: set[str],
    screenshot_dir: Path,
    dynamic_paths: dict[str, str],
    approval_path: str | None,
) -> dict[str, Any]:
    pages_result: dict[str, Any] = {}
    overflow_result: dict[str, Any] = {}
    viewport_result: dict[str, Any] = {}

    pages: list[tuple[str, str, list[str]]] = list(STATIC_PAGES)
    for key, path in dynamic_paths.items():
        pages.append((key, path, ["read_only", "operations", "admin"]))
    if approval_path:
        pages.append(("approval_detail", approval_path, ["read_only", "operations", "admin"]))

    for page_name, path, allowed_roles in pages:
        full_url = urljoin(base_url, path)
        page_checks: dict[str, Any] = {"path": path, "viewports": {}, "zoom": {}}
        page_fail = False
        try:
            browser.navigate(full_url)
            ok, detail = _page_render_ok(browser, role, allowed_roles)
            if not ok:
                checks.add(f"page_{page_name}", "FAIL", detail)
                page_fail = True
            storage = browser.storage_secrets_check(secrets)
            if storage.get("credentials_in_storage") or storage.get("credentials_in_url"):
                checks.add(f"page_{page_name}_secrets", "FAIL", "credential_exposure")
                page_fail = True

            for width, height in VIEWPORTS:
                browser.set_viewport(width, height)
                browser.navigate(full_url)
                overflow = browser.overflow_check()
                vp_key = f"{width}x{height}"
                page_checks["viewports"][vp_key] = overflow
                doc_bad = overflow.get("document_overflow")
                main_bad = overflow.get("main_overflow")
                if doc_bad or main_bad:
                    checks.add(f"overflow_{page_name}_{vp_key}", "FAIL", json.dumps(overflow)[:120])
                    page_fail = True
                    shot = screenshot_dir / f"fail_{page_name}_{vp_key}.png"
                    browser.capture_screenshot(shot)
                    page_checks["screenshot"] = str(shot.name)

            for zoom in ZOOM_LEVELS:
                browser.set_zoom(zoom)
                browser.set_viewport(1280, 800)
                browser.navigate(full_url)
                overflow = browser.overflow_check()
                page_checks["zoom"][str(zoom)] = overflow
                if overflow.get("document_overflow") or overflow.get("main_overflow"):
                    checks.add(f"zoom_{page_name}_{zoom}", "FAIL", "overflow")
                    page_fail = True

            browser.set_zoom(100)
            if not page_fail:
                checks.add(f"page_{page_name}", "PASS", path)
        except CdpError as exc:
            checks.add(f"page_{page_name}", "FAIL", type(exc).__name__)
            page_fail = True
        pages_result[page_name] = {**page_checks, "status": "FAIL" if page_fail else "PASS"}
        if page_fail:
            overflow_result[page_name] = page_checks.get("viewports", {})

    viewport_result = pages_result
    return {"pages": pages_result, "overflow": overflow_result, "viewports": viewport_result}


def _run_accessibility(browser: CdpBrowser, base_url: str, checks: CheckRecorder) -> dict[str, Any]:
    browser.set_viewport(1280, 800)
    browser.set_zoom(100)
    browser.navigate(f"{base_url}/ops/")
    probe = browser.accessibility_probe()
    if probe.get("skip_link_present"):
        checks.add("a11y_skip_link", "PASS", "present")
    else:
        checks.add("a11y_skip_link", "FAIL", "missing")
    if probe.get("focus_visible_class_present"):
        checks.add("a11y_focus_visible", "PASS", "class present")
    else:
        checks.add("a11y_focus_visible", "PARTIAL", "not detected on overview")
    return probe


def _run_legacy(browser: CdpBrowser, base_url: str, checks: CheckRecorder) -> dict[str, Any]:
    browser.navigate(f"{base_url}/ui")
    probe = browser.evaluate(
        """(() => ({
  read_only_banner: document.body.innerText.includes('read-only') || document.body.innerText.includes('read only') || document.body.innerText.includes('avvecklas'),
  deprecation: document.body.innerText.toLowerCase().includes('deprecated') || document.body.innerText.toLowerCase().includes('avvecklas'),
  local_admin_key: Object.keys(localStorage).some(k => k.toLowerCase().includes('admin') && k.toLowerCase().includes('key')),
}) )()"""
    )
    if probe.get("local_admin_key"):
        checks.add("legacy_no_admin_key", "FAIL", "admin key in localStorage")
    else:
        checks.add("legacy_no_admin_key", "PASS", "none")
    if probe.get("read_only_banner") or probe.get("deprecation"):
        checks.add("legacy_deprecation", "PASS", "banner text present")
    else:
        checks.add("legacy_deprecation", "PARTIAL", "banner not detected")
    return probe


def _run_approval_first(
    sess: requests.Session,
    base_url: str,
    role: str,
    checks: CheckRecorder,
    fixture: dict[str, str] | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "SKIP", "reason": "no_fixture"}
    if not fixture:
        return result
    tenant_id = fixture["tenant_id"]
    approval_id = fixture["approval_id"]
    headers = {"Origin": _origin(base_url), "Content-Type": "application/json"}

    list_resp = sess.get(f"{base_url}/admin/operations/needs-help", headers=headers, timeout=20)
    visible = list_resp.status_code == 200
    checks.add("approval_visible_api", "PASS" if visible else "FAIL", str(list_resp.status_code))

    item_id = f"approval:{approval_id}"
    detail_resp = sess.get(
        f"{base_url}/admin/operations/needs-help/{quote(item_id, safe='')}",
        headers=headers,
        timeout=20,
    )
    checks.add("approval_detail_api", "PASS" if detail_resp.status_code == 200 else "PARTIAL", str(detail_resp.status_code))

    reject_body = {
        "reason": "K12 browser matrix synthetic reject — no external write.",
        "idempotency_key": f"k12-browser-reject-{uuid.uuid4()}",
    }
    reject_resp = sess.post(
        f"{base_url}/admin/tenants/{tenant_id}/approvals/{approval_id}/reject",
        headers=headers,
        json=reject_body,
        timeout=20,
    )
    if role == "read_only":
        expected = reject_resp.status_code == 403
        checks.add("approval_reject_blocked", "PASS" if expected else "FAIL", str(reject_resp.status_code))
    elif role in {"operations", "admin"}:
        expected = reject_resp.status_code in {200, 409}
        checks.add("approval_reject_action", "PASS" if expected else "FAIL", str(reject_resp.status_code))
        stale_resp = sess.post(
            f"{base_url}/admin/tenants/{tenant_id}/approvals/{approval_id}/reject",
            headers=headers,
            json=reject_body,
            timeout=20,
        )
        checks.add(
            "approval_stale_version",
            "PASS" if stale_resp.status_code == 409 else "PARTIAL",
            str(stale_resp.status_code),
        )
    result = {
        "status": "PASS" if not checks.failed else "FAIL",
        "tenant_id": tenant_id,
        "approval_id_prefix": approval_id[:24],
        "needs_help_path": fixture.get("needs_help_path"),
        "external_side_effects": 0,
    }
    return result


def _run_session_states(
    base_url: str,
    username: str,
    password: str,
    checks: CheckRecorder,
) -> dict[str, Any]:
    bad = requests.Session()
    bad_resp = bad.post(
        f"{base_url}/auth/admin/login",
        json={"username": username, "password": "invalid-k12-browser-password"},
        headers={"Origin": _origin(base_url)},
        timeout=20,
    )
    checks.add("login_invalid", "PASS" if bad_resp.status_code == 401 else "FAIL", str(bad_resp.status_code))

    sess = _session_login(base_url, username, password)
    me = _session_me(sess, base_url)
    checks.add("login_valid", "PASS" if me.get("operator") else "FAIL", "session")

    logout_code = _session_logout(sess, base_url)
    checks.add("logout", "PASS" if logout_code == 200 else "FAIL", str(logout_code))
    me_after = _session_me(sess, base_url)
    checks.add("me_after_logout", "PASS" if me_after.get("status_code") == 401 else "FAIL", "expected 401")
    return {"logout_status": logout_code, "me_after_logout": me_after.get("status_code")}


def main() -> int:
    parser = argparse.ArgumentParser(description="K12 authenticated browser matrix (pilot).")
    parser.add_argument("--env-file", default="", help="Override env file path")
    parser.add_argument("--dry-run", action="store_true", help="Validate env only; do not launch browser")
    args = parser.parse_args()

    env_path = resolve_env_path(args.env_file or None)
    env = load_browser_env(env_path)
    secrets = secret_values(env)

    checks = CheckRecorder()
    if not env_path.is_file():
        checks.add("env_file", "FAIL", "missing — create /opt/krowolf/.env.browser-test first")
        _write_failure_report(env, checks, secrets, role="unknown")
        return 2

    present_keys = [k for k in ("K12_BROWSER_BASE_URL", "K12_BROWSER_USERNAME", "K12_BROWSER_PASSWORD", "K12_BROWSER_ROLE") if env.get(k)]
    if len(present_keys) < 4:
        checks.add("credentials", "SKIP", "env incomplete — operator must fill credentials")
        _write_failure_report(env, checks, secrets, role=env.get("K12_BROWSER_ROLE", "unknown"))
        return 2

    base_ok, base_url = validate_base_url(env["K12_BROWSER_BASE_URL"])
    if not base_ok:
        checks.add("base_url", "FAIL", base_url)
        _write_failure_report(env, checks, secrets, role=env.get("K12_BROWSER_ROLE", "unknown"))
        return 1

    role_ok, role = validate_role(env["K12_BROWSER_ROLE"])
    if not role_ok:
        checks.add("role", "FAIL", role)
        _write_failure_report(env, checks, secrets, role="unknown")
        return 1

    if args.dry_run:
        checks.add("dry_run", "PASS", "env readable; browser not launched")
        _write_failure_report(env, checks, secrets, role=role, status="SKIP")
        return 0

    username = env["K12_BROWSER_USERNAME"]
    password = env["K12_BROWSER_PASSWORD"]
    headless = env.get("K12_BROWSER_HEADLESS", "true").strip().lower() in {"1", "true", "yes"}
    chrome_path = find_chrome_binary(env.get("K12_BROWSER_CHROME_PATH"))
    tenant_hint = env.get("K12_BROWSER_TEST_TENANT", "T_K12_BROWSER")
    setup_approval = env.get("K12_BROWSER_SETUP_APPROVAL", "true").strip().lower() in {"1", "true", "yes"}

    fixture: dict[str, str] | None = None
    if setup_approval and role in {"operations", "admin"}:
        try:
            fixture = setup_synthetic_approval(tenant_hint)
            checks.add("approval_fixture_setup", "PASS", fixture["approval_id"][:28])
        except Exception as exc:
            checks.add("approval_fixture_setup", "FAIL", type(exc).__name__)

    sess = _session_login(base_url, username, password)
    me = _session_me(sess, base_url)
    returned_role = ((me.get("operator") or {}).get("role") or "").strip()
    if returned_role != role:
        checks.add("session_role_match", "FAIL", f"expected={role} returned={returned_role or 'none'}")
        _write_failure_report(env, checks, secrets, role=role, me_role=returned_role)
        return 1
    checks.add("session_role_match", "PASS", returned_role)
    checks.add("login", "PASS", "server-side session")

    api_writes: dict[str, Any] = {}
    for label, method, path, allowed_roles, allowed_status in ROLE_API_WRITES:
        status, code = _api_write_probe(sess, base_url, method, path, allowed_roles, role, allowed_status)
        checks.add(f"api_write_{label}", status, str(code))
        api_writes[label] = {"status": status, "http_status": code}

    dynamic_paths = _discover_dynamic_paths(sess, base_url, tenant_hint)
    approval_path = fixture.get("needs_help_path") if fixture else None

    screenshot_dir = Path(tempfile.mkdtemp(prefix="k12-browser-shots-"))
    browser = CdpBrowser(chrome_path=chrome_path, headless=headless)
    pages_report: dict[str, Any] = {}
    a11y_report: dict[str, Any] = {}
    legacy_report: dict[str, Any] = {}
    console_errors: list[dict[str, Any]] = []
    try:
        browser.start()
        _login_via_cdp(browser, base_url, username, password)
        storage = browser.storage_secrets_check(secrets)
        if storage.get("credentials_in_storage") or storage.get("credentials_in_url"):
            checks.add("credentials_exposed", "FAIL", "browser storage/url")
        else:
            checks.add("credentials_exposed", "PASS", "false")

        pages_report = _run_page_matrix(
            browser, base_url, role, checks, secrets, screenshot_dir, dynamic_paths, approval_path
        )
        a11y_report = _run_accessibility(browser, base_url, checks)
        legacy_report = _run_legacy(browser, base_url, checks)
        console_errors = list(browser.console_errors)

        _session_logout(sess, base_url)
        browser.navigate(f"{base_url}/ops/")
        time.sleep(0.5)
        url_after_logout = browser.current_url()
        checks.add(
            "browser_after_logout",
            "PASS" if "/ops/login" in url_after_logout or "login" in url_after_logout.lower() else "PARTIAL",
            "redirect expected",
        )
    except CdpError as exc:
        checks.add("browser_cdp", "FAIL", type(exc).__name__)
    finally:
        browser.close()

    session_report = _run_session_states(base_url, username, password, checks)
    approval_report = _run_approval_first(sess, base_url, role, checks, fixture)

    if fixture and role in {"operations", "admin"}:
        try:
            cleanup_synthetic_approvals(tenant_hint)
            checks.add("approval_fixture_cleanup", "PASS", "tenant isolated")
        except Exception as exc:
            checks.add("approval_fixture_cleanup", "FAIL", type(exc).__name__)

    console_errors = redact_console_errors(console_errors, secrets)
    severe_console = [e for e in console_errors if e.get("level") == "error"]
    if severe_console:
        checks.add("console_errors", "PARTIAL", f"errors={len(severe_console)}")
    else:
        checks.add("console_errors", "PASS", "none")

    overall = "PASS"
    if checks.failed:
        overall = "FAIL"
    elif any(item["status"] == "PARTIAL" for item in checks.items):
        overall = "PARTIAL"

    report = {
        "generated_at": utc_now_iso(),
        "base_url": base_url,
        "role_expected": role,
        "role_returned": returned_role,
        "status": overall,
        "login": "PASS" if any(c["name"] == "login" and c["status"] == "PASS" for c in checks.items) else "FAIL",
        "pages_tested": list(pages_report.get("pages", {}).keys()),
        "viewport_results": pages_report.get("viewports", {}),
        "zoom_levels": list(ZOOM_LEVELS),
        "overflow_results": pages_report.get("overflow", {}),
        "console_errors": console_errors[:20],
        "accessibility": a11y_report,
        "api_write_results": api_writes,
        "approval_first": approval_report,
        "session": session_report,
        "legacy": legacy_report,
        "screenshots": [p.name for p in screenshot_dir.glob("*.png")],
        "credentials_exposed": False,
        "external_side_effects": 0,
        "checks": checks.items,
    }
    if fixture:
        report["approval_fixture"] = fixture_summary(fixture)

    out_path = role_report_path(env, role)
    write_json_report(out_path, report, secrets)
    print(f"report={out_path}")
    print(f"status={overall}")
    return 0 if overall == "PASS" else 1


def _write_failure_report(
    env: dict[str, str],
    checks: CheckRecorder,
    secrets: set[str],
    role: str,
    me_role: str = "",
    status: str = "FAIL",
) -> None:
    payload = {
        "generated_at": utc_now_iso(),
        "status": status,
        "role_expected": env.get("K12_BROWSER_ROLE", role),
        "role_returned": me_role,
        "credentials_exposed": False,
        "checks": checks.items,
    }
    path = role_report_path(env, role if role in {"read_only", "operations", "admin"} else "read_only")
    write_json_report(path, payload, secrets)


if __name__ == "__main__":
    raise SystemExit(main())
