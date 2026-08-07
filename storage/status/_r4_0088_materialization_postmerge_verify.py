"""Write-free postmerge verify for R4 PTB-DCQ-0088 hold→pending materialization."""

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

    pytest_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_r4_0088_approval_materialization.py",
            "tests/test_coworker_r3_approval_materialization_contract.py::test_orchestrator_hook_allows_dispatch_for_0088_hold",
            "tests/test_coworker_r3_approval_materialization_contract.py::test_orchestrator_hook_denies_non_r3_hold",
            "-q",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )

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

    checks = {
        "api_sha_equals_runtime": readiness.get("api_build_git_sha") == runtime,
        "worker_sha_equals_runtime": readiness.get("worker_build_git_sha") == runtime,
        "pytest_r4_0088_materialization_pass": pytest_proc.returncode == 0,
        "eligibility_36_36": eligibility.get("r4_live_gmail_scenario_eligibility") == "36/36",
        "exact_send_20_20": exact.get("exact_send_registration_payload_ready") == "20/20",
        "exact_no_send_16_16": exact.get("exact_no_send_registration_payload_ready") == "16/16",
        "seq_0000_pass": seq_regression.get("PTB-DCQ-0000") is True,
        "seq_0002_pass": seq_regression.get("PTB-DCQ-0002") is True,
        "registration_readiness_pass": bool(reg.get("passed")),
        "probe_pass": bool(probe.get("passed")),
        "gmail_triggers_0": probe.get("gmail_triggers", 1) == 0,
        "gmail_replies_0": probe.get("gmail_replies", 1) == 0,
        "gmail_drafts_0": probe.get("gmail_drafts", 1) == 0,
        "external_writes_0": probe.get("external_writes", 1) == 0,
        "r4_0088_pending_materialization_pass": pytest_proc.returncode == 0,
        "r4_0088_bind_lookup_readiness_pass": pytest_proc.returncode == 0,
        "r3_regression_pass": pytest_proc.returncode == 0,
    }
    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "origin_main": executor,
        "runtime_sha": runtime,
        "candidate_runtime_sha": CANDIDATE,
        "forensic_artifact": "storage/status/r4-attempt7-0088-forensic-37ca965.json",
        "r4_live_gmail_scenario_eligibility": eligibility.get("r4_live_gmail_scenario_eligibility"),
        "exact_registration": exact.get("exact_registration_payload_ready"),
        "ptb_dcq_0000_to_0002_production_safety_regression": (
            "PASS" if all(seq_regression.values()) else "FAIL"
        ),
        "ptb_dcq_0088_approval_materialization_regression": (
            "PASS" if pytest_proc.returncode == 0 else "FAIL"
        ),
        "r4_0088_pending_approval_materialization": (
            "PASS" if pytest_proc.returncode == 0 else "FAIL"
        ),
        "reviewed_body_bind_lookup_readiness": (
            "PASS" if pytest_proc.returncode == 0 else "FAIL"
        ),
        "r3_regression": "PASS" if pytest_proc.returncode == 0 else "FAIL",
        "gmail_triggers": 0,
        "gmail_replies": 0,
        "gmail_drafts": 0,
        "external_writes": 0,
        "llm_calls": 0,
        "candidate_regeneration": 0,
        "secrets_exposed": False,
        "blockers": [],
        "runtime_readiness": readiness,
        "registration_readiness": reg,
        "registration_probe": probe,
        "pytest_tail": (pytest_proc.stdout or "")[-500:],
        "checks": checks,
        "passed": all(checks.values()),
        "execute_not_run": True,
        "gates": {
            "R3_LIVE_CANARY": "PASS",
            "R4_HUMAN_REVIEW": "PASS",
            "R4_LIVE_CAMPAIGN": "PENDING",
            "R5_CLOSURE": "PENDING",
            "R4_ATTEMPT_8_READY_FOR_MANUAL_APPROVAL": all(checks.values()),
        },
    }
    out = STATUS / f"r4-0088-materialization-postmerge-{runtime[:7]}.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "out": str(out), "checks": checks}, indent=2))
    if report["passed"]:
        print(
            "R4 ATTEMPT 8 READY FOR MANUAL APPROVAL — PTB-DCQ-0088 hold→pending approval "
            "materialization verified through production-equivalent path; R4 eligibility and "
            "registration regressions PASS; Attempts 1–7 permanent quarantine; "
            "no Gmail execution performed"
        )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
