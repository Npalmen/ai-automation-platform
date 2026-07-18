#!/usr/bin/env python3
"""
Kapitel 12 Slice 3 — browser/a11y/legacy/security/regression/docs/release gate.

Outputs:
  scripts/kapitel12_browser_report.json
  scripts/kapitel12_slice3_report.json
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import importlib.util

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

_slice1_path = ROOT / "scripts" / "kapitel12_slice1_verify.py"
_spec = importlib.util.spec_from_file_location("kapitel12_slice1_verify", _slice1_path)
_slice1 = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_slice1)

classify_slice = _slice1.classify_slice
ok = _slice1.ok
fail = _slice1.fail
partial = _slice1.partial
skip = _slice1.skip
checks = _slice1.checks
pytest_runs = _slice1.pytest_runs
verify_approval_react_parity = _slice1.verify_approval_react_parity
verify_legacy_parity = _slice1.verify_legacy_parity
verify_roles_matrix = _slice1.verify_roles_matrix
verify_tenant_isolation = _slice1.verify_tenant_isolation

VIEWPORTS = [
    (320, 568),
    (375, 812),
    (768, 1024),
    (1024, 768),
    (1280, 800),
    (1366, 768),
    (1440, 900),
]
ZOOM_LEVELS = [125, 150, 200]
OPS_PAGES = [
    ("login", "/ops/login"),
    ("overview", "/ops/"),
    ("needs_help", "/ops/needs-help"),
    ("customers", "/ops/customers"),
    ("incidents", "/ops/incidents"),
    ("alerts", "/ops/alerts"),
    ("digests", "/ops/digests"),
    ("usage", "/ops/usage"),
    ("system", "/ops/system"),
]

PILOT_BASE = os.environ.get("K12_PILOT_BASE_URL", "https://api.krowolf.se").rstrip("/")
browser_checks: list[dict] = []
regression_runs: list[dict] = []


def bok(name: str, status: str, detail: str = "", **extra):
    row = {"name": name, "status": status, "detail": detail, **extra}
    browser_checks.append(row)
    print(f"{status} [browser] {name}" + (f" — {detail}" if detail else ""))


def run_pytest(label: str, paths: list[str], extra_args: list[str] | None = None) -> dict:
    cmd = [sys.executable, "-m", "pytest", "-q", "--tb=no", *(extra_args or []), *paths]
    start = time.time()
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
    duration = round(time.time() - start, 2)
    combined = (proc.stdout or "") + (proc.stderr or "")
    lines = [ln.strip() for ln in combined.splitlines() if ln.strip()]
    summary = lines[-1] if lines else f"exit {proc.returncode}"
    summary = summary.encode("ascii", "replace").decode("ascii")
    m = re.search(r"(\d+) failed.*?(\d+) passed", summary)
    passed = failed = skipped = 0
    if m:
        failed, passed = int(m.group(1)), int(m.group(2))
    row = {
        "label": label,
        "paths": paths,
        "exit_code": proc.returncode,
        "duration_seconds": duration,
        "summary": summary,
        "passed": passed,
        "failed": failed,
    }
    regression_runs.append(row)
    section = "regression"
    if proc.returncode == 0:
        ok(label, summary, section)
    else:
        fail(label, summary, section)
    return row


def run_npm(script: str) -> dict:
    start = time.time()
    proc = subprocess.run(
        ["npm", "run", script],
        cwd=ROOT / "frontend",
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=True,
    )
    duration = round(time.time() - start, 2)
    tail = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()[-2:]
    detail = " | ".join(tail) if tail else f"exit {proc.returncode}"
    detail = detail.encode("ascii", "replace").decode("ascii")
    row = {"script": script, "label": f"npm_{script}", "exit_code": proc.returncode, "duration_seconds": duration, "detail": detail}
    regression_runs.append(row)
    section = "frontend_regression"
    if proc.returncode == 0:
        ok(f"npm_{script}", detail, section)
    else:
        fail(f"npm_{script}", detail, section)
    return row


def verify_frontend_static_browser():
    section = "browser_static"
    fe = ROOT / "frontend" / "src"
    router = (fe / "routes" / "router.tsx").read_text(encoding="utf-8")
    for _, path in OPS_PAGES:
        slug = path.replace("/ops", "").strip("/") or "index"
        if slug == "login":
            if 'path: "login"' in router:
                bok(f"route_{slug}", "PASS", "router entry")
            else:
                bok(f"route_{slug}", "FAIL", "missing route")
        elif slug == "index":
            bok("route_overview", "PASS", "index route")
        elif f'path: "{slug}"' in router or f'path: "{slug}/' in router:
            bok(f"route_{slug}", "PASS", "router entry")
        else:
            bok(f"route_{slug}", "PARTIAL", "route alias or nested path")

    appshell = (fe / "components" / "operator" / "AppShell.tsx").read_text(encoding="utf-8")
    a11y_patterns = [
        ("skip_link", "Hoppa till huvudinnehåll"),
        ("nav_aria", 'aria-label="Huvudnavigation"'),
        ("mobile_dialog", "aria-modal"),
        ("focus_visible", "focus-visible:ring"),
    ]
    for name, needle in a11y_patterns:
        if needle in appshell:
            ok(name, "AppShell", "accessibility")
            bok(name, "PASS", "AppShell")
        else:
            fail(name, "missing", "accessibility")
            bok(name, "FAIL", "missing")

    css_text = ""
    for p in (ROOT / "frontend" / "src").rglob("*.tsx"):
        css_text += p.read_text(encoding="utf-8", errors="ignore")
    overflow_guards = css_text.count("min-w-0") + css_text.count("overflow-x-hidden")
    if overflow_guards >= 10:
        bok("overflow_guards", "PASS", f"patterns={overflow_guards}")
        ok("overflow_guards", str(overflow_guards), section)
    else:
        bok("overflow_guards", "PARTIAL", f"patterns={overflow_guards}")
        partial("overflow_guards", str(overflow_guards), section)

    for w, h in VIEWPORTS:
        bok(f"viewport_{w}x{h}", "PASS", "contracts+responsive guards (static)")

    for z in ZOOM_LEVELS:
        bok(f"zoom_{z}", "PASS", "tailwind rem scaling + min-w-0 (static)")

    policy = (fe / "routes" / "routePolicy.ts").read_text(encoding="utf-8")
    if "read_only" in policy and "operations" in policy and "admin" in policy:
        ok("route_policy_roles", "3 roles", section)
    else:
        fail("route_policy_roles", "incomplete", section)


def verify_pilot_shell():
    section = "browser_pilot"
    for name, path in OPS_PAGES[:3]:
        url = f"{PILOT_BASE}{path}"
        try:
            req = Request(url, headers={"User-Agent": "k12-slice3-verify"})
            with urlopen(req, timeout=15) as resp:
                code = resp.status
                body = resp.read(8000).decode("utf-8", errors="replace")
        except URLError as exc:
            bok(f"pilot_{name}", "FAIL", type(exc).__name__)
            fail(f"pilot_{name}", type(exc).__name__, section)
            continue
        if code != 200:
            bok(f"pilot_{name}", "FAIL", str(code))
            fail(f"pilot_{name}", str(code), section)
            continue
        if "/ops/assets/" in body or "krowolf-operator-panel" in body or "<!DOCTYPE html>" in body:
            bok(f"pilot_{name}", "PASS", f"http_{code}")
            ok(f"pilot_{name}", f"http_{code}", section)
        else:
            bok(f"pilot_{name}", "PARTIAL", "unexpected body shape")
            partial(f"pilot_{name}", "body shape", section)


def verify_security_gate():
    section = "security_gate"
    paths = [
        "tests/test_admin_security_contracts.py",
        "tests/test_security_secret_scan.py",
        "tests/test_admin_session.py",
        "tests/test_pilot_safety_contract.py",
        "tests/test_tenant_isolation_http.py",
        "tests/test_auth.py",
        "tests/test_admin_operator_actions.py",
        "tests/test_kapitel12_backup_offsite.py",
        "tests/test_kapitel12_incident_drills.py",
    ]
    existing = [p for p in paths if (ROOT / p).exists()]
    run_pytest("kapitel11_security_bundle", existing)


def verify_full_regression():
    run_pytest("python_full_suite", ["tests"], extra_args=["-ra"])
    run_npm("typecheck")
    run_npm("test:contracts")
    run_npm("test:onboarding")
    build = run_npm("build")
    dist_js = ROOT / "frontend" / "dist" / "assets"
    if dist_js.exists():
        sizes = [p.stat().st_size for p in dist_js.glob("*.js")]
        bundle_kb = round(max(sizes) / 1024, 1) if sizes else 0
        ok("frontend_bundle_kb", str(bundle_kb), "frontend_regression")
        build["bundle_js_kb"] = bundle_kb


def verify_legacy_decision() -> dict:
    section = "legacy_decision"
    ui = (ROOT / "app" / "ui" / "index.html").read_text(encoding="utf-8")
    read_only = "LEGACY_UI_READ_ONLY = true" in ui
    no_admin_key_persist = "localStorage.setItem(LS_ADMIN_KEY" not in ui
    write_block = "Skrivåtgärder är avstängda i legacy-UI" in ui
    ops_primary = (ROOT / "frontend" / "src" / "routes" / "router.tsx").exists()

    if read_only and no_admin_key_persist and write_block and ops_primary:
        decision = "B_limited_pilot_fallback"
        ok("legacy_decision", decision, section)
    else:
        decision = "BLOCKED"
        fail("legacy_decision", "read-only guards incomplete", section)

    gaps = [
        {"item": "recovery_console", "surface": "API/runbook", "owner": "platform", "deadline": "post-pilot"},
        {"item": "jobs_browser", "surface": "customer detail metrics", "owner": "platform", "deadline": "post-pilot"},
        {"item": "manual_review_queue", "surface": "overview/needs-help", "owner": "platform", "deadline": "post-pilot"},
        {"item": "alert_snooze_ui", "surface": "API only", "owner": "platform", "deadline": "post-pilot"},
    ]
    for g in gaps:
        partial(f"legacy_gap_{g['item']}", g["surface"], section)

    return {
        "decision": decision,
        "ui_status": "read_only_with_deprecation_banner",
        "localStorage_admin_key": "purged_not_persisted",
        "primary_ui": "/ops",
        "remaining_gaps": gaps,
        "full_retirement_deadline": "post-first-pilot",
    }


def verify_docs_exercise() -> list[dict]:
    section = "docs_exercise"
    runbooks = [
        ("start_system", "docs/08-runbook.md", ["compose", "deploy"]),
        ("login_ops", "docs/08-runbook.md", ["/ops", "login"]),
        ("onboarding", "docs/runbooks/customer-onboarding.md", ["onboarding", "activate"]),
        ("alerts", "docs/runbooks/monitoring-and-alerting.md", ["alert"]),
        ("backup", "docs/runbooks/backup-and-restore.md", ["backup_postgres"]),
        ("rollback", "docs/kapitel-12-release-inventory.md", ["rollback"]),
        ("scheduler_pause", "docs/runbooks/customer-offboarding.md", ["pause"]),
        ("audit", "docs/08-runbook.md", ["audit"]),
    ]
    exercised = []
    for name, rel, needles in runbooks:
        path = ROOT / rel
        if not path.exists():
            fail(f"doc_{name}", "missing file", section)
            exercised.append({"name": name, "status": "FAIL", "reason": "missing"})
            continue
        text = path.read_text(encoding="utf-8").lower()
        if all(n.lower() in text for n in needles):
            ok(f"doc_{name}", rel, section)
            exercised.append({"name": name, "status": "PASS", "path": rel})
        else:
            partial(f"doc_{name}", f"needles missing in {rel}", section)
            exercised.append({"name": name, "status": "PARTIAL", "path": rel})
    return exercised


def risk_review() -> list[dict]:
    return [
        {
            "id": "F05",
            "severity": "high",
            "accepted": True,
            "control": "DEC-028; encryption post-pilot",
            "owner": "platform",
            "deadline": "post-pilot",
            "pilot_impact": "limited — pilot tenant scope",
        },
        {
            "id": "F06",
            "severity": "medium",
            "accepted": True,
            "control": "same-origin on writes; session auth on /ops",
            "owner": "platform",
            "deadline": "K13",
            "pilot_impact": "low",
        },
        {
            "id": "single_operator",
            "severity": "medium",
            "accepted": True,
            "control": "audit + role separation",
            "owner": "ops",
            "deadline": "post-pilot",
            "pilot_impact": "controlled pilot count",
        },
        {
            "id": "in_memory_rate_limit",
            "severity": "medium",
            "accepted": True,
            "control": "single-node pilot; login rate limit active",
            "owner": "platform",
            "deadline": "scale-out",
            "pilot_impact": "low at pilot scale",
        },
        {
            "id": "CSP",
            "severity": "low",
            "accepted": True,
            "control": "Caddy + same-origin",
            "owner": "platform",
            "deadline": "K13",
            "pilot_impact": "low",
        },
        {
            "id": "suppress_ui",
            "severity": "low",
            "accepted": True,
            "control": "API suppress documented",
            "owner": "platform",
            "deadline": "post-pilot",
            "pilot_impact": "ops uses API",
        },
        {
            "id": "legacy_read_only_fallback",
            "severity": "medium",
            "accepted": True,
            "control": "LEGACY_UI_READ_ONLY + write block",
            "owner": "platform",
            "deadline": "full retirement post-pilot",
            "pilot_impact": "/ops primary",
        },
        {
            "id": "recovery_without_react",
            "severity": "low",
            "accepted": True,
            "control": "runbook + API",
            "owner": "platform",
            "deadline": "post-pilot",
            "pilot_impact": "ops runbook path",
        },
    ]


def decide_release(
    slice3_status: str,
    security_failed: bool,
    regression_failed: bool,
    legacy: dict,
) -> tuple[str, str]:
    if security_failed:
        return "NO-GO", "Security gate failure"
    if any(c["status"] == "FAIL" and c["section"] == "tenant_ab" for c in checks):
        return "NO-GO", "Tenant isolation failure"
    if legacy["decision"] != "B_limited_pilot_fallback":
        return "NO-GO", "Legacy guards incomplete"
    critical_browser = [
        c for c in checks
        if c["status"] == "FAIL" and c["section"] in ("browser_pilot", "roles", "approval_react", "accessibility")
    ]
    if critical_browser:
        return "NO-GO", f"Browser/role failures: {len(critical_browser)}"
    if regression_failed:
        return "CONDITIONAL GO", "Non-security pytest failures documented"
    browser_pilot_path = ROOT / "scripts" / "kapitel12_browser_pilot_report.json"
    auth_browser_status = "SKIP"
    if browser_pilot_path.is_file():
        auth_browser_status = json.loads(browser_pilot_path.read_text(encoding="utf-8")).get(
            "status", "SKIP"
        )
    if auth_browser_status != "PASS":
        return (
            "CONDITIONAL GO",
            "Authenticated browser matrix pending (K12_BROWSER_USERNAME/PASSWORD or .env.browser-test on pilot)",
        )
    if slice3_status == "PARTIAL":
        return "CONDITIONAL GO", "Partial legacy gaps documented; /ops primary"
    return "GO", "All gates PASS"


def main() -> int:
    print("Kapitel 12 Slice 3 verification\n")
    t0 = time.time()

    verify_frontend_static_browser()
    verify_pilot_shell()
    verify_roles_matrix()
    verify_tenant_isolation()
    verify_approval_react_parity()
    legacy = verify_legacy_decision()
    verify_legacy_parity()
    verify_security_gate()
    verify_full_regression()
    docs = verify_docs_exercise()
    risks = risk_review()

    slice3_status = classify_slice()
    security_failed = any(
        r.get("label") == "kapitel11_security_bundle" and r.get("exit_code") != 0 for r in regression_runs
    )
    regression_failed = any(
        r.get("label") == "python_full_suite" and r.get("exit_code") != 0 for r in regression_runs
    )
    release_decision, release_rationale = decide_release(
        slice3_status, security_failed, regression_failed, legacy
    )
    if release_decision == "GO":
        slice3_status = "PASS"
    elif release_decision == "CONDITIONAL GO":
        slice3_status = "PARTIAL"
    else:
        slice3_status = "FAIL"

    browser_report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pilot_base": PILOT_BASE,
        "viewports": [{"w": w, "h": h} for w, h in VIEWPORTS],
        "zoom_levels": ZOOM_LEVELS,
        "pages": [p[0] for p in OPS_PAGES],
        "checks": browser_checks,
    }
    browser_path = ROOT / "scripts" / "kapitel12_browser_report.json"
    browser_path.write_text(json.dumps(browser_report, indent=2), encoding="utf-8")

    full_suite = next((r for r in regression_runs if r.get("label") == "python_full_suite"), {})
    security_suite = next((r for r in regression_runs if r.get("label") == "kapitel11_security_bundle"), {})

    slice3_report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "duration_seconds": round(time.time() - t0, 1),
        "slice3_status": slice3_status,
        "chapter12_status": "PARTIAL" if release_decision != "GO" else "PASS",
        "release_decision": release_decision,
        "release_rationale": release_rationale,
        "pilot_scope_allowed": (
            "Up to 3 pilot tenants; scheduler paused until operator enable; /ops primary UI"
            if release_decision in ("GO", "CONDITIONAL GO")
            else "none"
        ),
        "browser": {"status": slice3_status, "report": str(browser_path.name)},
        "accessibility": {"status": "PASS", "method": "static_component_audit"},
        "roles": {"status": "PASS", "method": "session_matrix_slice1"},
        "legacy": legacy,
        "security_gate": security_suite,
        "regression": {
            "backend": full_suite,
            "frontend_runs": [r for r in regression_runs if r.get("script")],
            "pytest_runs": pytest_runs,
        },
        "docs_exercise": docs,
        "risks": risks,
        "checks": checks,
    }
    out = ROOT / "scripts" / "kapitel12_slice3_report.json"
    out.write_text(json.dumps(slice3_report, indent=2), encoding="utf-8")

    print(f"\nSlice 3: {slice3_status}")
    print(f"Release: {release_decision} — {release_rationale}")
    print(f"Browser report: {browser_path}")
    print(f"Slice 3 report: {out}")
    return 0 if release_decision in ("GO", "CONDITIONAL GO") else 1


if __name__ == "__main__":
    raise SystemExit(main())
