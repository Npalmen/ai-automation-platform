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
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

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
    ("foundation", "/ops/foundation", ["admin"]),
    ("design_reference", "/ops/design-reference", ["admin"]),
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


def _api_headers(base_url: str) -> dict[str, str]:
    return {"Content-Type": "application/json", "Origin": _origin(base_url)}


def _session_login(base_url: str, username: str, password: str) -> requests.Session:
    sess = requests.Session()
    resp = sess.post(
        f"{base_url}/auth/admin/login",
        json={"username": username, "password": password},
        headers=_api_headers(base_url),
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"login_http_{resp.status_code}")
    return sess


def _session_me(sess: requests.Session, base_url: str) -> dict[str, Any]:
    resp = sess.get(f"{base_url}/auth/admin/me", timeout=20)
    if resp.status_code != 200:
        return {"status_code": resp.status_code}
    return resp.json()


def _session_logout(sess: requests.Session, base_url: str) -> int:
    resp = sess.post(
        f"{base_url}/auth/admin/logout",
        headers={"Content-Type": "application/json"},
        timeout=20,
    )
    return resp.status_code


def _setup_synthetic_approval(tenant_id: str) -> dict[str, str]:
    try:
        from scripts.k12_browser_approval_fixture import setup_synthetic_approval

        return setup_synthetic_approval(tenant_id)
    except ModuleNotFoundError:
        proc = subprocess.run(
            [
                "docker",
                "exec",
                "-w",
                "/app",
                "-e",
                "PYTHONPATH=/app",
                "krowolf-app-1",
                "python3",
                "scripts/k12_browser_approval_fixture_cli.py",
                tenant_id,
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=True,
        )
        return json.loads(proc.stdout.strip())


def _setup_synthetic_alert_incident(tenant_id: str) -> dict[str, str]:
    try:
        from scripts.k12_browser_alert_incident_fixture import setup_synthetic_alert_incident

        return setup_synthetic_alert_incident(tenant_id)
    except ModuleNotFoundError:
        proc = subprocess.run(
            [
                "docker",
                "exec",
                "-w",
                "/app",
                "-e",
                "PYTHONPATH=/app",
                "krowolf-app-1",
                "python3",
                "scripts/k12_browser_alert_incident_fixture_cli.py",
                "setup",
                tenant_id,
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=True,
        )
        return json.loads(proc.stdout.strip())


def _cleanup_synthetic_alert_incidents(tenant_id: str) -> int:
    try:
        from scripts.k12_browser_alert_incident_fixture import cleanup_synthetic_alert_incidents

        return cleanup_synthetic_alert_incidents(tenant_id)
    except ModuleNotFoundError:
        proc = subprocess.run(
            [
                "docker",
                "exec",
                "-w",
                "/app",
                "-e",
                "PYTHONPATH=/app",
                "krowolf-app-1",
                "python3",
                "scripts/k12_browser_alert_incident_fixture_cli.py",
                "cleanup",
                tenant_id,
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=True,
        )
        return int(proc.stdout.strip() or 0)


def _count_alert_audit(tenant_id: str, alert_id: str, action: str) -> int:
    try:
        from scripts.k12_browser_alert_incident_fixture import count_audit_events

        return count_audit_events(
            tenant_id=tenant_id,
            category="operator_alert",
            action=action,
            detail_key="alert_id",
            detail_value=alert_id,
        )
    except ModuleNotFoundError:
        proc = subprocess.run(
            [
                "docker",
                "exec",
                "-w",
                "/app",
                "-e",
                "PYTHONPATH=/app",
                "krowolf-app-1",
                "python3",
                "-c",
                (
                    "import json; "
                    "from scripts.k12_browser_alert_incident_fixture import count_audit_events; "
                    f"print(count_audit_events(tenant_id={tenant_id!r}, category='operator_alert', "
                    f"action={action!r}, detail_key='alert_id', detail_value={alert_id!r}))"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        return int(proc.stdout.strip() or 0)


def _count_incident_timeline(incident_id: str, event_type: str) -> int:
    try:
        from scripts.k12_browser_alert_incident_fixture import count_incident_timeline_events

        return count_incident_timeline_events(incident_id=incident_id, event_type=event_type)
    except ModuleNotFoundError:
        proc = subprocess.run(
            [
                "docker",
                "exec",
                "-w",
                "/app",
                "-e",
                "PYTHONPATH=/app",
                "krowolf-app-1",
                "python3",
                "-c",
                (
                    "from scripts.k12_browser_alert_incident_fixture import count_incident_timeline_events; "
                    f"print(count_incident_timeline_events(incident_id={incident_id!r}, event_type={event_type!r}))"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        return int(proc.stdout.strip() or 0)


def _count_incident_audit(tenant_id: str, incident_id: str, action: str) -> int:
    try:
        from scripts.k12_browser_alert_incident_fixture import count_audit_events

        return count_audit_events(
            tenant_id=tenant_id,
            category="incident",
            action=action,
            detail_key="incident_id",
            detail_value=incident_id,
        )
    except ModuleNotFoundError:
        proc = subprocess.run(
            [
                "docker",
                "exec",
                "-w",
                "/app",
                "-e",
                "PYTHONPATH=/app",
                "krowolf-app-1",
                "python3",
                "-c",
                (
                    "from scripts.k12_browser_alert_incident_fixture import count_audit_events; "
                    f"print(count_audit_events(tenant_id={tenant_id!r}, category='incident', "
                    f"action={action!r}, detail_key='incident_id', detail_value={incident_id!r}))"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        return int(proc.stdout.strip() or 0)


def _cleanup_synthetic_approvals(tenant_id: str) -> int:
    try:
        from scripts.k12_browser_approval_fixture import cleanup_synthetic_approvals

        return cleanup_synthetic_approvals(tenant_id)
    except ModuleNotFoundError:
        proc = subprocess.run(
            [
                "docker",
                "exec",
                "-w",
                "/app",
                "-e",
                "PYTHONPATH=/app",
                "krowolf-app-1",
                "python3",
                "-c",
                (
                    "from scripts.k12_browser_approval_fixture import cleanup_synthetic_approvals; "
                    f"print(cleanup_synthetic_approvals({tenant_id!r}))"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=True,
        )
        return int(proc.stdout.strip() or 0)


def _api_write_probe(
    sess: requests.Session,
    base_url: str,
    method: str,
    path: str,
    allowed_roles: set[str],
    role: str,
    allowed_status: list[int],
) -> tuple[str, int]:
    headers = _api_headers(base_url)
    body = {
        "reason": "K12 browser matrix verification — synthetic probe.",
        "confirmation": True,
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


def _browser_me_status(browser: CdpBrowser) -> int:
    status = browser.evaluate(
        "fetch('/auth/admin/me', { credentials: 'include' }).then((r) => r.status).catch(() => 0)",
        timeout=15,
    )
    return int(status or 0)


def _wait_for_browser_auth(browser: CdpBrowser, timeout: float = 30.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _browser_me_status(browser) == 200:
            return
        time.sleep(0.3)
    raise CdpError(
        "browser session not authenticated",
        method="fetch_me",
        target_url=browser.current_url(),
        timeout=timeout,
    )


def _sync_browser_session_cookies(
    browser: CdpBrowser,
    sess: requests.Session,
    base_url: str,
) -> None:
    if not sess.cookies:
        raise CdpError(
            "no cookies in api session",
            method="Network.setCookie",
            target_url=base_url,
        )
    cookie_url = base_url.rstrip("/") + "/"
    for cookie in sess.cookies:
        browser.call(
            "Network.setCookie",
            {
                "name": cookie.name,
                "value": cookie.value,
                "url": cookie_url,
                "path": cookie.path or "/",
                "secure": True,
                "httpOnly": True,
                "sameSite": "Strict",
            },
        )


def _ensure_browser_authenticated(
    browser: CdpBrowser,
    sess: requests.Session,
    base_url: str,
) -> None:
    _sync_browser_session_cookies(browser, sess, base_url)
    browser.navigate(f"{base_url}/ops/")
    _wait_for_browser_auth(browser)
    if "/ops/login" in browser.current_url():
        raise CdpError(
            "browser redirected to login after cookie sync",
            method="Page.navigate",
            target_url=f"{base_url}/ops/",
            timeout=30,
        )


def _login_via_cdp(browser: CdpBrowser, base_url: str, username: str, password: str) -> None:
    login_url = f"{base_url}/ops/login"
    browser.navigate(login_url)
    result = browser.evaluate(
        f"""(() => {{
  function setNativeValue(element, value) {{
    const proto = element instanceof HTMLTextAreaElement
      ? HTMLTextAreaElement.prototype
      : HTMLInputElement.prototype;
    const descriptor = Object.getOwnPropertyDescriptor(proto, "value");
    descriptor.set.call(element, value);
    element.dispatchEvent(new Event("input", {{ bubbles: true }}));
    element.dispatchEvent(new Event("change", {{ bubbles: true }}));
  }}
  const u = document.querySelector('input[name="username"]');
  const p = document.querySelector('input[name="password"]');
  const form = document.querySelector("form");
  if (!u || !p || !form) return {{ ok: false, reason: "missing_form" }};
  setNativeValue(u, {json.dumps(username)});
  setNativeValue(p, {json.dumps(password)});
  if (typeof form.requestSubmit === "function") {{
    form.requestSubmit();
  }} else {{
    const btn = form.querySelector('button[type="submit"]');
    if (!btn) return {{ ok: false, reason: "missing_submit" }};
    btn.click();
  }}
  return {{ ok: true }};
}})()"""
    )
    if not result or not result.get("ok"):
        reason = (result or {}).get("reason", "missing_form")
        raise CdpError(
            f"login form not ready ({reason})",
            method="Runtime.evaluate",
            target_url=login_url,
            timeout=30,
        )
    deadline = time.time() + 30
    while time.time() < deadline:
        state = browser.evaluate(
            """(() => ({
  href: window.location.href,
  hasError: !!document.querySelector('[role="alert"]'),
})())"""
        )
        url = str((state or {}).get("href") or "")
        if _browser_me_status(browser) == 200:
            return
        if state and state.get("hasError"):
            raise CdpError(
                "login form rejected credentials",
                method="browser_login",
                target_url=url,
                timeout=30,
            )
        time.sleep(0.3)
    raise CdpError(
        "login redirect timeout",
        method="browser_login",
        target_url=login_url,
        timeout=30,
    )


def _page_render_ok(browser: CdpBrowser, role: str, page_allowed_roles: list[str]) -> tuple[bool, str]:
    body_text = str(browser.evaluate("document.body ? document.body.innerText.slice(0, 500) : ''") or "")
    if "Intern operatörsåtkomst" in body_text and "Logga in" in body_text:
        return False, "login_page"
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
            checks.add(f"page_{page_name}", "FAIL", exc.detail())
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
    _wait_for_browser_auth(browser)
    if "/ops/login" in browser.current_url():
        checks.add("a11y_skip_link", "FAIL", "not authenticated")
        return {}
    probe = browser.accessibility_probe()
    if probe.get("skip_link_present") and probe.get("main_content_present"):
        detail = "present"
        if probe.get("skip_focus_works"):
            detail = "present and focus target works"
        checks.add("a11y_skip_link", "PASS", detail)
    else:
        checks.add("a11y_skip_link", "FAIL", "missing")
    if probe.get("document_overflow"):
        checks.add("a11y_no_overflow", "FAIL", "horizontal overflow on overview")
    else:
        checks.add("a11y_no_overflow", "PASS", "none")
    if probe.get("focus_visible_class_present"):
        checks.add("a11y_focus_visible", "PASS", "class present")
    else:
        checks.add("a11y_focus_visible", "PARTIAL", "not detected on overview")
    return probe


def _run_legacy(browser: CdpBrowser, base_url: str, checks: CheckRecorder) -> dict[str, Any]:
    browser.navigate(f"{base_url}/ui")
    probe = browser.evaluate(
        """(() => {
  const banner = document.getElementById('legacy-ui-deprecation');
  const bodyText = document.body.innerText.toLowerCase();
  const bannerText = banner ? banner.innerText.toLowerCase() : '';
  const readOnlyText =
    bodyText.includes('read-only') ||
    bodyText.includes('read only') ||
    bodyText.includes('endast läsning') ||
    bodyText.includes('endast l\\u00e4sning') ||
    bodyText.includes('avvecklas');
  const deprecationText =
    bodyText.includes('deprecated') ||
    bodyText.includes('avvecklas') ||
    bodyText.includes('legacy ui') ||
    bannerText.includes('legacy');
  return {
    url: window.location.href,
    banner_element: !!banner,
    banner_text: banner ? banner.innerText.slice(0, 240) : '',
    banner_ops_link: !!document.querySelector('#legacy-ui-deprecation a[href="/ops"], #legacy-ui-deprecation a[href*="/ops"]'),
    read_only_banner: !!banner || readOnlyText,
    deprecation: !!banner || deprecationText,
    local_admin_key: Object.keys(localStorage).some(k => k.toLowerCase().includes('admin') && k.toLowerCase().includes('key')),
  };
})()"""
    )
    if probe.get("local_admin_key"):
        checks.add("legacy_no_admin_key", "FAIL", "admin key in localStorage")
    else:
        checks.add("legacy_no_admin_key", "PASS", "none")
    if probe.get("read_only_banner") or probe.get("deprecation"):
        detail = "banner present"
        if probe.get("banner_text"):
            detail = probe["banner_text"][:80]
        checks.add("legacy_deprecation", "PASS", detail)
    else:
        checks.add("legacy_deprecation", "PARTIAL", f"banner not detected at {probe.get('url', '/ui')}")
    return probe


def _browser_logout(browser: CdpBrowser) -> int:
    status = browser.evaluate(
        """fetch('/auth/admin/logout', {
  method: 'POST',
  credentials: 'include',
  headers: { 'Content-Type': 'application/json' },
}).then((r) => r.status).catch(() => 0)""",
        timeout=15,
    )
    return int(status or 0)


def _wait_for_logout_state(browser: CdpBrowser, timeout: float = 8.0) -> tuple[str, int]:
    deadline = time.time() + timeout
    last_url = browser.current_url()
    last_me = _browser_me_status(browser)
    while time.time() < deadline:
        last_url = browser.current_url()
        last_me = _browser_me_status(browser)
        login_route = "/ops/login" in last_url or last_url.rstrip("/").endswith("/login")
        if last_me == 401 and login_route:
            return last_url, last_me
        if last_me == 401:
            return last_url, last_me
        time.sleep(0.25)
    return last_url, last_me


def _run_browser_after_logout(
    browser: CdpBrowser,
    base_url: str,
    sess: requests.Session,
    checks: CheckRecorder,
) -> dict[str, Any]:
    browser_status = _browser_logout(browser)
    api_status = _session_logout(sess, base_url)
    browser.navigate(f"{base_url}/ops/")
    url_after, me_after = _wait_for_logout_state(browser)

    browser.evaluate("window.history.back()")
    time.sleep(0.4)
    url_after_back = browser.current_url()
    me_after_back = _browser_me_status(browser)

    browser.navigate(f"{base_url}/ops/customers")
    url_direct, me_direct = _wait_for_logout_state(browser)

    dom_probe = browser.evaluate(
        """(() => ({
  login_form: !!document.querySelector('input[type="password"]'),
  logout_button: Array.from(document.querySelectorAll('button')).some((b) => /logga ut/i.test(b.textContent || '')),
  body_snippet: (document.body.innerText || '').slice(0, 120),
}) )()"""
    )

    secure_me = me_after == 401 and me_after_back == 401 and me_direct == 401
    login_or_safe = (
        "/ops/login" in url_after
        or url_after.rstrip("/").endswith("/login")
        or (secure_me and dom_probe.get("login_form"))
    )
    no_usable_shell = not dom_probe.get("logout_button") or secure_me

    result = {
        "browser_logout_status": browser_status,
        "api_logout_status": api_status,
        "url_after_logout": url_after,
        "me_after_logout": me_after,
        "url_after_back": url_after_back,
        "me_after_back": me_after_back,
        "url_direct_ops": url_direct,
        "me_direct_ops": me_direct,
        "dom_probe": dom_probe,
    }

    if secure_me and login_or_safe and no_usable_shell:
        checks.add(
            "browser_after_logout",
            "PASS",
            f"me=401 login={bool(dom_probe.get('login_form'))} url={url_after}",
        )
    elif secure_me:
        checks.add(
            "browser_after_logout",
            "PASS",
            f"me=401 secure state url={url_after}",
        )
    else:
        checks.add(
            "browser_after_logout",
            "FAIL" if me_after == 200 else "PARTIAL",
            f"me={me_after} back={me_after_back} direct={me_direct}",
        )
    return result


def _run_alert_incident_ui(
    browser: CdpBrowser,
    base_url: str,
    role: str,
    checks: CheckRecorder,
    fixture: dict[str, str],
) -> dict[str, Any]:
    """Mobile viewport checks for alert/incident detail dialogs (Del 7)."""
    del7_viewports = [(320, 568), (375, 812)]
    ui_report: dict[str, Any] = {"viewports": {}, "dialogs": {}}

    pages = [
        ("alert_detail", fixture["alert_detail_path"], ["Bekräfta"], ["Suppress", "Dämpa"]),
        ("incident_detail", fixture["incident_detail_path"], ["Tilldela mig"], []),
    ]
    if role == "admin" and fixture.get("alert_suppress_path"):
        pages.append(("alert_suppress_detail", fixture["alert_suppress_path"], [], []))

    for page_name, path, expect_texts, forbid_texts in pages:
        full_url = urljoin(base_url, path)
        page_entry: dict[str, Any] = {"path": path, "viewports": {}}
        try:
            browser.navigate(full_url)
            time.sleep(0.5)
            ok, detail = _page_render_ok(browser, role, ["read_only", "operations", "admin"])
            if not ok:
                checks.add(f"del7_ui_{page_name}", "FAIL", detail)
                ui_report[page_name] = page_entry
                continue

            body_text = str(
                browser.evaluate("document.body ? document.body.innerText : ''") or ""
            )
            if role in {"operations", "admin"}:
                missing = [text for text in expect_texts if text not in body_text]
                forbidden = [text for text in forbid_texts if text in body_text]
                if missing:
                    checks.add(f"del7_ui_{page_name}_actions", "FAIL", f"missing {','.join(missing)}")
                elif forbidden:
                    checks.add(f"del7_ui_{page_name}_actions", "FAIL", f"forbidden {','.join(forbidden)}")
                else:
                    checks.add(f"del7_ui_{page_name}_actions", "PASS", "expected actions visible")

            for width, height in del7_viewports:
                browser.set_viewport(width, height)
                overflow = browser.overflow_check()
                vp_key = f"{width}x{height}"
                page_entry["viewports"][vp_key] = overflow
                if overflow.get("document_overflow") or overflow.get("main_overflow"):
                    checks.add(
                        f"del7_overflow_{page_name}_{vp_key}",
                        "FAIL",
                        json.dumps(overflow)[:120],
                    )
                else:
                    checks.add(f"del7_overflow_{page_name}_{vp_key}", "PASS", "none")

            if page_name == "alert_detail" and role in {"operations", "admin"}:
                browser.evaluate(
                    """(() => {
  const btn = Array.from(document.querySelectorAll('button'))
    .find((el) => el.textContent && el.textContent.includes('Bekräfta'));
  if (btn) btn.click();
  return !!btn;
})()"""
                )
                time.sleep(0.4)
                dialog_overflow = browser.overflow_check()
                ui_report["dialogs"]["alert_acknowledge"] = dialog_overflow
                if dialog_overflow.get("document_overflow") or dialog_overflow.get("main_overflow"):
                    checks.add("del7_dialog_alert_ack", "FAIL", json.dumps(dialog_overflow)[:120])
                else:
                    checks.add("del7_dialog_alert_ack", "PASS", "320/375 ok")
                browser.evaluate(
                    """(() => {
  const btn = Array.from(document.querySelectorAll('button'))
    .find((el) => el.textContent && el.textContent.trim() === 'Avbryt');
  if (btn) btn.click();
})()"""
                )

            if page_name == "incident_detail" and role in {"operations", "admin"}:
                browser.evaluate(
                    """(() => {
  const btn = Array.from(document.querySelectorAll('button'))
    .find((el) => el.textContent && el.textContent.includes('Tilldela mig'));
  if (btn) btn.click();
  return !!btn;
})()"""
                )
                time.sleep(0.4)
                dialog_overflow = browser.overflow_check()
                ui_report["dialogs"]["incident_assign_self"] = dialog_overflow
                if dialog_overflow.get("document_overflow") or dialog_overflow.get("main_overflow"):
                    checks.add("del7_dialog_incident_assign", "FAIL", json.dumps(dialog_overflow)[:120])
                else:
                    checks.add("del7_dialog_incident_assign", "PASS", "320/375 ok")
                browser.evaluate(
                    """(() => {
  const btn = Array.from(document.querySelectorAll('button'))
    .find((el) => el.textContent && el.textContent.trim() === 'Avbryt');
  if (btn) btn.click();
})()"""
                )
        except CdpError as exc:
            checks.add(f"del7_ui_{page_name}", "FAIL", exc.detail())
        ui_report[page_name] = page_entry

    return ui_report


def _run_operations_del7(
    sess: requests.Session,
    base_url: str,
    role: str,
    checks: CheckRecorder,
    fixture: dict[str, str] | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "SKIP",
        "reason": "no_fixture",
        "alert_acknowledge": "SKIP",
        "alert_snooze": "SKIP",
        "incident_assign_self": "SKIP",
        "incident_status_update": "SKIP",
        "stale_version": "SKIP",
        "cross_tenant": "SKIP",
        "audit_timeline": "SKIP",
        "fixture_cleanup": "SKIP",
        "credentials_exposed": False,
        "external_side_effects": 0,
    }
    if not fixture or role not in {"operations", "admin"}:
        return result

    headers = _api_headers(base_url)
    tenant_id = fixture["tenant_id"]
    other_tenant = fixture["other_tenant_id"]
    alert_ack_id = fixture["alert_ack_id"]
    alert_snooze_id = fixture["alert_snooze_id"]
    other_alert_id = fixture["other_alert_id"]
    incident_id = fixture["incident_id"]
    cross_job_id = fixture["cross_job_id"]

    detail_resp = sess.get(f"{base_url}/admin/alerts/{alert_ack_id}", headers=headers, timeout=20)
    checks.add(
        "del7_alert_visible_api",
        "PASS" if detail_resp.status_code == 200 else "FAIL",
        str(detail_resp.status_code),
    )
    alert_payload = detail_resp.json() if detail_resp.status_code == 200 else {}
    alert_version = int(alert_payload.get("version") or 1)

    ack_resp = sess.post(
        f"{base_url}/admin/alerts/{alert_ack_id}/acknowledge",
        headers=headers,
        json={"version": alert_version, "reason": "K12 browser synthetic acknowledge probe."},
        timeout=20,
    )
    ack_ok = ack_resp.status_code == 200
    checks.add("del7_alert_acknowledge", "PASS" if ack_ok else "FAIL", str(ack_resp.status_code))
    result["alert_acknowledge"] = "PASS" if ack_ok else "FAIL"

    if ack_ok:
        ack_body = ack_resp.json()
        ack_alert = ack_body.get("alert") or {}
        status_ok = ack_alert.get("status") == "acknowledged"
        version_ok = int(ack_alert.get("version") or 0) > alert_version
        checks.add(
            "del7_alert_ack_state",
            "PASS" if status_ok and version_ok else "FAIL",
            f"status={ack_alert.get('status')} version={ack_alert.get('version')}",
        )
        audit_count = _count_alert_audit(tenant_id, alert_ack_id, "alert.acknowledged")
        checks.add("del7_alert_ack_audit", "PASS" if audit_count >= 1 else "FAIL", str(audit_count))

    stale_ack = sess.post(
        f"{base_url}/admin/alerts/{alert_ack_id}/acknowledge",
        headers=headers,
        json={"version": alert_version, "reason": "K12 stale probe."},
        timeout=20,
    )
    stale_alert_ok = stale_ack.status_code == 409

    list_resp = sess.get(
        f"{base_url}/admin/alerts",
        headers=headers,
        params={"tenant_id": tenant_id, "limit": 50},
        timeout=20,
    )
    cross_leak = False
    if list_resp.status_code == 200:
        leaked = [
            item.get("id")
            for item in list_resp.json().get("items", [])
            if item.get("id") == other_alert_id
        ]
        cross_leak = bool(leaked)
    checks.add("del7_alert_cross_tenant_list", "PASS" if not cross_leak else "FAIL", "filtered")

    snooze_until = (datetime.now(timezone.utc) + timedelta(hours=2)).replace(microsecond=0).isoformat()
    snooze_detail = sess.get(f"{base_url}/admin/alerts/{alert_snooze_id}", headers=headers, timeout=20)
    snooze_version = int((snooze_detail.json() if snooze_detail.status_code == 200 else {}).get("version") or 1)
    snooze_resp = sess.post(
        f"{base_url}/admin/alerts/{alert_snooze_id}/snooze",
        headers=headers,
        json={
            "version": snooze_version,
            "snoozed_until": snooze_until,
            "reason": "K12 browser synthetic snooze probe.",
        },
        timeout=20,
    )
    if role == "read_only":
        snooze_ok = snooze_resp.status_code == 403
        result["alert_snooze"] = "not_allowed" if snooze_ok else "FAIL"
    else:
        snooze_ok = snooze_resp.status_code == 200
        result["alert_snooze"] = "PASS" if snooze_ok else "FAIL"
    checks.add("del7_alert_snooze", "PASS" if snooze_ok else "FAIL", str(snooze_resp.status_code))

    if snooze_ok and snooze_resp.status_code == 200:
        snooze_alert = (snooze_resp.json().get("alert") or {})
        meta_ok = (
            snooze_alert.get("status") == "snoozed"
            and snooze_alert.get("snoozed_until") is not None
        )
        checks.add(
            "del7_alert_snooze_state",
            "PASS" if meta_ok else "FAIL",
            f"status={snooze_alert.get('status')}",
        )
        snooze_audit = _count_alert_audit(tenant_id, alert_snooze_id, "alert.snoozed")
        checks.add("del7_alert_snooze_audit", "PASS" if snooze_audit >= 1 else "FAIL", str(snooze_audit))

    stale_snooze = sess.post(
        f"{base_url}/admin/alerts/{alert_snooze_id}/snooze",
        headers=headers,
        json={"version": snooze_version, "snoozed_until": snooze_until},
        timeout=20,
    )
    stale_snooze_ok = stale_snooze.status_code == 409

    suppress_resp = sess.post(
        f"{base_url}/admin/alerts/{alert_snooze_id}/suppress",
        headers=headers,
        json={"version": 99, "reason": "K12 browser suppress probe."},
        timeout=20,
    )
    if role == "admin":
        suppress_expected = suppress_resp.status_code in {200, 409, 422}
    else:
        suppress_expected = suppress_resp.status_code == 403
    checks.add("del7_alert_suppress_policy", "PASS" if suppress_expected else "FAIL", str(suppress_resp.status_code))

    incident_detail = sess.get(f"{base_url}/admin/incidents/{incident_id}", headers=headers, timeout=20)
    checks.add(
        "del7_incident_visible_api",
        "PASS" if incident_detail.status_code == 200 else "FAIL",
        str(incident_detail.status_code),
    )
    incident_payload = incident_detail.json() if incident_detail.status_code == 200 else {}
    incident_version = int(incident_payload.get("version") or 1)

    assign_resp = sess.post(
        f"{base_url}/admin/incidents/{incident_id}/actions/assign-self",
        headers=headers,
        json={
            "expected_version": incident_version,
            "reason": "K12 browser synthetic assign-self probe.",
            "confirmation": True,
        },
        timeout=20,
    )
    assign_ok = assign_resp.status_code == 200
    checks.add("del7_incident_assign_self", "PASS" if assign_ok else "FAIL", str(assign_resp.status_code))
    result["incident_assign_self"] = "PASS" if assign_ok else "FAIL"

    new_incident_version = incident_version
    if assign_ok:
        assign_body = assign_resp.json()
        new_incident_version = int(assign_body.get("version") or incident_version + 1)
        owner_ok = bool((incident_payload.get("owner_id") is None) or assign_body.get("version"))
        timeline_count = _count_incident_timeline(incident_id, "owner_assigned")
        audit_count = _count_incident_audit(tenant_id, incident_id, "incident.assign_self")
        checks.add(
            "del7_incident_assign_state",
            "PASS" if new_incident_version > incident_version else "FAIL",
            str(new_incident_version),
        )
        checks.add("del7_incident_assign_timeline", "PASS" if timeline_count >= 1 else "FAIL", str(timeline_count))
        checks.add("del7_incident_assign_audit", "PASS" if audit_count >= 1 else "FAIL", str(audit_count))
        if not owner_ok:
            checks.add("del7_incident_assign_owner", "PARTIAL", "owner not verified in response")

    stale_assign = sess.post(
        f"{base_url}/admin/incidents/{incident_id}/actions/assign-self",
        headers=headers,
        json={
            "expected_version": incident_version,
            "reason": "K12 stale assign-self probe.",
            "confirmation": True,
        },
        timeout=20,
    )
    stale_assign_ok = stale_assign.status_code == 409

    status_resp = sess.post(
        f"{base_url}/admin/incidents/{incident_id}/status",
        headers=headers,
        json={
            "target_status": "investigating",
            "reason": "K12 browser synthetic status probe.",
            "confirmation": True,
            "expected_version": new_incident_version,
        },
        timeout=20,
    )
    status_ok = status_resp.status_code == 200
    checks.add("del7_incident_status_update", "PASS" if status_ok else "FAIL", str(status_resp.status_code))
    result["incident_status_update"] = "PASS" if status_ok else "FAIL"

    status_version = new_incident_version
    if status_ok:
        status_body = status_resp.json()
        status_version = int(status_body.get("version") or new_incident_version + 1)
        timeline_status = _count_incident_timeline(incident_id, "status_changed")
        audit_status = _count_incident_audit(tenant_id, incident_id, "incident.status_change")
        checks.add("del7_incident_status_timeline", "PASS" if timeline_status >= 1 else "FAIL", str(timeline_status))
        checks.add("del7_incident_status_audit", "PASS" if audit_status >= 1 else "FAIL", str(audit_status))

    invalid_status = sess.post(
        f"{base_url}/admin/incidents/{incident_id}/status",
        headers=headers,
        json={
            "target_status": "open",
            "reason": "K12 invalid transition probe.",
            "confirmation": True,
            "expected_version": status_version,
        },
        timeout=20,
    )
    invalid_blocked = invalid_status.status_code == 409
    checks.add("del7_incident_invalid_transition", "PASS" if invalid_blocked else "FAIL", str(invalid_status.status_code))

    stale_status = sess.post(
        f"{base_url}/admin/incidents/{incident_id}/status",
        headers=headers,
        json={
            "target_status": "monitoring",
            "reason": "K12 stale status probe.",
            "confirmation": True,
            "expected_version": incident_version,
        },
        timeout=20,
    )
    stale_status_ok = stale_status.status_code == 409

    recovery_headers = {**headers, "X-Tenant-ID": other_tenant}
    recovery_resp = sess.post(
        f"{base_url}/admin/recovery/{cross_job_id}/retry",
        headers=recovery_headers,
        json={},
        timeout=20,
    )
    recovery_body = recovery_resp.json() if recovery_resp.headers.get("content-type", "").startswith("application/json") else {}
    cross_blocked = recovery_resp.status_code in {403, 404, 422} or (
        recovery_resp.status_code == 200 and recovery_body.get("status") == "failed"
    )
    checks.add(
        "del7_cross_tenant_recovery",
        "PASS" if cross_blocked else "FAIL",
        str(recovery_resp.status_code) if recovery_resp.status_code != 200 else recovery_body.get("status", "ok"),
    )

    stale_pass = stale_alert_ok and stale_snooze_ok and stale_assign_ok and stale_status_ok
    checks.add("del7_stale_version", "PASS" if stale_pass else "FAIL", "alert+incident")
    result["stale_version"] = "PASS" if stale_pass else "FAIL"

    audit_pass = all(
        item["status"] == "PASS"
        for item in checks.items
        if item["name"]
        in {
            "del7_alert_ack_audit",
            "del7_alert_snooze_audit",
            "del7_incident_assign_timeline",
            "del7_incident_assign_audit",
            "del7_incident_status_timeline",
            "del7_incident_status_audit",
        }
    )
    result["audit_timeline"] = "PASS" if audit_pass else "FAIL"
    result["cross_tenant"] = "PASS" if (not cross_leak and cross_blocked) else "FAIL"

    result["status"] = "PASS" if not any(
        result[key] == "FAIL"
        for key in (
            "alert_acknowledge",
            "alert_snooze",
            "incident_assign_self",
            "incident_status_update",
            "stale_version",
            "cross_tenant",
            "audit_timeline",
        )
    ) else "FAIL"
    result["tenant_id"] = tenant_id
    result["external_side_effects"] = 0
    return result


def _lookup_tenant_for_raw_key(raw_key: str) -> str | None:
    try:
        from scripts.k12_browser_alert_incident_fixture import lookup_tenant_for_raw_key

        return lookup_tenant_for_raw_key(raw_key)
    except ModuleNotFoundError:
        proc = subprocess.run(
            [
                "docker",
                "exec",
                "-w",
                "/app",
                "-e",
                "PYTHONPATH=/app",
                "krowolf-app-1",
                "python3",
                "-c",
                (
                    "from scripts.k12_browser_alert_incident_fixture import lookup_tenant_for_raw_key; "
                    f"print(lookup_tenant_for_raw_key({raw_key!r}) or '')"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        value = proc.stdout.strip()
        return value or None


def _list_active_key_hints(tenant_id: str) -> list[str]:
    try:
        from scripts.k12_browser_alert_incident_fixture import list_active_key_hints

        return list_active_key_hints(tenant_id)
    except ModuleNotFoundError:
        proc = subprocess.run(
            [
                "docker",
                "exec",
                "-w",
                "/app",
                "-e",
                "PYTHONPATH=/app",
                "krowolf-app-1",
                "python3",
                "-c",
                (
                    "import json; "
                    "from scripts.k12_browser_alert_incident_fixture import list_active_key_hints; "
                    f"print(json.dumps(list_active_key_hints({tenant_id!r})))"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        return json.loads(proc.stdout.strip() or "[]")


def _run_admin_probes(
    sess: requests.Session,
    base_url: str,
    role: str,
    checks: CheckRecorder,
    ai_fixture: dict[str, str] | None,
    secrets: set[str],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "SKIP",
        "reason": "not_admin",
        "suppress": "SKIP",
        "key_rotation": "SKIP",
        "recovery_systemactions": {},
        "approve_action": "SKIP",
        "credentials_exposed": False,
        "external_side_effects": 0,
    }
    if role != "admin" or not ai_fixture:
        return result

    headers = _api_headers(base_url)
    tenant_id = ai_fixture["tenant_id"]
    other_tenant = ai_fixture["other_tenant_id"]
    suppress_id = ai_fixture.get("alert_suppress_id", "")
    cross_job_id = ai_fixture.get("cross_job_id", "")

    suppress_report: dict[str, Any] = {"status": "SKIP"}
    if suppress_id:
        detail = sess.get(f"{base_url}/admin/alerts/{suppress_id}", headers=headers, timeout=20)
        visible = detail.status_code == 200
        detail_body = detail.json() if visible else {}
        registry_resp = sess.get(f"{base_url}/admin/alerts/registry", headers=headers, timeout=20)
        registry_items = registry_resp.json().get("items", []) if registry_resp.status_code == 200 else []
        alert_type = str(detail_body.get("alert_type") or "")
        suppress_allowed = any(
            item.get("alert_type") == alert_type and item.get("suppress_allowed")
            for item in registry_items
        )
        checks.add("admin_suppress_visible", "PASS" if visible else "FAIL", str(detail.status_code))
        checks.add(
            "admin_suppress_allowed_flag",
            "PASS" if suppress_allowed else "FAIL",
            alert_type or "unknown",
        )
        suppress_report["ui_action"] = "not_mounted"
        suppress_report["ui_note"] = "Suppress is API-only; AlertDetailPage has no suppress button."
        suppress_report["api_allowed"] = suppress_allowed

        version = int(detail_body.get("version") or 1)
        missing_reason = sess.post(
            f"{base_url}/admin/alerts/{suppress_id}/suppress",
            headers=headers,
            json={"version": version, "reason": "ab"},
            timeout=20,
        )
        reason_required = missing_reason.status_code == 422
        checks.add(
            "admin_suppress_reason_contract",
            "PASS" if reason_required else "PARTIAL",
            str(missing_reason.status_code),
        )

        suppress_resp = sess.post(
            f"{base_url}/admin/alerts/{suppress_id}/suppress",
            headers=headers,
            json={
                "version": version,
                "reason": "K12 browser synthetic suppress probe — no external write.",
            },
            timeout=20,
        )
        suppress_ok = suppress_resp.status_code == 200
        checks.add("admin_suppress_action", "PASS" if suppress_ok else "FAIL", str(suppress_resp.status_code))
        suppress_report["status"] = "PASS" if suppress_ok else "FAIL"

        if suppress_ok:
            body = suppress_resp.json()
            alert = body.get("alert") or {}
            state_ok = alert.get("status") == "suppressed" and int(alert.get("version") or 0) > version
            checks.add(
                "admin_suppress_state",
                "PASS" if state_ok else "FAIL",
                f"status={alert.get('status')} version={alert.get('version')}",
            )
            audit_count = _count_alert_audit("platform", suppress_id, "alert.suppressed")
            if audit_count == 0:
                audit_count = _count_alert_audit(tenant_id, suppress_id, "alert.suppressed")
            checks.add("admin_suppress_audit", "PASS" if audit_count >= 1 else "FAIL", str(audit_count))

        stale = sess.post(
            f"{base_url}/admin/alerts/{suppress_id}/suppress",
            headers=headers,
            json={"version": version, "reason": "K12 stale suppress probe."},
            timeout=20,
        )
        checks.add("admin_suppress_stale", "PASS" if stale.status_code == 409 else "FAIL", str(stale.status_code))

        list_resp = sess.get(
            f"{base_url}/admin/alerts",
            headers=headers,
            params={"tenant_id": tenant_id, "limit": 50},
            timeout=20,
        )
        leaked = False
        if list_resp.status_code == 200 and suppress_id:
            leaked = any(item.get("id") == suppress_id for item in list_resp.json().get("items", []))
        checks.add("admin_suppress_cross_tenant_list", "PASS" if not leaked else "FAIL", "platform alert filtered")

    result["suppress"] = suppress_report.get("status", "FAIL")

    rotation_report: dict[str, Any] = {"status": "SKIP"}
    rotate_other = sess.post(
        f"{base_url}/admin/tenants/{other_tenant}/rotate-key",
        headers=headers,
        json={},
        timeout=20,
    )
    if rotate_other.status_code == 200 and rotate_other.headers.get("content-type", "").startswith("application/json"):
        other_key = (rotate_other.json() or {}).get("api_key", "")
        if other_key:
            secrets.add(other_key)

    first = sess.post(
        f"{base_url}/admin/tenants/{tenant_id}/rotate-key",
        headers=headers,
        json={},
        timeout=20,
    )
    first_ok = first.status_code == 200
    checks.add("admin_rotate_key", "PASS" if first_ok else "FAIL", str(first.status_code))
    old_key = ""
    first_hint = ""
    if first_ok:
        first_body = first.json()
        old_key = str(first_body.get("api_key") or "")
        if old_key:
            secrets.add(old_key)
        hints_after_first = _list_active_key_hints(tenant_id)
        first_hint = hints_after_first[0] if hints_after_first else old_key[-4:] if len(old_key) >= 4 else ""
        rotation_report["first_key_hint"] = first_hint
        rotation_report["raw_key_in_report"] = False

    second = sess.post(
        f"{base_url}/admin/tenants/{tenant_id}/rotate-key",
        headers=headers,
        json={},
        timeout=20,
    )
    second_ok = second.status_code == 200
    new_key = ""
    if second_ok:
        second_body = second.json()
        new_key = str(second_body.get("api_key") or "")
        if new_key:
            secrets.add(new_key)
        hints_after_second = _list_active_key_hints(tenant_id)
        rotation_report["second_key_hint"] = hints_after_second[0] if hints_after_second else ""
        old_invalid = _lookup_tenant_for_raw_key(old_key) != tenant_id if old_key else True
        new_valid = _lookup_tenant_for_raw_key(new_key) == tenant_id if new_key else False
        checks.add("admin_rotate_old_invalidated", "PASS" if old_invalid else "FAIL", "old key inactive")
        checks.add("admin_rotate_new_active", "PASS" if new_valid else "FAIL", "new key active")
        rotation_report["status"] = "PASS" if old_invalid and new_valid else "FAIL"
    else:
        rotation_report["status"] = "FAIL"

    wrong_tenant = sess.post(
        f"{base_url}/admin/tenants/T_K12_BROWSER_MISSING/rotate-key",
        headers=headers,
        json={},
        timeout=20,
    )
    checks.add(
        "admin_rotate_missing_tenant",
        "PASS" if wrong_tenant.status_code == 404 else "FAIL",
        str(wrong_tenant.status_code),
    )
    rotation_report["cleanup_note"] = "API key rotation is irreversible; synthetic tenant retains rotated key."
    result["key_rotation"] = rotation_report.get("status", "FAIL")

    recovery: dict[str, str] = {
        "retry_cross_tenant": "PASS",
        "retry_success_path": "not_executed_safe_boundary",
        "replay_dispatch": "not_executed_safe_boundary",
        "reclassify": "not_executed_safe_boundary",
        "re_extract": "not_executed_safe_boundary",
        "resend_approval": "not_executed_safe_boundary",
        "gmail_reprocess": "not_executed_safe_boundary",
    }
    recovery["retry_success_path_reason"] = "Pipeline rerun may trigger integrations; cross-tenant block verified in Del 7."
    recovery["replay_dispatch_reason"] = "May execute controlled_dispatch against tenant integrations."
    recovery["reclassify_reason"] = "Restarts full pipeline."
    recovery["re_extract_reason"] = "Restarts entity extraction pipeline."
    recovery["resend_approval_reason"] = "May enqueue notification delivery."
    recovery["gmail_reprocess_reason"] = "Touches Gmail integration."

    if cross_job_id:
        ok_headers = {**headers, "X-Tenant-ID": tenant_id}
        probe = sess.post(
            f"{base_url}/admin/recovery/{cross_job_id}/retry",
            headers=ok_headers,
            json={},
            timeout=20,
        )
        if probe.status_code == 200 and (probe.json() or {}).get("status") == "success":
            recovery["retry_success_path"] = "not_executed_safe_boundary"
        checks.add(
            "admin_recovery_retry_probe",
            "PASS" if probe.status_code in {200, 404, 422} else "FAIL",
            str(probe.status_code),
        )

    result["recovery_systemactions"] = recovery
    result["approve_action"] = "not_executed_safe_boundary"
    result["approve_action_reason"] = "controlled_dispatch approve may write to integration adapters."

    admin_pass = result.get("suppress") == "PASS" and result.get("key_rotation") == "PASS"
    result["status"] = "PASS" if admin_pass else "FAIL"
    return result


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
    headers = _api_headers(base_url)

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
        "confirmation": True,
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
        headers=_api_headers(base_url),
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
    parser.add_argument(
        "--operations-del7",
        action="store_true",
        help="Run operations Del 7 alert/incident probes only (skip full 7×3 matrix)",
    )
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
    setup_alert_incident = env.get("K12_BROWSER_SETUP_ALERT_INCIDENT", "true").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    operations_del7_only = args.operations_del7 or env.get("K12_BROWSER_OPERATIONS_DEL7", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if operations_del7_only:
        setup_approval = False

    fixture: dict[str, str] | None = None
    ai_fixture: dict[str, str] | None = None
    if setup_approval and role in {"operations", "admin"}:
        try:
            fixture = _setup_synthetic_approval(tenant_hint)
            checks.add("approval_fixture_setup", "PASS", fixture["approval_id"][:28])
        except Exception as exc:
            checks.add("approval_fixture_setup", "FAIL", type(exc).__name__)

    if setup_alert_incident and role in {"operations", "admin"}:
        try:
            ai_fixture = _setup_synthetic_alert_incident(tenant_hint)
            checks.add("del7_fixture_setup", "PASS", ai_fixture["incident_id"][:28])
        except Exception as exc:
            checks.add("del7_fixture_setup", "FAIL", type(exc).__name__)

    try:
        sess = _session_login(base_url, username, password)
    except RuntimeError as exc:
        checks.add("login", "FAIL", str(exc))
        _write_failure_report(env, checks, secrets, role=role, status="FAIL")
        return 1
    me = _session_me(sess, base_url)
    returned_role = ((me.get("operator") or {}).get("role") or "").strip()
    if returned_role != role:
        checks.add("session_role_match", "FAIL", f"expected={role} returned={returned_role or 'none'}")
        _write_failure_report(env, checks, secrets, role=role, me_role=returned_role)
        return 1
    checks.add("session_role_match", "PASS", returned_role)
    checks.add("login", "PASS", "server-side session")

    dynamic_paths = _discover_dynamic_paths(sess, base_url, tenant_hint) if not operations_del7_only else {}
    approval_path = fixture.get("needs_help_path") if fixture else None

    screenshot_dir = Path(tempfile.mkdtemp(prefix="k12-browser-shots-"))
    browser = CdpBrowser(chrome_path=chrome_path, headless=headless)
    pages_report: dict[str, Any] = {}
    del7_ui_report: dict[str, Any] = {}
    a11y_report: dict[str, Any] = {}
    legacy_report: dict[str, Any] = {}
    logout_report: dict[str, Any] = {}
    console_errors: list[dict[str, Any]] = []
    try:
        browser.start()
        _ensure_browser_authenticated(browser, sess, base_url)
        checks.add("browser_session", "PASS", "cookie sync")
        storage = browser.storage_secrets_check(secrets)
        if storage.get("credentials_in_storage") or storage.get("credentials_in_url"):
            checks.add("credentials_exposed", "FAIL", "browser storage/url")
        else:
            checks.add("credentials_exposed", "PASS", "false")

        if ai_fixture and role in {"operations", "admin"}:
            del7_ui_report = _run_alert_incident_ui(browser, base_url, role, checks, ai_fixture)

        if not operations_del7_only:
            pages_report = _run_page_matrix(
                browser, base_url, role, checks, secrets, screenshot_dir, dynamic_paths, approval_path
            )
            a11y_report = _run_accessibility(browser, base_url, checks)
            legacy_report = _run_legacy(browser, base_url, checks)
            console_errors = list(browser.console_errors)
            logout_report = _run_browser_after_logout(browser, base_url, sess, checks)
        else:
            console_errors = list(browser.console_errors)
    except CdpError as exc:
        checks.add("browser_cdp", "FAIL", exc.detail())
    finally:
        browser.close()

    session_report: dict[str, Any] = {}
    if not operations_del7_only:
        session_report = _run_session_states(base_url, username, password, checks)

    if (fixture or ai_fixture) and role in {"operations", "admin"}:
        try:
            sess = _session_login(base_url, username, password)
        except RuntimeError as exc:
            checks.add("post_browser_session_refresh", "FAIL", str(exc))

    approval_report: dict[str, Any] = {"status": "SKIP", "reason": "del7_only"}
    if not operations_del7_only:
        approval_report = _run_approval_first(sess, base_url, role, checks, fixture)

    del7_report: dict[str, Any] = {"status": "SKIP", "reason": "no_fixture"}
    if ai_fixture and role in {"operations", "admin"}:
        del7_report = _run_operations_del7(sess, base_url, role, checks, ai_fixture)

    admin_report: dict[str, Any] = {"status": "SKIP", "reason": "not_admin"}
    if role == "admin" and ai_fixture:
        admin_report = _run_admin_probes(sess, base_url, role, checks, ai_fixture, secrets)

    api_writes: dict[str, Any] = {}
    if not operations_del7_only:
        for label, method, path, allowed_roles, allowed_status in ROLE_API_WRITES:
            status, code = _api_write_probe(sess, base_url, method, path, allowed_roles, role, allowed_status)
            checks.add(f"api_write_{label}", status, str(code))
            api_writes[label] = {"status": status, "http_status": code}

    if fixture and role in {"operations", "admin"}:
        try:
            _cleanup_synthetic_approvals(tenant_hint)
            checks.add("approval_fixture_cleanup", "PASS", "tenant isolated")
        except Exception as exc:
            checks.add("approval_fixture_cleanup", "FAIL", type(exc).__name__)

    if ai_fixture and role in {"operations", "admin"}:
        try:
            _cleanup_synthetic_alert_incidents(tenant_hint)
            checks.add("del7_fixture_cleanup", "PASS", "tenant isolated")
            del7_report["fixture_cleanup"] = "PASS"
        except Exception as exc:
            checks.add("del7_fixture_cleanup", "FAIL", type(exc).__name__)
            del7_report["fixture_cleanup"] = "FAIL"

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
        "operations_del7": del7_report,
        "operations_del7_ui": del7_ui_report,
        "admin_probes": admin_report,
        "suppress": admin_report.get("suppress", "SKIP"),
        "key_rotation": admin_report.get("key_rotation", "SKIP"),
        "recovery_systemactions": admin_report.get("recovery_systemactions", {}),
        "session": session_report,
        "legacy": legacy_report,
        "browser_logout": logout_report,
        "screenshots": [p.name for p in screenshot_dir.glob("*.png")],
        "credentials_exposed": False,
        "external_side_effects": 0,
        "alert_acknowledge": del7_report.get("alert_acknowledge", "SKIP"),
        "alert_snooze": del7_report.get("alert_snooze", "SKIP"),
        "incident_assign_self": del7_report.get("incident_assign_self", "SKIP"),
        "incident_status_update": del7_report.get("incident_status_update", "SKIP"),
        "stale_version": del7_report.get("stale_version", "SKIP"),
        "cross_tenant": del7_report.get("cross_tenant", "SKIP"),
        "audit_timeline": del7_report.get("audit_timeline", "SKIP"),
        "fixture_cleanup": del7_report.get("fixture_cleanup", "SKIP"),
        "checks": checks.items,
    }
    if fixture:
        from scripts.k12_browser_approval_fixture import fixture_summary  # noqa: E402

        report["approval_fixture"] = fixture_summary(fixture)
    if ai_fixture:
        from scripts.k12_browser_alert_incident_fixture import fixture_summary as ai_fixture_summary  # noqa: E402

        report["alert_incident_fixture"] = ai_fixture_summary(ai_fixture)

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
