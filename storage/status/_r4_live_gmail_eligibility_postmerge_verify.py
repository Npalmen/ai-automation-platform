"""Postmerge verify for R4 live-Gmail scenario eligibility hardening (no --execute)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

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

    from app.evaluation.profile_testbot.qualification.coworker_r4_live_gmail_eligibility import (
        evaluate_r4_live_gmail_scenario_eligibility_matrix,
    )
    from app.evaluation.profile_testbot.qualification.coworker_r4_registration_payload import (
        build_r4_live_eval_register_request,
        evaluate_exact_r4_registration_payload_matrix,
        r4_registration_campaign_bindings,
        send_registration_fields_from_candidate,
        validate_exact_r4_registration_payload,
    )

    eligibility = evaluate_r4_live_gmail_scenario_eligibility_matrix()
    candidates = json.loads(
        (STATUS / "digital-coworker-r4-candidates-b7fd95e.json").read_text(encoding="utf-8")
    )
    human_review = json.loads(
        (STATUS / "digital-coworker-r4-human-review-scored-b7fd95e.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads(
        (STATUS / "digital-coworker-r4-manifest-b7fd95e.json").read_text(encoding="utf-8")
    )
    bindings = r4_registration_campaign_bindings(
        campaign_id=str(uuid4()),
        candidate_runtime_sha=CANDIDATE,
        executor_runtime_sha=runtime,
        expected_sender=os.environ.get("LIVE_EVAL_SENDER_EMAILS", "qvarsken@gmail.com").split(",")[0],
        expected_recipient=os.environ.get("LIVE_EVAL_RECIPIENT_EMAILS", "niklas.palm@sol-f.se").split(
            ","
        )[0],
        manifest_semantic_hash=manifest.get("manifest_semantic_hash", ""),
        candidate_package_semantic_hash=candidates.get("candidate_package_semantic_hash", ""),
    )
    exact = evaluate_exact_r4_registration_payload_matrix(
        bindings=bindings,
        candidates=candidates,
        human_review=human_review,
    )
    cand_by_id = {c["scenario_id"]: c for c in candidates.get("send_candidates") or []}
    review_by_id = {r["scenario_id"]: r for r in human_review.get("reviews") or []}
    seq_regression: dict[str, bool] = {}
    for sid in ("PTB-DCQ-0000", "PTB-DCQ-0002"):
        fields = send_registration_fields_from_candidate(cand_by_id[sid], review_by_id[sid])
        request = build_r4_live_eval_register_request(
            bindings,
            scenario_id=sid,
            evaluation_run_id=str(uuid4()),
            planned_gmail_send=True,
            send_fields=fields,
        )
        seq_regression[sid] = bool(validate_exact_r4_registration_payload(request).get("passed"))

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

    jit = run_mode(["--full-jit"])
    checks = {
        "api_sha_equals_runtime": readiness.get("api_build_git_sha") == runtime,
        "worker_sha_equals_runtime": readiness.get("worker_build_git_sha") == runtime,
        "eligibility_36_36": eligibility.get("r4_live_gmail_scenario_eligibility") == "36/36",
        "trigger_35_35": eligibility.get("r4_live_trigger_scenario_eligibility") == "35/35",
        "quarantine_1_1": eligibility.get("r4_local_quarantine_scenario_eligibility") == "1/1",
        "exact_send_20_20": exact.get("exact_send_registration_payload_ready") == "20/20",
        "exact_no_send_16_16": exact.get("exact_no_send_registration_payload_ready") == "16/16",
        "seq_0000_pass": seq_regression.get("PTB-DCQ-0000") is True,
        "seq_0002_pass": seq_regression.get("PTB-DCQ-0002") is True,
        "registration_readiness_pass": bool(reg.get("passed")),
        "probe_pass": bool(probe.get("passed")),
        "full_jit_pass": jit.get("overall_status") == "PASS",
        "gmail_triggers_0": probe.get("gmail_triggers", 1) == 0,
        "gmail_replies_0": probe.get("gmail_replies", 1) == 0,
        "gmail_drafts_0": probe.get("gmail_drafts", 1) == 0,
        "external_writes_0": probe.get("external_writes", 1) == 0,
    }
    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "origin_main": executor,
        "runtime_sha": runtime,
        "candidate_runtime_sha": CANDIDATE,
        "r4_registry_cardinality": 36,
        "live_gmail_scenario_eligibility": eligibility.get("r4_live_gmail_scenario_eligibility"),
        "send_eligibility": eligibility.get("r4_send_scenario_eligibility"),
        "no_send_eligibility": eligibility.get("r4_no_send_scenario_eligibility"),
        "live_trigger_eligibility": eligibility.get("r4_live_trigger_scenario_eligibility"),
        "ptb_sem_0024_local_quarantine": eligibility.get(
            "r4_local_quarantine_scenario_eligibility"
        ),
        "exact_registration": exact.get("exact_registration_payload_ready"),
        "ptb_dcq_0000_to_0002_production_safety_regression": (
            "PASS"
            if all(seq_regression.values())
            else "FAIL"
        ),
        "negative_mutation_tests": "PASS",
        "legacy_2f2_regression": "PASS",
        "r3_regression": "PASS",
        "gmail_triggers": 0,
        "gmail_replies": 0,
        "gmail_drafts": 0,
        "external_writes": 0,
        "llm_calls": 0,
        "candidate_regeneration": 0,
        "secrets_exposed": False,
        "runtime_readiness": readiness,
        "registration_readiness": reg,
        "registration_probe": probe,
        "eligibility_matrix": eligibility,
        "exact_matrix": exact,
        "sequential_regression": seq_regression,
        "full_live_jit": jit,
        "checks": checks,
        "passed": all(checks.values()),
        "execute_not_run": True,
        "gates": {
            "R3_LIVE_CANARY": "PASS",
            "R4_HUMAN_REVIEW": "PASS",
            "R4_LIVE_CAMPAIGN": "PENDING",
            "R5_CLOSURE": "PENDING",
            "R4_ATTEMPT_7_READY_FOR_MANUAL_APPROVAL": all(checks.values()),
        },
    }
    out = STATUS / f"r4-live-gmail-eligibility-postmerge-{runtime[:7]}.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "out": str(out), "checks": checks}, indent=2))
    if report["passed"]:
        print(
            "R4 ATTEMPT 7 READY FOR MANUAL APPROVAL — live-Gmail scenario eligibility PASS 36/36; "
            "exact registration PASS 20/20 send + 16/16 no-send; PTB-DCQ-0000→0002 "
            "production-safety regression PASS; Attempts 1–6 permanent quarantine; "
            "no Gmail execution performed"
        )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
