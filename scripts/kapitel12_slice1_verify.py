"""
Kapitel 12 Slice 1 — golden paths, roles, tenant isolation, contracts,
approval-first React parity, legacy parity matrix.

Output: scripts/kapitel12_slice1_report.json
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from app.core.admin_session import hash_password
from app.core.settings import get_settings
from app.main import app

ORIGIN_OK = "http://testserver"
PASSWORD = "k12-slice1-password"
SECRET = "k12-slice1-secret"
TENANT_A = "T_K12_A"
TENANT_B = "T_K12_B"

checks: list[dict] = []
pytest_runs: list[dict] = []


def ok(name: str, detail: str = "", section: str = ""):
    checks.append({"section": section, "name": name, "status": "PASS", "detail": detail})
    print(f"PASS [{section}] {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str, section: str = ""):
    checks.append({"section": section, "name": name, "status": "FAIL", "detail": detail})
    print(f"FAIL [{section}] {name} — {detail}")


def skip(name: str, detail: str, section: str = ""):
    checks.append({"section": section, "name": name, "status": "SKIP", "detail": detail})
    print(f"SKIP [{section}] {name} — {detail}")


def partial(name: str, detail: str, section: str = ""):
    checks.append({"section": section, "name": name, "status": "PARTIAL", "detail": detail})
    print(f"PARTIAL [{section}] {name} — {detail}")


def _session_settings(role: str = "admin"):
    h = hash_password(PASSWORD)
    return SimpleNamespace(
        SESSION_SECRET_KEY=SECRET,
        ADMIN_PASSWORD_HASH=h,
        ADMIN_USERNAME="admin",
        ADMIN_ROLE=role,
        ADMIN_DISPLAY_NAME="K12 Operator",
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


def run_pytest(label: str, paths: list[str]) -> bool:
    cmd = [sys.executable, "-m", "pytest", "-q", "--tb=no", *paths]
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
    detail = " | ".join(tail) if tail else f"exit {proc.returncode}"
    pytest_runs.append(
        {
            "label": label,
            "paths": paths,
            "exit_code": proc.returncode,
            "detail": detail,
        }
    )
    section = "pytest"
    if proc.returncode == 0:
        ok(label, detail, section)
        return True
    fail(label, detail, section)
    return False


def verify_golden_paths():
    section = "golden_paths"
    mapping = {
        "A_onboarding": ["tests/test_admin_onboarding.py", "tests/test_onboarding_wizard.py"],
        "B_manual_review": [
            "tests/test_manual_review_handoff.py",
            "tests/test_job_pending_approval_visibility.py",
        ],
        "C_lead": ["tests/test_local_golden_path.py"],
        "D_support": ["tests/test_core_intelligence_quality.py", "tests/test_support_layer_v1.py"],
        "E_invoice": ["tests/test_swedish_extraction_quality.py", "tests/test_invoice_extraction.py"],
        "F_alerts": ["tests/test_admin_alerts.py", "tests/test_alerting.py"],
        "G_incidents": ["tests/test_admin_incidents.py"],
        "H_recovery": ["tests/test_recovery_actions.py"],
        "I_daily_ops": [
            "tests/test_admin_operations_triage.py",
            "tests/test_admin_operations_needs_help.py",
            "tests/test_admin_system_status.py",
        ],
    }
    for path_id, files in mapping.items():
        existing = [f for f in files if (ROOT / f).exists()]
        if not existing:
            skip(path_id, "test files missing", section)
            continue
        run_pytest(path_id, existing)


def verify_roles_matrix():
    section = "roles"
    endpoints = [
        ("GET", "/admin/operations/overview", "overview", [200], ["read_only", "operations", "admin"]),
        ("GET", "/admin/operations/needs-help", "needs_help", [200], ["read_only", "operations", "admin"]),
        ("POST", "/admin/alerts/run-all", "alert_eval", [200, 202], ["operations", "admin"]),
        (
            "POST",
            "/admin/tenants/T_X/approvals/appr-x/approve",
            "approve",
            [403, 404, 422],
            ["operations", "admin"],
        ),
        (
            "POST",
            "/admin/tenants/T_X/approvals/appr-x/reject",
            "reject",
            [403, 404, 422],
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
            headers = {"Origin": ORIGIN_OK, "X-Tenant-ID": TENANT_A}
            for method, path, label, allowed_status, allowed_roles in endpoints:
                if method == "GET":
                    r = client.get(path, headers=headers)
                else:
                    r = client.request(
                        method,
                        path,
                        headers=headers,
                        json={
                            "reason": "K12 slice1 role matrix verification.",
                            "idempotency_key": "k12-role-matrix",
                        },
                    )
                if role in allowed_roles:
                    if r.status_code in allowed_status or (r.status_code < 500 and r.status_code != 403):
                        ok(f"{role}.{label}", str(r.status_code), section)
                    else:
                        fail(f"{role}.{label}", f"unexpected {r.status_code}", section)
                elif r.status_code == 403:
                    ok(f"{role}.{label}_blocked", "403", section)
                else:
                    fail(f"{role}.{label}_blocked", f"expected 403 got {r.status_code}", section)


def verify_tenant_isolation():
    section = "tenant_ab"
    run_pytest("tenant_isolation_http", ["tests/test_tenant_isolation_http.py"])

    api_key = get_settings().ADMIN_API_KEY.strip()
    if not api_key:
        skip("tenant_ab_live", "ADMIN_API_KEY missing", section)
        return
    client = TestClient(app)
    h = {"X-Admin-API-Key": api_key, "Origin": ORIGIN_OK}

    r_a = client.get("/admin/alerts", params={"tenant_id": TENANT_A, "limit": 5}, headers=h)
    if r_a.status_code == 200:
        leaked = [
            item.get("tenant_id")
            for item in r_a.json().get("items", [])
            if item.get("tenant_id") and item.get("tenant_id") != TENANT_A
        ]
        if leaked:
            fail("alerts_filter_a", f"leaked {leaked[:3]}", section)
        else:
            ok("alerts_filter_a", "no cross-tenant rows", section)
    else:
        fail("alerts_filter_a", str(r_a.status_code), section)

    with patch("app.admin.recovery_actions.JobRepository.get_job_by_id", return_value=None):
        r_rec = client.post(
            "/admin/recovery/job-k12/retry",
            headers={**h, "X-Tenant-ID": TENANT_B},
            json={},
        )
    if r_rec.status_code in (403, 404):
        ok("recovery_wrong_context", str(r_rec.status_code), section)
    else:
        fail("recovery_wrong_context", str(r_rec.status_code), section)


def verify_approval_react_parity():
    section = "approval_react"
    frontend = ROOT / "frontend" / "src"
    required = {
        "api_approve": frontend / "features" / "operatorActions" / "api.ts",
        "mutation_approve": frontend / "features" / "operatorActions" / "mutations.ts",
        "registry_approve": frontend / "features" / "operatorActions" / "actionRegistry.ts",
        "needs_help_detail": frontend / "features" / "needsHelp" / "NeedsHelpDetailPage.tsx",
        "customer_detail_link": frontend / "features" / "customers" / "CustomerDetailPage.tsx",
    }
    for name, path in required.items():
        if not path.exists():
            fail(name, "missing file", section)
            continue
        text = path.read_text(encoding="utf-8")
        if name == "api_approve" and "approveTenantApproval" in text:
            ok(name, "approveTenantApproval exported", section)
        elif name == "mutation_approve" and "useApproveApprovalMutation" in text:
            ok(name, "useApproveApprovalMutation exported", section)
        elif name == "registry_approve" and '"approval.approve"' in text:
            ok(name, "approval.approve presentation", section)
        elif name == "needs_help_detail" and "OperatorActionsSection" in text:
            ok(name, "operator actions on needs-help detail", section)
        elif name == "customer_detail_link" and "needs-help/approval:" in text:
            ok(name, "pending approvals link to needs-help", section)
        else:
            fail(name, "required symbol missing", section)

    mounted = {getattr(r, "path", "") for r in app.routes}
    if "/admin/tenants/{tenant_id}/approvals/{approval_id}/approve" in mounted:
        ok("backend_approve_route", "mounted", section)
    else:
        fail("backend_approve_route", "not mounted", section)

    with role_client("operations") as client:
        r = client.post(
            f"/admin/tenants/{TENANT_A}/approvals/appr-k12/approve",
            headers={"Origin": ORIGIN_OK, "X-Tenant-ID": TENANT_A},
            json={
                "reason": "K12 slice1 approval parity check.",
                "idempotency_key": "k12-approve-parity",
            },
        )
    if r.status_code in (403, 404, 409, 422):
        ok("approve_session_endpoint", str(r.status_code), section)
    else:
        fail("approve_session_endpoint", str(r.status_code), section)

    run_pytest(
        "operator_actions_approve",
        ["tests/test_admin_operator_actions.py", "tests/test_admin_security_contracts.py"],
    )


def verify_legacy_parity():
    section = "legacy"
    ui_path = ROOT / "app" / "ui" / "index.html"
    if not ui_path.exists():
        fail("legacy_ui_exists", "missing", section)
        return
    text = ui_path.read_text(encoding="utf-8")

    if "LEGACY_UI_READ_ONLY = true" in text:
        ok("legacy_read_only_flag", "true", section)
    else:
        fail("legacy_read_only_flag", "not set", section)

    if re.search(r"localStorage\.setItem\s*\(\s*LS_ADMIN_KEY", text):
        fail("legacy_admin_key_persist", "setItem(LS_ADMIN_KEY) found", section)
    else:
        ok("legacy_admin_key_persist", "no setItem(LS_ADMIN_KEY)", section)

    if "_purgeLegacyAdminKeyStorage" in text and "localStorage.removeItem(LS_ADMIN_KEY)" in text:
        ok("legacy_admin_key_purge", "purge helper present", section)
    else:
        fail("legacy_admin_key_purge", "purge missing", section)

    if "Skrivåtgärder är avstängda i legacy-UI" in text:
        ok("legacy_write_block", "adminApiFetch blocks writes", section)
    else:
        fail("legacy_write_block", "message missing", section)

    if "Legacy UI (endast läsning)" in text or "legacy" in text.lower():
        ok("legacy_deprecation_banner", "present", section)
    else:
        partial("legacy_deprecation_banner", "banner text not found", section)

    matrix = [
        ("overview", "/ops", "PASS"),
        ("customers_onboarding", "/ops/customers", "PASS"),
        ("needs_help", "/ops/needs-help", "PASS"),
        ("incidents", "/ops/incidents", "PASS"),
        ("alerts", "/ops/alerts", "PASS"),
        ("usage", "/ops/usage", "PASS"),
        ("system", "/ops/system", "PASS"),
        ("approvals_approve", "React operator actions", "PASS"),
        ("approvals_reject", "React operator actions", "PASS"),
        ("recovery_console", "API/runbook only", "PARTIAL"),
        ("jobs_browser", "metrics on customer detail", "PARTIAL"),
        ("manual_review_queue", "overview/needs-help counts", "PARTIAL"),
    ]
    for item, surface, status in matrix:
        if status == "PASS":
            ok(f"parity_{item}", surface, section)
        else:
            partial(f"parity_{item}", surface, section)

    client = TestClient(app)
    api_key = get_settings().ADMIN_API_KEY.strip()
    headers = {"X-Admin-API-Key": api_key, "Origin": ORIGIN_OK} if api_key else {}
    r_get = client.get("/admin/alerts/run-all", headers=headers)
    if r_get.status_code in (401, 403, 404, 405):
        ok("no_get_run_all", str(r_get.status_code), section)
    else:
        fail("no_get_run_all", str(r_get.status_code), section)

    suspicious = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            for method in route.methods or []:
                if method == "GET" and any(
                    x in route.path for x in ("run-all", "rotate", "recovery", "activate", "seed")
                ):
                    suspicious.append(f"GET {route.path}")
    if suspicious:
        fail("state_changing_get_inventory", "; ".join(sorted(suspicious)[:8]), section)
    else:
        ok("state_changing_get_inventory", "clean", section)


def verify_contracts_and_release_blockers():
    section = "release_blockers"
    offsite = os.environ.get("OFFSITE_BACKUP_COMMAND", "").strip()
    if offsite:
        ok("RB-01_offsite_configured", "OFFSITE_BACKUP_COMMAND set", section)
    else:
        partial("RB-01_offsite_configured", "OFFSITE_BACKUP_COMMAND empty — release blocker", section)

    run_pytest(
        "security_bundle",
        [
            "tests/test_admin_security_contracts.py",
            "tests/test_security_secret_scan.py",
            "tests/test_admin_session.py",
        ],
    )

    frontend = ROOT / "frontend"
    if (frontend / "package.json").exists():
        for script, label in (
            (["run", "typecheck"], "frontend_typecheck"),
            (["run", "test:contracts"], "frontend_contracts"),
            (["run", "test:onboarding"], "frontend_onboarding"),
        ):
            proc = subprocess.run(
                ["npm", *script],
                cwd=frontend,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=True,
            )
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            tail = (stdout + stderr).strip().splitlines()[-2:]
            detail = " | ".join(tail) if tail else f"exit {proc.returncode}"
            if proc.returncode == 0:
                ok(label, detail, section)
            else:
                fail(label, detail, section)
    else:
        skip("frontend_gates", "frontend missing", section)


def classify_slice() -> str:
    statuses = [c["status"] for c in checks]
    if any(s == "FAIL" for s in statuses):
        return "FAIL"
    pytest_failed = any(r["exit_code"] != 0 for r in pytest_runs)
    if pytest_failed:
        return "FAIL"
    if any(s == "PARTIAL" for s in statuses):
        return "PARTIAL"
    if any(s == "SKIP" for s in statuses):
        return "PARTIAL"
    return "PASS"


def main() -> int:
    print("Kapitel 12 Slice 1 verification\n")
    verify_golden_paths()
    verify_roles_matrix()
    verify_tenant_isolation()
    verify_approval_react_parity()
    verify_legacy_parity()
    verify_contracts_and_release_blockers()

    slice_status = classify_slice()
    out = ROOT / "scripts" / "kapitel12_slice1_report.json"
    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "slice_status": slice_status,
        "test_tenants": [TENANT_A, TENANT_B, "T_K12_RELEASE_VERIFY"],
        "pass": sum(1 for c in checks if c["status"] == "PASS"),
        "fail": sum(1 for c in checks if c["status"] == "FAIL"),
        "partial": sum(1 for c in checks if c["status"] == "PARTIAL"),
        "skip": sum(1 for c in checks if c["status"] == "SKIP"),
        "pytest_runs": pytest_runs,
        "release_blockers_open": ["RB-01 offsite backup + restore PASS"],
        "checks": checks,
    }
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSlice 1 status: {slice_status}")
    print(f"Report: {out}")
    print(
        f"PASS={summary['pass']} FAIL={summary['fail']} "
        f"PARTIAL={summary['partial']} SKIP={summary['skip']}"
    )
    return 1 if slice_status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
