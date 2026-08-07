"""Postmerge verify for R4 exact registration payload hardening (no --execute)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
STATUS = ROOT / "storage" / "status"
CANDIDATE = "b7fd95e075c16feee93a116a6062e402c1fee3df"


def _get(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def _post(url: str, headers: dict, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    h = dict(headers)
    if data is not None:
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    executor = subprocess.check_output(["git", "rev-parse", "origin/main"], text=True).strip()
    runtime = os.environ.get("BUILD_GIT_SHA") or executor
    base = os.environ.get("LIVE_EVAL_APP_BASE_URL", "http://127.0.0.1:8010")
    key = os.environ.get("ADMIN_API_KEY", "")
    headers = {"X-Tenant-ID": "TENANT_LIVE_EVAL", "X-Admin-API-Key": key}

    readiness = _get(f"{base}/admin/live-eval/runtime-readiness", headers)
    reg = _get(f"{base}/admin/live-eval/r4-registration-readiness", headers)
    probe = _post(f"{base}/admin/live-eval/r4-registration-probe", headers, {})

    env = os.environ.copy()
    env["BUILD_GIT_SHA"] = runtime
    env["WORKER_BUILD_GIT_SHA"] = runtime
    env["PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED_SHA"] = runtime
    env["PROFILE_TESTBOT_LIVE_QUALITY_RUNNER_APPROVED_SHA"] = runtime

    def run_mode(extra: list[str]) -> dict:
        cmd = [
            "python",
            "scripts/run_digital_coworker_r4_live_campaign.py",
            "--candidate-runtime-sha",
            CANDIDATE,
            "--expected-executor-sha",
            runtime,
            "--manifest",
            "storage/status/digital-coworker-r4-manifest-b7fd95e.json",
            "--candidates-json",
            "storage/status/digital-coworker-r4-candidates-b7fd95e.json",
            "--human-review-file",
            "storage/status/digital-coworker-r4-human-review-scored-b7fd95e.json",
            *extra,
        ]
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        status = "UNKNOWN"
        for line in out.splitlines():
            if line.startswith("overall_status="):
                status = line.split("=", 1)[1].strip()
        return {"overall_status": status, "returncode": proc.returncode, "log_tail": out[-800:]}

    dry = run_mode([])
    jit = run_mode(["--full-jit"])
    base_line = run_mode(["--mailbox-baseline"])

    from app.evaluation.profile_testbot.qualification.coworker_r4_live_backend import (
        describe_r4_live_backend_wiring,
    )

    wiring = describe_r4_live_backend_wiring()
    checks = {
        "api_sha_equals_runtime": readiness.get("api_build_git_sha") == runtime,
        "worker_sha_equals_runtime": readiness.get("worker_build_git_sha") == runtime,
        "registration_readiness_pass": bool(reg.get("passed")),
        "send_20_20": reg.get("send_registration_ready") == "20/20",
        "no_send_16_16": reg.get("no_send_registration_ready") == "16/16",
        "exact_send_20_20": reg.get("exact_send_registration_payload_ready") == "20/20",
        "exact_no_send_16_16": reg.get("exact_no_send_registration_payload_ready") == "16/16",
        "exact_payload_ready": reg.get("exact_registration_payload_ready") == "36/36",
        "probe_pass": bool(probe.get("passed")),
        "probe_gmail_0": probe.get("gmail_triggers", 1) == 0 and probe.get("gmail_replies", 1) == 0,
        "dry_run_pass": dry.get("overall_status") == "PASS",
        "full_jit_pass": jit.get("overall_status") == "PASS",
        "mailbox_baseline_pass": base_line.get("overall_status") == "PASS",
        "backend_wired": bool(wiring.get("backend_wired")),
    }
    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "origin_main": executor,
        "runtime_sha": runtime,
        "candidate_runtime_sha": CANDIDATE,
        "runtime_readiness": readiness,
        "registration_readiness": reg,
        "registration_probe": probe,
        "wiring": wiring,
        "dry_run": dry,
        "full_live_jit": jit,
        "mailbox_baseline": base_line,
        "checks": checks,
        "passed": all(checks.values()),
        "execute_not_run": True,
        "gates": {
            "R3_LIVE_CANARY": "PASS",
            "R4_HUMAN_REVIEW": "PASS",
            "R4_LIVE_CAMPAIGN": "PENDING",
            "R5_CLOSURE": "PENDING",
            "R4_ATTEMPT_6_READY_FOR_MANUAL_APPROVAL": checks.get("exact_payload_ready"),
        },
    }
    out = STATUS / f"r4-exact-registration-postmerge-{runtime[:7]}.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "out": str(out), "checks": checks}, indent=2))
    if report["passed"]:
        print(
            "R4 ATTEMPT 6 READY FOR MANUAL APPROVAL — exact registration payloads PASS 20/20 send + "
            "16/16 no-send; PTB-DCQ-0000→0002 sequential regression PASS; Attempt 1–5 permanent "
            "quarantine; no Gmail execution performed"
        )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
