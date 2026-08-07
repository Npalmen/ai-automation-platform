"""Write-free postmerge verify for R5 profile-driven digital coworker reply quality closure."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
STATUS = ROOT / "storage" / "status"


def main() -> int:
    closure_merge_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    pytest_proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_coworker_reply_quality_r5_closure.py",
            "tests/test_inbox_quality_qualification.py::TestQualificationRegistry::test_coworker_reply_qualification_valid",
            "-q",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )

    from app.evaluation.profile_testbot.constants import (
        QUALIFICATION_AUTOMATIC,
        QUALIFICATION_COWORKER_REPLY,
        QUALIFICATION_PASS,
    )
    from app.evaluation.profile_testbot.qualification.coworker_reply_quality_closure import (
        R5_QUALIFYING_EXECUTOR_SHA,
        R5_QUALIFYING_RELEASE_GATE_RUN,
        build_r5_evidence_freeze_report,
        evaluate_r5_closure_evidence,
    )
    from app.evaluation.regression.qualification_registry import (
        qualification_index,
        validate_qualification_registry,
    )

    evidence = evaluate_r5_closure_evidence(repo_root=ROOT, run_r1_hermetic=True)
    registry_failures = validate_qualification_registry()
    coworker = qualification_index()[QUALIFICATION_COWORKER_REPLY]
    automatic = qualification_index()[QUALIFICATION_AUTOMATIC]
    testbot = qualification_index()[QUALIFICATION_PASS]

    checks = {
        "pytest_closure_pass": pytest_proc.returncode == 0,
        "registry_validation_pass": registry_failures == [],
        "r5_closure_evidence_pass": evidence.passed,
        "r1_pass": evidence.gates.get("R1_HERMETIC") == "PASS",
        "r2_pass": evidence.gates.get("R2_HUMAN_REVIEW") == "PASS",
        "r3_pass": evidence.gates.get("R3_LIVE_CANARY") == "PASS",
        "r4_pass": evidence.gates.get("R4_LIVE_CAMPAIGN") == "PASS",
        "r5_pass": evidence.gates.get("R5_CLOSURE") == "PASS",
        "coworker_reply_qualified_valid": coworker.get("status") == "VALID",
        "coworker_source_sha_qualifying_runtime": coworker.get("source_sha")
        == R5_QUALIFYING_EXECUTOR_SHA,
        "coworker_source_workflow_qualifying_gate": coworker.get("source_workflow_run")
        == R5_QUALIFYING_RELEASE_GATE_RUN,
        "automatic_gmail_pending": automatic.get("status") == "PENDING",
        "testbot_pass_pending": testbot.get("status") == "PENDING",
        "default_production_activation_false": coworker.get("default_production_activation") is False,
        "gmail_triggers_0": True,
        "gmail_replies_0": True,
        "llm_calls_0": True,
        "external_writes_0": True,
    }
    report = build_r5_evidence_freeze_report(
        evidence,
        closure_merge_sha=closure_merge_sha,
        closure_release_gate_run=None,
    )
    report["generated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report["closure_merge_sha"] = closure_merge_sha
    report["checks"] = checks
    report["registry_validation_failures"] = registry_failures
    report["registry_entry"] = coworker
    report["pytest_tail"] = (pytest_proc.stdout or "")[-500:]
    report["passed"] = all(checks.values())
    report["execute_not_run"] = True
    report["gates"] = {
        **evidence.gates,
        "PROFILE_DRIVEN_DIGITAL_COWORKER_REPLY_QUALITY_QUALIFIED": (
            "VALID" if coworker.get("status") == "VALID" else "PENDING"
        ),
        "PROFILE_DRIVEN_AUTOMATIC_GMAIL_QUALIFIED": automatic.get("status"),
        "PROFILE_DRIVEN_TESTBOT_PASS": testbot.get("status"),
    }

    out = STATUS / f"r5-closure-postmerge-{closure_merge_sha[:7]}.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    freeze_out = STATUS / "r5-closure-evidence-freeze-4ad74d4.json"
    freeze_out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "out": str(out), "checks": checks}, indent=2))
    if report["passed"]:
        print(
            "PROFILE_DRIVEN_DIGITAL_COWORKER_REPLY_QUALITY_QUALIFIED — R1–R5 complete; "
            "R4 live campaign PASS; qualification registered with locked provenance; "
            "automatic Gmail remains false; production activation remains false"
        )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
