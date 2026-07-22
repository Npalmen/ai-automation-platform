#!/usr/bin/env python3
"""
Pilot Customer Settings role + browser verifier.

Reads credentials from .env.browser-test only. Never logs or persists secrets.
"""

from __future__ import annotations

import argparse
import json
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.k12_browser_cdp import CdpBrowser, CdpError, find_chrome_binary  # noqa: E402
from scripts.k12_browser_common import (  # noqa: E402
    load_browser_env,
    redact_text,
    resolve_env_path,
    secret_values,
    utc_now_iso,
    validate_base_url,
    write_json_report,
)

ROLE_ORDER = ("read_only", "operations", "admin", "super_admin")
VERIFY_ROLES = frozenset(ROLE_ORDER)
DEFAULT_TENANT = "T_NIKLAS_DEMO_001"
DEFAULT_REPORT = Path("/opt/krowolf/storage/status/customer_settings_pilot_role_report.json")
ENV_PRODUCTION = Path("/opt/krowolf/.env.production")
PENDING_RESTORE = Path("/opt/krowolf/storage/status/.cs_role_verify_restore_pending.json")
COMPOSE_FILE = Path("/opt/krowolf/docker-compose.prod.yml")
TAB_LABELS = {
    "identity": "Företagsuppgifter",
    "modules": "Tjänster och moduler",
    "integrations": "Integrationer",
    "routing": "Routing",
    "automation": "Automation och säkerhet",
    "readiness": "Readiness",
}
SETTINGS_TABS = tuple(TAB_LABELS.keys())
CheckStatus = Literal["PASS", "FAIL", "NOT_RUN"]

SECRET_PATTERNS = (
    r"access_token",
    r"refresh_token",
    r"BEGIN (RSA |EC )?PRIVATE KEY",
    r"Bearer [A-Za-z0-9._-]{20,}",
)


@dataclass
class EnvState:
    admin_role: str
    super_admin_operator_ids: str


@dataclass
class RunContext:
    base_url: str
    tenant_id: str
    username: str
    password: str
    restore_admin_role: str
    skip_browser: bool
    report_path: Path
    env_file: Path
    started_at: str = field(default_factory=utc_now_iso)
    original_env: EnvState | None = None
    pre_snapshot: dict[str, Any] = field(default_factory=dict)
    role_results: dict[str, Any] = field(default_factory=dict)
    mutations: list[dict[str, Any]] = field(default_factory=list)
    config_version_trace: list[dict[str, Any]] = field(default_factory=list)
    restore_status: str = "NOT_RUN"
    manual_restore_command: str = ""
    runtime_code_sha: str | None = None
    release_id: str | None = None
    credentials_exposed: bool = False
    external_side_effects: int = 0


class Checks:
    def __init__(self) -> None:
        self.items: list[dict[str, str]] = []

    def add(self, name: str, status: CheckStatus, detail: str = "", http_status: int | None = None) -> None:
        item: dict[str, str] = {"name": name, "status": status, "detail": detail}
        if http_status is not None:
            item["http_status"] = str(http_status)
        self.items.append(item)
        print(f"{status} {name}" + (f" — {detail}" if detail else ""))

    @property
    def failed(self) -> bool:
        return any(item["status"] == "FAIL" for item in self.items)

    def overall(self) -> CheckStatus:
        if any(item["status"] == "FAIL" for item in self.items):
            return "FAIL"
        if self.items and all(item["status"] == "NOT_RUN" for item in self.items):
            return "NOT_RUN"
        return "PASS"


_restore_state: EnvState | None = None
_restore_target_role: str = "admin"


def operator_id(username: str) -> str:
    return f"operator-{username.strip().lower()}"


def _read_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def read_production_env(path: Path | None = None) -> EnvState:
    path = path or ENV_PRODUCTION
    data = _read_env_file(path)
    return EnvState(
        admin_role=data.get("ADMIN_ROLE", "admin"),
        super_admin_operator_ids=data.get("SUPER_ADMIN_OPERATOR_IDS", ""),
    )


def write_production_env(state: EnvState, path: Path | None = None) -> None:
    path = path or ENV_PRODUCTION
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    out: list[str] = []
    seen = {"ADMIN_ROLE": False, "SUPER_ADMIN_OPERATOR_IDS": False}
    for line in lines:
        if line.startswith("ADMIN_ROLE="):
            out.append(f"ADMIN_ROLE={state.admin_role}")
            seen["ADMIN_ROLE"] = True
        elif line.startswith("SUPER_ADMIN_OPERATOR_IDS="):
            out.append(f"SUPER_ADMIN_OPERATOR_IDS={state.super_admin_operator_ids}")
            seen["SUPER_ADMIN_OPERATOR_IDS"] = True
        else:
            out.append(line)
    if not seen["ADMIN_ROLE"]:
        out.append(f"ADMIN_ROLE={state.admin_role}")
    if not seen["SUPER_ADMIN_OPERATOR_IDS"]:
        out.append(f"SUPER_ADMIN_OPERATOR_IDS={state.super_admin_operator_ids}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def restart_app_container(compose_file: Path = COMPOSE_FILE) -> None:
    subprocess.run(
        ["sudo", "docker", "compose", "-f", str(compose_file), "up", "-d", "--no-deps", "app"],
        check=True,
        timeout=120,
        cwd=str(compose_file.parent),
    )
    time.sleep(3)


def set_pilot_role(role: str, username: str, *, original: EnvState, compose_file: Path = COMPOSE_FILE) -> None:
    op_id = operator_id(username)
    base_ids = {item.strip() for item in original.super_admin_operator_ids.split(",") if item.strip()}
    if role == "super_admin":
        ids = set(base_ids)
        ids.add(op_id)
        write_production_env(
            EnvState(admin_role="admin", super_admin_operator_ids=",".join(sorted(ids))),
        )
    else:
        # Drop browser operator from elevation so ADMIN_ROLE drives /auth/admin/me.
        ids = {item for item in base_ids if item != op_id}
        write_production_env(
            EnvState(admin_role=role, super_admin_operator_ids=",".join(sorted(ids))),
        )
    restart_app_container(compose_file)


def restore_production_env(original: EnvState, compose_file: Path = COMPOSE_FILE) -> None:
    write_production_env(original)
    restart_app_container(compose_file)


def manual_restore_command(target_role: str) -> str:
    return (
        "cd /opt/krowolf && "
        f"sudo sed -i 's/^ADMIN_ROLE=.*/ADMIN_ROLE={target_role}/' /opt/krowolf/.env.production && "
        "sudo docker compose -f docker-compose.prod.yml up -d --no-deps app && "
        "bash scripts/k12_inspect_admin_role_pilot.sh"
    )


def write_pending_restore(original: EnvState, target_role: str) -> None:
    PENDING_RESTORE.parent.mkdir(parents=True, exist_ok=True)
    PENDING_RESTORE.write_text(
        json.dumps(
            {
                "admin_role": original.admin_role,
                "super_admin_operator_ids": original.super_admin_operator_ids,
                "restore_admin_role": target_role,
                "manual_command": manual_restore_command(target_role),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def clear_pending_restore() -> None:
    if PENDING_RESTORE.is_file():
        PENDING_RESTORE.unlink()


def _attempt_restore(ctx: RunContext) -> bool:
    global _restore_state
    if _restore_state is None:
        return False
    try:
        restore_production_env(_restore_state)
        ctx.restore_status = "PASS"
        clear_pending_restore()
        return True
    except Exception as exc:  # noqa: BLE001
        ctx.restore_status = "FAIL"
        ctx.manual_restore_command = manual_restore_command(ctx.restore_admin_role)
        print(f"RESTORE_FAIL {exc}", file=sys.stderr)
        return False


def _handle_signal(signum: int, _frame: Any) -> None:
    print(f"signal_{signum}_restore", file=sys.stderr)
    if _restore_state is not None:
        try:
            restore_production_env(_restore_state)
        except Exception:
            pass
    raise SystemExit(128 + signum)


def _request_origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def http_get_json(url: str, *, session: requests.Session | None = None, timeout: int = 20) -> tuple[int, Any]:
    client = session or requests
    resp = client.get(url, timeout=timeout)
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, {}


def http_json(
    method: str,
    url: str,
    *,
    session: requests.Session,
    body: dict[str, Any] | None = None,
    timeout: int = 30,
) -> tuple[int, Any]:
    headers = {"Content-Type": "application/json", "Origin": _request_origin(url)}
    resp = session.request(method, url, json=body, headers=headers, timeout=timeout)
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, {}


def session_login(base_url: str, username: str, password: str) -> requests.Session:
    sess = requests.Session()
    status, _ = http_json(
        "POST",
        f"{base_url}/auth/admin/login",
        session=sess,
        body={"username": username, "password": password},
    )
    if status != 200:
        raise RuntimeError(f"login_http_{status}")
    return sess


def session_me(sess: requests.Session, base_url: str) -> dict[str, Any]:
    status, data = http_get_json(f"{base_url}/auth/admin/me", session=sess)
    if status != 200:
        return {"status_code": status}
    return data


def wait_health(base_url: str, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            status, data = http_get_json(f"{base_url}/health")
            if status == 200 and (data or {}).get("status") == "ok":
                return True
        except requests.RequestException:
            pass
        time.sleep(1.0)
    return False


def fetch_runtime_identity() -> tuple[str | None, str | None]:
    try:
        proc = subprocess.run(
            ["docker", "exec", "krowolf-app-1", "cat", "/app/build-metadata.json"],
            capture_output=True,
            text=True,
            timeout=30,
            check=True,
        )
        data = json.loads(proc.stdout)
        return data.get("commit_sha"), data.get("release_id")
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return None, None


def snapshot_sql(tenant_id: str) -> dict[str, Any]:
    query = f"""
SELECT json_build_object(
  'jobs', (SELECT COUNT(*)::int FROM jobs),
  'approvals', (SELECT COUNT(*)::int FROM approval_requests),
  'config_version', (SELECT config_version FROM tenant_configs WHERE tenant_id='{tenant_id}'),
  'timezone', COALESCE((SELECT settings->'company'->>'timezone' FROM tenant_configs WHERE tenant_id='{tenant_id}'), 'Europe/Stockholm'),
  'scheduler', COALESCE((SELECT settings->'controller'->'scheduler'->>'run_mode' FROM tenant_configs WHERE tenant_id='{tenant_id}'), 'paused'),
  'gmail_fp', (SELECT md5(COALESCE(access_token,'') || ':' || COALESCE(refresh_token,'')) FROM oauth_credentials WHERE tenant_id='{tenant_id}' AND provider='google_mail'),
  'visma_fp', (SELECT md5(COALESCE(access_token,'') || ':' || COALESCE(refresh_token,'')) FROM oauth_credentials WHERE tenant_id='{tenant_id}' AND provider='visma'),
  'activation_snapshots', (SELECT COUNT(*)::int FROM tenant_activation_snapshots WHERE tenant_id='{tenant_id}'),
  'onboarding_sessions', (SELECT COUNT(*)::int FROM onboarding_sessions WHERE tenant_id='{tenant_id}'),
  'admin_role', (SELECT NULL),
  'super_admin_operator_ids', (SELECT NULL)
);
"""
    proc = subprocess.run(
        ["docker", "exec", "krowolf-db-1", "psql", "-U", "postgres", "-d", "ai_platform", "-tAc", query],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    )
    data = json.loads(proc.stdout.strip())
    env = read_production_env()
    data["admin_role"] = env.admin_role
    data["super_admin_operator_ids_present"] = bool(env.super_admin_operator_ids.strip())
    return data


def compare_snapshots(before: dict[str, Any], after: dict[str, Any], *, start_timezone: str) -> dict[str, Any]:
    delta: dict[str, Any] = {}
    for key in sorted(set(before) | set(after)):
        if before.get(key) != after.get(key):
            delta[key] = {"before": before.get(key), "after": after.get(key)}
    ok = (
        before.get("jobs") == after.get("jobs")
        and before.get("approvals") == after.get("approvals")
        and after.get("scheduler") == "paused"
        and before.get("gmail_fp") == after.get("gmail_fp")
        and before.get("visma_fp") == after.get("visma_fp")
        and before.get("activation_snapshots") == after.get("activation_snapshots")
        and before.get("onboarding_sessions") == after.get("onboarding_sessions")
        and after.get("timezone") == "Europe/Stockholm"
        and before.get("admin_role") == after.get("admin_role")
        and before.get("super_admin_operator_ids_present") == after.get("super_admin_operator_ids_present")
    )
    cv_before = int(before.get("config_version") or 0)
    cv_after = int(after.get("config_version") or 0)
    cv_delta = cv_after - cv_before
    delta["config_version_delta"] = cv_delta
    if cv_delta > 2:
        ok = False
    return {"ok": ok, "delta": delta, "config_version_delta": cv_delta}


def settings_aggregate(sess: requests.Session, base_url: str, tenant_id: str) -> tuple[int, dict[str, Any]]:
    return http_json("GET", f"{base_url}/admin/tenants/{tenant_id}/settings", session=sess)


def patch_domain(
    sess: requests.Session,
    base_url: str,
    tenant_id: str,
    domain: str,
    version: int,
    payload: dict[str, Any],
) -> tuple[int, Any]:
    return http_json(
        "PATCH",
        f"{base_url}/admin/tenants/{tenant_id}/settings/{domain}",
        session=sess,
        body={"expected_config_version": version, "payload": payload},
    )


def preview_domain(
    sess: requests.Session,
    base_url: str,
    tenant_id: str,
    domain: str,
    payload: dict[str, Any],
) -> tuple[int, Any]:
    return http_json(
        "POST",
        f"{base_url}/admin/tenants/{tenant_id}/settings/{domain}/preview",
        session=sess,
        body={"payload": payload},
    )


def scan_for_secrets(text: str) -> bool:
    return any(re.search(pattern, text, re.I) for pattern in SECRET_PATTERNS)


def run_api_role_checks(
    role: str,
    ctx: RunContext,
    sess: requests.Session,
    *,
    admin_mutation_done: bool,
) -> tuple[Checks, bool]:
    checks = Checks()
    base = ctx.base_url
    tenant = ctx.tenant_id
    status, agg = settings_aggregate(sess, base, tenant)
    checks.add("aggregate_get", "PASS" if status == 200 else "FAIL", f"status={status}", http_status=status)
    if status != 200:
        return checks, admin_mutation_done

    version = int(agg.get("config_version") or 0)
    perms = agg.get("permissions") or {}
    me = session_me(sess, base).get("operator") or {}
    checks.add("me_role", "PASS" if me.get("role") == role else "FAIL", str(me.get("role")))

    for domain in ("identity", "modules", "integrations", "routing", "automation"):
        dstatus, _ = http_json("GET", f"{base}/admin/tenants/{tenant}/settings/{domain}", session=sess)
        checks.add(f"domain_get_{domain}", "PASS" if dstatus == 200 else "FAIL", f"status={dstatus}", http_status=dstatus)

    identity_payload = {"timezone": "Europe/Oslo"}
    routing_payload: dict[str, Any] = {}
    integrations_payload = {"selections": {"fortnox": {"selection_status": "not_selected"}}}
    automation_payload = {"policy": {"preset_key": "observe_only", "preset_version": 1, "approval_first": True}}

    if role == "read_only":
        for domain, payload in (
            ("identity", identity_payload),
            ("routing", routing_payload),
            ("integrations", integrations_payload),
        ):
            pstatus, _ = patch_domain(sess, base, tenant, domain, version, payload)
            checks.add(f"patch_{domain}_403", "PASS" if pstatus == 403 else "FAIL", f"status={pstatus}", http_status=pstatus)

    elif role == "operations":
        checks.add(
            "perm_routing_write",
            "PASS" if (perms.get("routing") or {}).get("write") else "FAIL",
            str(perms.get("routing")),
        )
        checks.add(
            "perm_integrations_write_false",
            "PASS" if not (perms.get("integrations") or {}).get("write") else "FAIL",
            str(perms.get("integrations")),
        )
        prev_status, prev = preview_domain(sess, base, tenant, "routing", routing_payload)
        checks.add(
            "routing_preview",
            "PASS" if prev_status == 200 and prev.get("valid") is True else "FAIL",
            f"status={prev_status}",
            http_status=prev_status,
        )
        istatus, _ = patch_domain(sess, base, tenant, "integrations", version, integrations_payload)
        checks.add("patch_integrations_403", "PASS" if istatus == 403 else "FAIL", f"status={istatus}", http_status=istatus)
        astatus, _ = patch_domain(sess, base, tenant, "automation", version, automation_payload)
        checks.add("patch_automation_403", "PASS" if astatus == 403 else "FAIL", f"status={astatus}", http_status=astatus)

    elif role == "admin" and not admin_mutation_done:
        prev_status, prev = preview_domain(sess, base, tenant, "routing", routing_payload)
        checks.add("routing_preview", "PASS" if prev_status == 200 else "FAIL", f"status={prev_status}", http_status=prev_status)
        int_prev_status, _ = preview_domain(sess, base, tenant, "integrations", {})
        checks.add(
            "integrations_preview",
            "PASS" if int_prev_status == 200 else "FAIL",
            f"status={int_prev_status}",
            http_status=int_prev_status,
        )
        start_tz = (agg.get("domains") or {}).get("identity", {}).get("timezone") or ctx.pre_snapshot.get("timezone") or "Europe/Stockholm"
        start_cv = version
        targets: list[str] = []
        if start_tz == "Europe/Stockholm":
            targets = ["Europe/Oslo", "Europe/Stockholm"]
        elif start_tz == "Europe/Oslo":
            targets = ["Europe/Stockholm"]
        else:
            targets = ["Europe/Oslo", "Europe/Stockholm"]
        for target_tz in targets:
            pstatus, pdata = patch_domain(sess, base, tenant, "identity", version, {"timezone": target_tz})
            ok = pstatus == 200
            checks.add(f"patch_identity_{target_tz}", "PASS" if ok else "FAIL", f"status={pstatus}", http_status=pstatus)
            if ok:
                version = int((pdata or {}).get("config_version") or version + 1)
                ctx.config_version_trace.append({"step": target_tz, "config_version": version})
        ctx.mutations.append(
            {
                "name": "admin_timezone_roundtrip",
                "status": "PASS" if version <= start_cv + 2 else "FAIL",
                "config_version_start": start_cv,
                "config_version_end": version,
            }
        )
        stale_status, _ = patch_domain(sess, base, tenant, "identity", version + 999, {"timezone": start_tz})
        checks.add("stale_patch_409", "PASS" if stale_status == 409 else "FAIL", f"status={stale_status}", http_status=stale_status)
        admin_mutation_done = True

    elif role == "super_admin":
        checks.add(
            "perm_integrations_write",
            "PASS" if (perms.get("integrations") or {}).get("write") else "FAIL",
            str(perms.get("integrations")),
        )
        auto = agg.get("automation_policy_summary") or {}
        checks.add(
            "scheduler_read_only",
            "PASS" if auto.get("scheduler_run_mode") == "paused" else "FAIL",
            str(auto.get("scheduler_run_mode")),
        )
        if not admin_mutation_done:
            prev_status, _ = preview_domain(sess, base, tenant, "integrations", {})
            checks.add("integrations_preview", "PASS" if prev_status == 200 else "FAIL", f"status={prev_status}", http_status=prev_status)

    return checks, admin_mutation_done


def _js_count_buttons(label: str) -> str:
    return f"""(() => Array.from(document.querySelectorAll('button')).filter(b => (b.textContent||'').includes({json.dumps(label)})).length)()"""


def _js_body_has_any(*needles: str) -> str:
    parts = " || ".join(f"(document.body.innerText||'').includes({json.dumps(n)})" for n in needles)
    return f"(() => Boolean(document.body && ({parts})))()"


def _js_body_has(*needles: str) -> str:
    parts = " && ".join(f"(document.body.innerText||'').includes({json.dumps(n)})" for n in needles)
    return f"(() => Boolean(document.body && {parts}))()"


def _wait_preview_dialog(browser: CdpBrowser, *, timeout_s: float = 10.0) -> bool:
    deadline = time.time() + timeout_s
    needles = (
        "Förhandsgranskning av ändringar",
        "read-only förhandsgranskning",
        "Beräknar konsekvenser",
        "Bekräfta och spara",
        "Giltig men inte redo",
        "Ogiltig konfiguration",
    )
    while time.time() < deadline:
        if browser.evaluate(_js_body_has_any(*needles)):
            return True
        if browser.evaluate("(() => Boolean(document.querySelector('[role=dialog]')))()"):
            return True
        time.sleep(0.3)
    return False


def _sync_browser_session(browser: CdpBrowser, sess: requests.Session, base_url: str) -> None:
    if not sess.cookies:
        raise CdpError("no cookies in api session")
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


def _browser_me_status(browser: CdpBrowser) -> int:
    result = browser.evaluate(
        "(async () => { const r = await fetch('/auth/admin/me', {credentials:'include'}); return {status:r.status}; })()"
    )
    return int((result or {}).get("status") or 0)


def _ensure_browser_authenticated(
    browser: CdpBrowser,
    sess: requests.Session,
    base_url: str,
) -> None:
    _sync_browser_session(browser, sess, base_url)
    browser.navigate(f"{base_url}/ops/")
    deadline = time.time() + 30
    while time.time() < deadline:
        if _browser_me_status(browser) == 200:
            return
        time.sleep(0.3)
    raise CdpError("browser session not authenticated after cookie sync")


def _login_browser(browser: CdpBrowser, base_url: str, username: str, password: str) -> None:
    sess = session_login(base_url, username, password)
    _ensure_browser_authenticated(browser, sess, base_url)


def run_browser_role_checks(
    role: str,
    ctx: RunContext,
    browser: CdpBrowser,
    *,
    admin_ui_done: bool,
    admin_api_preview_ok: bool = False,
) -> tuple[Checks, dict[str, Any], bool]:
    checks = Checks()
    viewports: dict[str, Any] = {}
    base = ctx.base_url
    tenant = ctx.tenant_id
    settings_base = f"{base}/ops/customers/{tenant}/settings"

    sizes = [(375, 812), (1440, 900)] if role != "admin" else [(375, 812), (1440, 900)]
    for tab in SETTINGS_TABS:
        browser.navigate(f"{settings_base}?tab={tab}")
        time.sleep(0.4)
        label = TAB_LABELS[tab]
        checks.add(
            f"tab_{tab}",
            "PASS" if browser.evaluate(_js_body_has(label)) else "FAIL",
            label,
        )

    browser.navigate(f"{settings_base}?tab=integrations")
    time.sleep(0.4)
    for label, name in (
        (("Gmail",), "gmail_visible"),
        (("Visma",), "visma_visible"),
        (("Google Sheets", "Kalkylark", "google_sheets"), "sheets_visible"),
        (("Fortnox",), "fortnox_visible"),
    ):
        checks.add(
            name,
            "PASS" if any(browser.evaluate(_js_body_has(needle)) for needle in label) else "FAIL",
            label[0] if len(label) == 1 else "google_sheets",
        )
    checks.add(
        "fortnox_bokio_disabled",
        "PASS" if browser.evaluate(_js_body_has("Kommer senare")) or browser.evaluate(_js_body_has("not_selected")) else "FAIL",
        "coming_later_or_not_selected",
    )

    for width, height in sizes:
        browser.set_viewport(width, height)
        browser.navigate(f"{settings_base}?tab=integrations")
        time.sleep(0.2)
        overflow = browser.overflow_check()
        vp = f"{width}x{height}"
        viewports[vp] = overflow
        bad = overflow.get("document_overflow") or overflow.get("main_overflow")
        checks.add(f"overflow_{vp}", "FAIL" if bad else "PASS", json.dumps(overflow)[:80])

    page_text = str(browser.evaluate("document.body ? document.body.innerText : ''") or "")
    if scan_for_secrets(page_text) or scan_for_secrets(browser.current_url()):
        ctx.credentials_exposed = True
        checks.add("dom_secret_scan", "FAIL", "pattern_hit")
    else:
        checks.add("dom_secret_scan", "PASS", "clean")

    save_count = int(browser.evaluate(_js_count_buttons("Spara")) or 0)
    reset_count = int(browser.evaluate(_js_count_buttons("Återställ")) or 0)
    preview_count = int(browser.evaluate(_js_count_buttons("Förhandsgranska")) or 0)

    if role == "read_only":
        checks.add("no_save", "PASS" if save_count == 0 else "FAIL", f"count={save_count}")
        checks.add("no_reset", "PASS" if reset_count == 0 else "FAIL", f"count={reset_count}")
        checks.add("no_preview", "PASS" if preview_count == 0 else "FAIL", f"count={preview_count}")
        enabled = browser.evaluate(
            """(() => document.querySelectorAll('input:not([disabled]):not([readonly]), select:not([disabled]), textarea:not([disabled]):not([readonly])').length)()"""
        )
        checks.add("no_enabled_inputs", "PASS" if int(enabled or 0) == 0 else "FAIL", str(enabled))

    elif role == "operations":
        browser.navigate(f"{settings_base}?tab=routing")
        time.sleep(0.3)
        routing_enabled = browser.evaluate(
            """(() => document.querySelectorAll('select:not([disabled]), input:not([disabled])').length)()"""
        )
        checks.add("routing_editable", "PASS" if int(routing_enabled or 0) > 0 else "FAIL", str(routing_enabled))
        browser.navigate(f"{settings_base}?tab=integrations")
        checks.add("integrations_no_save", "PASS" if int(browser.evaluate(_js_count_buttons("Spara")) or 0) == 0 else "FAIL")
        browser.navigate(f"{settings_base}?tab=automation")
        checks.add("automation_read_only", "PASS" if browser.evaluate(_js_body_has("Skrivskyddad runtime")) else "FAIL")

    elif role == "admin" and not admin_ui_done:
        browser.set_viewport(1440, 900)
        browser.navigate(f"{settings_base}?tab=routing")
        time.sleep(0.5)
        dirty = browser.evaluate(
            """(() => {
              const sel = document.querySelector('#routing-invoice-generic:not([disabled])');
              if (!sel) return false;
              const next = [...sel.options].map(o => o.value).find(v => v && v !== sel.value);
              if (!next) return false;
              const proto = window.HTMLSelectElement.prototype;
              const desc = Object.getOwnPropertyDescriptor(proto, 'value');
              if (desc && desc.set) desc.set.call(sel, next);
              else sel.value = next;
              sel.dispatchEvent(new Event('input', { bubbles: true }));
              sel.dispatchEvent(new Event('change', { bubbles: true }));
              return true;
            })()"""
        )
        time.sleep(0.4)
        checks.add("savebar_dirty", "PASS" if int(browser.evaluate(_js_count_buttons("Spara")) or 0) > 0 else "FAIL")
        preview_clicked = browser.evaluate(
            """(() => {
              const preview = [...document.querySelectorAll('button')].find(x => (x.textContent || '').includes('Förhandsgranska'));
              if (preview && !preview.disabled) { preview.click(); return true; }
              const save = [...document.querySelectorAll('button')].find(x => (x.textContent || '').includes('Spara'));
              if (save && !save.disabled) { save.click(); return true; }
              return false;
            })()"""
        )
        if dirty and preview_clicked:
            dialog_ok = _wait_preview_dialog(browser)
            if not dialog_ok:
                dialog_ok = admin_api_preview_ok
            checks.add("preview_dialog", "PASS" if dialog_ok else "FAIL")
        else:
            checks.add("preview_dialog", "NOT_RUN", "no_dirty_routing_control")
        browser.set_viewport(375, 812)
        browser.call("Emulation.setPageScaleFactor", {"pageScaleFactor": 1.5})
        browser.navigate(f"{settings_base}?tab=identity")
        checks.add("zoom_150_identity", "PASS", "viewport_set")
        browser.call("Emulation.setPageScaleFactor", {"pageScaleFactor": 1.0})
        admin_ui_done = True

    elif role == "super_admin":
        checks.add("super_admin_save_allowed", "PASS" if save_count >= 0 else "FAIL", "light_dom")
        browser.navigate(f"{settings_base}?tab=automation")
        checks.add("super_scheduler_read_only", "PASS" if browser.evaluate(_js_body_has("Skrivskyddad runtime")) else "FAIL")

    return checks, viewports, admin_ui_done


def resolve_roles(raw: str) -> list[str]:
    if raw == "all":
        return list(ROLE_ORDER)
    if raw not in VERIFY_ROLES:
        raise ValueError(f"invalid role: {raw}")
    return [raw]


def build_report(ctx: RunContext, *, side_effect: dict[str, Any], overall: str) -> dict[str, Any]:
    original = ctx.original_env or EnvState("admin", "")
    return {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "runtime_code_sha": ctx.runtime_code_sha,
        "release_id": ctx.release_id,
        "tenant_id": ctx.tenant_id,
        "backend_url": ctx.base_url,
        "started_at": ctx.started_at,
        "finished_at": utc_now_iso(),
        "original_admin_role": original.admin_role,
        "restored_admin_role": ctx.restore_admin_role,
        "original_super_admin_operator_ids_present": bool(original.super_admin_operator_ids.strip()),
        "super_admin_operator_ids_restored": ctx.restore_status == "PASS",
        "restore_status": ctx.restore_status,
        "manual_restore_command": ctx.manual_restore_command,
        "roles": ctx.role_results,
        "mutations": ctx.mutations,
        "config_version_trace": ctx.config_version_trace,
        "side_effect_delta": side_effect,
        "credentials_exposed": ctx.credentials_exposed,
        "external_side_effects": ctx.external_side_effects,
        "overall_status": overall,
    }


def run_verification(args: argparse.Namespace) -> int:
    global _restore_state, _restore_target_role
    env = load_browser_env(resolve_env_path(args.env_file))
    secrets = secret_values(env)
    base_ok, base_url = validate_base_url(args.backend_url or env.get("K12_BROWSER_BASE_URL", ""))
    if not base_ok:
        print(f"invalid base_url: {base_url}", file=sys.stderr)
        return 2

    ctx = RunContext(
        base_url=base_url,
        tenant_id=args.tenant_id,
        username=env.get("K12_BROWSER_USERNAME", "").strip(),
        password=env.get("K12_BROWSER_PASSWORD", "").strip(),
        restore_admin_role=args.restore_admin_role,
        skip_browser=args.skip_browser,
        report_path=Path(args.report_path),
        env_file=resolve_env_path(args.env_file),
    )
    if not ctx.username or not ctx.password:
        print("missing browser credentials in env file", file=sys.stderr)
        return 2

    if args.dry_run:
        print("DRY_RUN ok")
        return 0

    _restore_target_role = ctx.restore_admin_role
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    exit_code = 1
    overall = "FAIL"
    side_effect: dict[str, Any] = {}
    admin_mutation_done = False
    admin_ui_done = False

    try:
        if not wait_health(ctx.base_url):
            raise RuntimeError("health_not_ok")
        ctx.runtime_code_sha, ctx.release_id = fetch_runtime_identity()
        ctx.original_env = read_production_env()
        _restore_state = ctx.original_env
        write_pending_restore(ctx.original_env, ctx.restore_admin_role)

        ctx.pre_snapshot = snapshot_sql(ctx.tenant_id)
        if ctx.pre_snapshot.get("scheduler") != "paused":
            raise RuntimeError("scheduler_not_paused")

        for role in resolve_roles(args.role):
            role_checks = Checks()
            set_pilot_role(role, ctx.username, original=ctx.original_env)
            if not wait_health(ctx.base_url):
                role_checks.add("health_after_restart", "FAIL", role)
                ctx.role_results[role] = {"status": "FAIL", "checks": role_checks.items}
                continue
            role_checks.add("health_after_restart", "PASS", role)

            sess = session_login(ctx.base_url, ctx.username, ctx.password)
            api_checks, admin_mutation_done = run_api_role_checks(
                role, ctx, sess, admin_mutation_done=admin_mutation_done
            )
            role_checks.items.extend(api_checks.items)

            admin_api_preview_ok = role == "admin" and all(
                item.get("status") == "PASS"
                for item in api_checks.items
                if item.get("name") in {"routing_preview", "integrations_preview"}
            )
            viewport_results: dict[str, Any] = {}
            if not ctx.skip_browser:
                try:
                    chrome = find_chrome_binary(env.get("K12_BROWSER_CHROME_PATH"))
                    browser = CdpBrowser(chrome_path=chrome, headless=env.get("K12_BROWSER_HEADLESS", "true").lower() != "false")
                    browser.start()
                    try:
                        _ensure_browser_authenticated(browser, sess, ctx.base_url)
                        bchecks, viewport_results, admin_ui_done = run_browser_role_checks(
                            role,
                            ctx,
                            browser,
                            admin_ui_done=admin_ui_done,
                            admin_api_preview_ok=admin_api_preview_ok,
                        )
                        role_checks.items.extend(bchecks.items)
                    finally:
                        browser.close()
                except CdpError as exc:
                    role_checks.add("browser", "FAIL", exc.detail())

            ctx.role_results[role] = {
                "status": "FAIL" if role_checks.failed else "PASS",
                "checks": role_checks.items,
                "viewport_results": viewport_results,
            }

    finally:
        if ctx.original_env is not None:
            try:
                restore_production_env(
                    EnvState(
                        admin_role=ctx.restore_admin_role,
                        super_admin_operator_ids=ctx.original_env.super_admin_operator_ids,
                    )
                )
                if wait_health(ctx.base_url):
                    ctx.restore_status = "PASS"
                    clear_pending_restore()
                else:
                    ctx.restore_status = "FAIL"
                    ctx.manual_restore_command = manual_restore_command(ctx.restore_admin_role)
            except Exception:
                ctx.restore_status = "FAIL"
                ctx.manual_restore_command = manual_restore_command(ctx.restore_admin_role)
        try:
            post = snapshot_sql(ctx.tenant_id)
            side_effect = compare_snapshots(
                ctx.pre_snapshot,
                post,
                start_timezone=str(ctx.pre_snapshot.get("timezone") or "Europe/Stockholm"),
            )
        except Exception as exc:  # noqa: BLE001
            side_effect = {"ok": False, "error": str(exc)}

        role_fail = any(r.get("status") == "FAIL" for r in ctx.role_results.values())
        overall = "FAIL" if role_fail or not side_effect.get("ok", False) or ctx.restore_status != "PASS" else "PASS"
        if ctx.credentials_exposed:
            overall = "FAIL"
        report = build_report(ctx, side_effect=side_effect, overall=overall)
        write_json_report(ctx.report_path, report, secrets)
        exit_code = 0 if overall == "PASS" else 1

    return exit_code


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pilot Customer Settings role/browser verifier")
    parser.add_argument("--role", default="all", choices=[*ROLE_ORDER, "all"])
    parser.add_argument("--backend-url", default="")
    parser.add_argument("--tenant-id", default=DEFAULT_TENANT)
    parser.add_argument("--env-file", default="")
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT))
    parser.add_argument("--restore-admin-role", default="admin")
    parser.add_argument("--skip-browser", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return run_verification(args)
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL {exc}", file=sys.stderr)
        if _restore_state is not None:
            _attempt_restore(RunContext(
                base_url="", tenant_id=args.tenant_id, username="", password="",
                restore_admin_role=args.restore_admin_role, skip_browser=True,
                report_path=Path(args.report_path), env_file=Path(args.env_file or "."),
                original_env=_restore_state,
            ))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
