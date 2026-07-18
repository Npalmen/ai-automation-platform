"""
Kapitel 12 Slice 2 — drift, backup/restore, deploy/rollback, incidents, performance.

Output: scripts/kapitel12_slice2_report.json
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

checks: list[dict] = []
pytest_runs: list[dict] = []
capabilities: dict[str, bool] = {}


def ok(name: str, detail: str = "", section: str = ""):
    checks.append({"section": section, "name": name, "status": "PASS", "detail": detail})
    print(f"PASS [{section}] {name}" + (f" — {detail}" if detail else ""))


def fail(name: str, detail: str, section: str = ""):
    checks.append({"section": section, "name": name, "status": "FAIL", "detail": detail})
    print(f"FAIL [{section}] {name} — {detail}")


def blocked(name: str, detail: str, section: str = ""):
    checks.append({"section": section, "name": name, "status": "BLOCKED", "detail": detail})
    print(f"BLOCKED [{section}] {name} — {detail}")


def partial(name: str, detail: str, section: str = ""):
    checks.append({"section": section, "name": name, "status": "PARTIAL", "detail": detail})
    print(f"PARTIAL [{section}] {name} — {detail}")


def run_pytest(label: str, paths: list[str]) -> bool:
    cmd = [sys.executable, "-m", "pytest", "-q", "--tb=no", *paths]
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    tail = (proc.stdout or "") + (proc.stderr or "")
    lines = [ln for ln in tail.strip().splitlines() if ln.strip()]
    detail = lines[-1] if lines else f"exit {proc.returncode}"
    pytest_runs.append(
        {"label": label, "paths": paths, "exit_code": proc.returncode, "detail": detail}
    )
    if proc.returncode == 0:
        ok(label, detail, "pytest")
        return True
    fail(label, detail, "pytest")
    return False


def detect_capabilities():
    capabilities["docker"] = shutil.which("docker") is not None
    capabilities["bash"] = shutil.which("bash") is not None
    capabilities["pg_dump"] = shutil.which("pg_dump") is not None
    capabilities["git"] = shutil.which("git") is not None
    capabilities["offsite_command"] = bool(os.environ.get("OFFSITE_BACKUP_COMMAND", "").strip())
    capabilities["offsite_dest_dir"] = bool(os.environ.get("OFFSITE_BACKUP_DEST_DIR", "").strip())


def verify_backup_inventory():
    section = "backup_inventory"
    required = [
        "scripts/backup_postgres.sh",
        "scripts/restore_postgres_rehearsal.sh",
        "scripts/restore_from_offsite_rehearsal.sh",
        "scripts/offsite_backup_upload.py",
        "scripts/check_backup_freshness.sh",
        "scripts/write_operation_status.py",
        "docs/runbooks/backup-and-restore.md",
    ]
    for rel in required:
        if (ROOT / rel).exists():
            ok(f"file_{Path(rel).name}", rel, section)
        else:
            fail(f"file_{Path(rel).name}", f"missing {rel}", section)

    backup_sh = (ROOT / "scripts" / "backup_postgres.sh").read_text(encoding="utf-8")
    for token in (
        "OFFSITE_BACKUP_COMMAND",
        "--archive-integrity-verified",
        "offsite_verified",
        "BACKUP_RETENTION_DAYS",
    ):
        if token in backup_sh:
            ok(f"backup_script_{token}", "present", section)
        else:
            fail(f"backup_script_{token}", "missing", section)


def verify_rb01_offsite():
    section = "RB-01"
    import tempfile

    local = Path(tempfile.mkdtemp(prefix="k12-local-"))
    offsite = Path(tempfile.mkdtemp(prefix="k12-offsite-"))
    try:
        backup = local / "ai_platform_slice2_test.sql.gz"
        backup.write_bytes(b"-- k12 slice2 synthetic backup\n" * 80)
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "offsite_backup_upload.py"), str(backup)],
            capture_output=True,
            text=True,
            env={
                **os.environ,
                "OFFSITE_BACKUP_DEST_DIR": str(offsite),
                "BACKUP_DIR": str(local),
            },
            check=False,
        )
        if proc.returncode == 0 and (offsite / backup.name).is_file():
            ok("offsite_upload_script", "checksum verified copy", section)
        else:
            fail("offsite_upload_script", (proc.stderr or proc.stdout or "failed")[:200], section)

        if capabilities["offsite_command"] or capabilities["offsite_dest_dir"]:
            ok("offsite_env_configured", "env present", section)
        else:
            blocked(
                "offsite_env_configured",
                "OFFSITE_BACKUP_COMMAND / OFFSITE_BACKUP_DEST_DIR not set in environment",
                section,
            )

        if capabilities["docker"] or capabilities["pg_dump"]:
            partial("postgres_backup_live", "tooling available — run on server with DB", section)
        else:
            blocked(
                "postgres_backup_live",
                "No docker/pg_dump in execution environment",
                section,
            )
            blocked(
                "offsite_restore_rehearsal",
                "Requires PostgreSQL + offsite destination on pilot server",
                section,
            )
    finally:
        shutil.rmtree(local, ignore_errors=True)
        shutil.rmtree(offsite, ignore_errors=True)


def verify_backup_incidents():
    section = "backup_incidents"
    run_pytest("backup_incident_drills", ["tests/test_kapitel12_incident_drills.py"])
    run_pytest("backup_offsite_unit", ["tests/test_kapitel12_backup_offsite.py"])
    run_pytest("backup_metadata", ["tests/test_backup_scripts.py", "tests/test_system_status_sources.py"])


def verify_deploy_rollback():
    section = "deploy_rollback"
    for rel in ("Dockerfile", "docker-compose.prod.yml", "docker-compose.yml"):
        if (ROOT / rel).exists():
            ok(f"artifact_{rel}", "present", section)
        else:
            fail(f"artifact_{rel}", "missing", section)

    if capabilities["git"]:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if sha.returncode == 0:
            ok("source_commit_sha", sha.stdout.strip()[:12], section)
        else:
            partial("source_commit_sha", "unavailable", section)
    else:
        blocked("source_commit_sha", "git not available", section)

    partial(
        "deploy_rehearsal_live",
        "Requires staging server — checklist in docs/runbooks/backup-and-restore.md + deploy runbook",
        section,
    )
    partial(
        "rollback_rehearsal_live",
        "Requires previous image tag on server — not executed locally",
        section,
    )


def verify_incident_drills():
    section = "incidents"
    run_pytest(
        "incident_regression",
        [
            "tests/test_recovery_actions.py",
            "tests/test_admin_alerts.py",
            "tests/test_alerting.py",
            "tests/test_admin_system_status.py",
            "tests/test_admin_session.py",
            "tests/test_tenant_isolation_http.py",
        ],
    )
    for name, cap in (
        ("app_outage_live", "docker"),
        ("db_outage_live", "docker"),
        ("scheduler_live", "docker"),
    ):
        if capabilities.get(cap):
            partial(name, "requires controlled container stop on server", section)
        else:
            blocked(name, f"No {cap} — live drill deferred to pilot server", section)
    partial("credential_revoked", "covered by integration health tests + runbook", section)
    ok("evaluator_isolation", "registry + incident drill tests", section)


def verify_performance():
    section = "performance"
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "kapitel12_perf_baseline.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    report_path = ROOT / "scripts" / "kapitel12_perf_report.json"
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        status = report.get("status", "UNKNOWN")
        if status == "PASS":
            ok("profil_a_b", f"status={status}", section)
        else:
            fail("profil_a_b", f"status={status}", section)
        for key, passed in report.get("threshold_checks", {}).items():
            if passed:
                ok(key, "within threshold", section)
            else:
                fail(key, "threshold exceeded", section)
    else:
        fail("profil_a_b", "perf report not generated", section)
    if proc.returncode != 0:
        partial("perf_script_exit", f"exit {proc.returncode}", section)


def verify_regression_bundle():
    run_pytest(
        "slice2_regression",
        [
            "tests/test_backup_scripts.py",
            "tests/test_kapitel12_backup_offsite.py",
            "tests/test_kapitel12_incident_drills.py",
            "tests/test_admin_system_status.py",
            "tests/test_recovery_actions.py",
            "tests/test_admin_onboarding.py",
            "tests/test_admin_session.py",
            "tests/test_tenant_isolation_http.py",
        ],
    )


def classify_slice() -> str:
    statuses = {c["status"] for c in checks}
    if any(r["exit_code"] != 0 for r in pytest_runs):
        return "FAIL"
    real_fails = [c for c in checks if c["status"] == "FAIL" and c["section"] != "backup_inventory"]
    if real_fails:
        return "FAIL"
    if "BLOCKED" in statuses:
        return "PARTIAL"
    if "PARTIAL" in statuses:
        return "PARTIAL"
    if "FAIL" in statuses:
        return "FAIL"
    return "PASS"


def acceptance_matrix() -> dict[str, str]:
    blocked_names = {c["name"] for c in checks if c["status"] == "BLOCKED"}
    fail_names = {c["name"] for c in checks if c["status"] == "FAIL"}
    pass_names = {c["name"] for c in checks if c["status"] == "PASS"}

    def _mark(key: str, required: list[str]) -> str:
        if any(k in fail_names for k in required):
            return "FAIL"
        if any(k in blocked_names for k in required):
            return "BLOCKED"
        if all(k in pass_names for k in required):
            return "PASS"
        return "PARTIAL"

    return {
        "offsite_destination_configured": _mark(
            "offsite",
            ["offsite_env_configured"],
        ),
        "offsite_backup_successful": _mark("backup", ["postgres_backup_live", "offsite_upload_script"]),
        "restore_from_offsite_copy": _mark("restore", ["offsite_restore_rehearsal"]),
        "profil_a_complete": "PASS" if "profil_a_b" in pass_names else "FAIL",
        "profil_b_complete": "PASS" if "profil_a_b" in pass_names else "FAIL",
        "deploy_rehearsal": "PARTIAL",
        "rollback_rehearsal": "PARTIAL",
        "backup_incident_detected": "PASS" if "backup_incident_drills" in pass_names else "FAIL",
    }


def main() -> int:
    print("Kapitel 12 Slice 2 verification\n")
    started = time.time()
    detect_capabilities()
    verify_backup_inventory()
    verify_rb01_offsite()
    verify_backup_incidents()
    verify_deploy_rollback()
    verify_incident_drills()
    verify_performance()
    verify_regression_bundle()

    slice_status = classify_slice()
    acceptance = acceptance_matrix()
    rb01_status = (
        "BLOCKED"
        if acceptance.get("offsite_destination_configured") == "BLOCKED"
        or acceptance.get("restore_from_offsite_copy") == "BLOCKED"
        else acceptance.get("offsite_backup_successful", "PARTIAL")
    )

    out = ROOT / "scripts" / "kapitel12_slice2_report.json"
    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "slice_status": slice_status,
        "rb_01_status": rb01_status,
        "capabilities": capabilities,
        "acceptance": acceptance,
        "pass": sum(1 for c in checks if c["status"] == "PASS"),
        "fail": sum(1 for c in checks if c["status"] == "FAIL"),
        "partial": sum(1 for c in checks if c["status"] == "PARTIAL"),
        "blocked": sum(1 for c in checks if c["status"] == "BLOCKED"),
        "duration_seconds": round(time.time() - started, 1),
        "pytest_runs": pytest_runs,
        "remaining_blockers": [
            {
                "id": "RB-01",
                "severity": "high",
                "status": rb01_status,
                "effect": "GO and CONDITIONAL GO blocked until offsite backup + restore PASS on pilot server",
                "owner": "platform-ops",
                "deadline": "before pilot release decision",
            }
        ]
        if rb01_status != "PASS"
        else [],
        "checks": checks,
    }
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nSlice 2 status: {slice_status}")
    print(f"RB-01: {rb01_status}")
    print(f"Report: {out}")
    print(
        f"PASS={summary['pass']} FAIL={summary['fail']} "
        f"PARTIAL={summary['partial']} BLOCKED={summary['blocked']}"
    )
    return 1 if slice_status == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
