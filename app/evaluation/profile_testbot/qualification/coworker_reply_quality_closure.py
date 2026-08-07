"""R5 write-free closure evidence for profile-driven digital coworker reply quality."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.evaluation.profile_testbot.constants import (
    QUALIFICATION_AUTOMATIC,
    QUALIFICATION_COWORKER_REPLY,
    QUALIFICATION_PASS,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_attempt1_orphan import (
    ATTEMPT1_CAMPAIGN_ID,
    attempt1_orphan_record,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R3_QUALIFYING_CAMPAIGN_ID,
    R3_QUALIFYING_SHA,
    R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
    R4_LOCKED_CANDIDATE_RUNTIME_SHA,
    R4_LOCKED_MANIFEST_SEMANTIC_HASH,
    R4_LOCKED_REVIEW_ARTIFACT_SHA256,
)
from app.evaluation.profile_testbot.qualification.hermetic_coworker_reply import (
    HERMETIC_COWORKER_CONTRACT_VERSION,
    run_hermetic_coworker_reply_qualification,
)
from app.evaluation.regression.qualification_registry import qualification_index

R5_QUALIFYING_EXECUTOR_SHA = "4ad74d4ac19011d5edfb8ea160112f649052422d"
R5_QUALIFYING_RELEASE_GATE_RUN = "31220948265"
R5_R4_PASS_CAMPAIGN_ID = "b4dcd6a8-9bda-4ce4-8b63-4e7a54176605"

R5_QUARANTINED_CAMPAIGN_IDS: frozenset[str] = frozenset(
    {
        ATTEMPT1_CAMPAIGN_ID,
        "4d836572-9c27-4eac-9892-a3693801d334",
        "32c6ed26-d030-441a-af52-5b186fae1107",
        "99fa0b7f-1a6b-45aa-bec9-07f54f845de3",
        "af0c2de2-eebe-486e-bb67-3414ac59d1b9",
        "298aeee7-dc72-4614-86eb-8f20566bee2f",
        "462aad8c-8266-4ee7-bc83-3831368a136b",
        "92305703-a8ca-4e91-8b16-c13ebebb6655",
        "8e0fa53a-868f-454f-b40f-2a41f94b2efe",
        "87bb6153-8358-4758-8f64-bac153763170",
        "452e65bd-8d9c-4bb0-a630-31c1f6d87b19",
    }
)

R5_PASS_RECORD_REL = "storage/status/digital-coworker-r4-attempt12-pass-record-4ad74d4.json"
R5_EXECUTION_REPORT_REL = "storage/status/digital-coworker-r4-live-execution-4ad74d4.json"
R5_RECONCILIATION_REL = "storage/status/digital-coworker-r4-reconciliation-4ad74d4.json"
R5_HUMAN_REVIEW_REL = "storage/status/digital-coworker-r4-human-review-scored-b7fd95e.json"
R5_MANIFEST_REL = "storage/status/digital-coworker-r4-manifest-b7fd95e.json"
R5_CANDIDATES_REL = "storage/status/digital-coworker-r4-candidates-b7fd95e.json"
R5_R3_RESULT_DOC = "docs/reply-quality/r3-live-canary-result.md"


@dataclass
class R5ClosureEvidenceResult:
    passed: bool
    blockers: list[str] = field(default_factory=list)
    provenance: dict[str, Any] = field(default_factory=dict)
    gates: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "blockers": self.blockers,
            "provenance": self.provenance,
            "gates": self.gates,
        }


def _repo_root(start: Path | None = None) -> Path:
    if start is not None:
        return start
    return Path(__file__).resolve().parents[4]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_r1_hermetic(*, run_hermetic: bool) -> tuple[bool, dict[str, Any], list[str]]:
    blockers: list[str] = []
    if not run_hermetic:
        return True, {"mode": "frozen_gate_pass_not_rerun"}, []
    result = run_hermetic_coworker_reply_qualification()
    passed = result.overall_status == "PASS" and not result.gate_failures
    if not passed:
        blockers.append("r1_hermetic_qualification_failed")
    return passed, result.to_dict(), blockers


def _verify_r2_human_review(path: Path) -> tuple[bool, dict[str, Any], list[str]]:
    blockers: list[str] = []
    if not path.is_file():
        return False, {}, ["r2_human_review_artifact_missing"]
    review = _load_json(path)
    sha = _sha256_file(path)
    if sha != R4_LOCKED_REVIEW_ARTIFACT_SHA256:
        blockers.append("r2_human_review_sha256_mismatch")
    counts = review.get("status_counts") or {}
    if counts.get("FAIL", 0) != 0 or counts.get("PENDING", 0) != 0:
        blockers.append("r2_human_review_incomplete_or_failed")
    if not review.get("human_review_complete"):
        blockers.append("r2_human_review_not_complete")
    if not review.get("body_hash_bindings_valid"):
        blockers.append("r2_body_hash_bindings_invalid")
    if review.get("manifest_semantic_hash") != R4_LOCKED_MANIFEST_SEMANTIC_HASH:
        blockers.append("r2_manifest_hash_mismatch")
    if review.get("candidate_package_semantic_hash") != R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH:
        blockers.append("r2_candidate_package_hash_mismatch")
    return not blockers, {"artifact_sha256": sha, "status_counts": counts}, blockers


def _verify_r3() -> tuple[bool, dict[str, Any], list[str]]:
    blockers: list[str] = []
    if R3_QUALIFYING_SHA.lower() in {"", "pending"}:
        blockers.append("r3_qualifying_sha_missing")
    if R3_QUALIFYING_CAMPAIGN_ID.lower() in {"", "pending"}:
        blockers.append("r3_qualifying_campaign_missing")
    if R3_QUALIFYING_CAMPAIGN_ID.lower() in {c.lower() for c in R5_QUARANTINED_CAMPAIGN_IDS}:
        blockers.append("r3_campaign_quarantined")
    return not blockers, {
        "qualifying_sha": R3_QUALIFYING_SHA,
        "qualifying_campaign_id": R3_QUALIFYING_CAMPAIGN_ID,
        "doc": R5_R3_RESULT_DOC,
    }, blockers


def _verify_r4_pass_record(record: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if record.get("overall_status") != "PASS":
        blockers.append("r4_pass_record_not_pass")
    if record.get("campaign_id") != R5_R4_PASS_CAMPAIGN_ID:
        blockers.append("r4_campaign_id_mismatch")
    if record.get("candidate_runtime_sha") != R4_LOCKED_CANDIDATE_RUNTIME_SHA:
        blockers.append("r4_candidate_sha_mismatch")
    if record.get("executor_runtime_sha") != R5_QUALIFYING_EXECUTOR_SHA:
        blockers.append("r4_executor_sha_mismatch")
    if record.get("send_passed") != "20/20":
        blockers.append("r4_send_not_20_20")
    if record.get("no_send_passed") != "16/16":
        blockers.append("r4_no_send_not_16_16")
    for key, expected in (
        ("failed", 0),
        ("not_run", 0),
        ("ambiguous", 0),
        ("gmail_replies", 20),
        ("gmail_triggers", 35),
        ("gmail_drafts", 0),
        ("llm_calls", 0),
    ):
        if record.get(key) != expected:
            blockers.append(f"r4_{key}_mismatch")
    if record.get("r4_live_campaign") != "PASS":
        blockers.append("r4_live_campaign_not_pass")
    if record.get("automatic_gmail") is True or record.get("production_activation") is True:
        blockers.append("r4_activation_flags_true")
    if record.get("campaign_id", "").lower() in {c.lower() for c in R5_QUARANTINED_CAMPAIGN_IDS}:
        blockers.append("r4_pass_campaign_quarantined")
    return blockers


def _verify_r4_execution(execution: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if execution.get("overall_status") != "PASS":
        blockers.append("r4_execution_not_pass")
    outcomes = execution.get("scenario_outcomes") or []
    if len(outcomes) != 36:
        blockers.append("r4_scenario_count_not_36")
    if any(o.get("status") == "failed" for o in outcomes):
        blockers.append("r4_execution_has_failed_scenario")
    if any(o.get("status") == "not_run" for o in outcomes):
        blockers.append("r4_execution_has_not_run")
    by_id = {o.get("scenario_id"): o for o in outcomes}
    for sid in ("PTB-DCQ-0007", "PTB-DCQ-0088", "PTB-SEM-0023", "PTB-SEM-0024"):
        row = by_id.get(sid)
        if not row or row.get("status") != "passed":
            blockers.append(f"r4_special_scenario_{sid}_not_passed")
    sem_0023 = by_id.get("PTB-SEM-0023") or {}
    if sem_0023.get("intake_suppression_reason") != "newsletter_disabled":
        blockers.append("r4_sem_0023_suppression_mismatch")
    if sem_0023.get("gmail_sends", 1) != 0:
        blockers.append("r4_sem_0023_scenario_gmail_sends_not_zero")
    return blockers


def _is_quarantine_record(rec: dict[str, Any]) -> bool:
    if rec.get("permanent_quarantine") is True:
        return True
    return (
        rec.get("reuse_blocked") is True
        and rec.get("exclude_from_r4_pass") is True
        and rec.get("resume_forbidden") is True
    )


def _verify_quarantine(status_dir: Path) -> list[str]:
    blockers: list[str] = []
    attempt1 = attempt1_orphan_record().to_dict()
    if not attempt1.get("exclude_from_r4_pass") or not attempt1.get("reuse_blocked"):
        blockers.append("attempt1_quarantine_flags_missing")
    for n in range(2, 12):
        path = status_dir / f"digital-coworker-r4-attempt{n}-orphan-registry.json"
        if not path.is_file():
            blockers.append(f"attempt{n}_orphan_registry_missing")
            continue
        rec = _load_json(path)
        if not _is_quarantine_record(rec):
            blockers.append(f"attempt{n}_quarantine_flags_missing")
        if rec.get("exclude_from_r4_pass") is not True:
            blockers.append(f"attempt{n}_exclude_from_r4_pass_missing")
    return blockers


def _verify_locked_artifacts(
    *,
    manifest_path: Path,
    candidates_path: Path,
) -> tuple[list[str], dict[str, Any]]:
    blockers: list[str] = []
    provenance: dict[str, Any] = {}
    if not manifest_path.is_file():
        blockers.append("manifest_artifact_missing")
    else:
        manifest = _load_json(manifest_path)
        provenance["manifest_semantic_hash"] = manifest.get("manifest_semantic_hash")
        if manifest.get("manifest_semantic_hash") != R4_LOCKED_MANIFEST_SEMANTIC_HASH:
            blockers.append("manifest_hash_mismatch")
    if not candidates_path.is_file():
        blockers.append("candidates_artifact_missing")
    else:
        candidates = _load_json(candidates_path)
        provenance["candidate_package_semantic_hash"] = candidates.get(
            "candidate_package_semantic_hash"
        )
        if candidates.get("candidate_package_semantic_hash") != R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH:
            blockers.append("candidate_package_hash_mismatch")
    return blockers, provenance


def _verify_registry_pre_state(
    *,
    expected_sha: str,
    expected_run: str,
    allow_already_valid: bool,
) -> list[str]:
    blockers: list[str] = []
    entry = qualification_index().get(QUALIFICATION_COWORKER_REPLY) or {}
    status = str(entry.get("status") or "PENDING")
    source_sha = str(entry.get("source_sha") or "")
    source_run = str(entry.get("source_workflow_run") or "")
    if status == "VALID":
        if not allow_already_valid:
            blockers.append("registry_already_valid")
        elif source_sha != expected_sha or source_run != expected_run:
            blockers.append("registry_conflicting_valid_provenance")
    elif status != "PENDING":
        blockers.append(f"registry_unexpected_status_{status}")
    if qualification_index().get(QUALIFICATION_AUTOMATIC, {}).get("status") == "VALID":
        blockers.append("automatic_gmail_qualification_must_remain_pending")
    if qualification_index().get(QUALIFICATION_PASS, {}).get("status") == "VALID":
        blockers.append("testbot_pass_qualification_must_remain_pending")
    return blockers


def evaluate_r5_closure_evidence(
    *,
    repo_root: Path | None = None,
    status_dir: Path | None = None,
    run_r1_hermetic: bool = True,
    allow_registry_already_valid: bool = True,
    pass_record: dict[str, Any] | None = None,
    execution_report: dict[str, Any] | None = None,
) -> R5ClosureEvidenceResult:
    """Evaluate frozen R1–R4 evidence for R5 closure (write-free)."""
    root = _repo_root(repo_root)
    status = status_dir or (root / "storage" / "status")
    blockers: list[str] = []
    provenance: dict[str, Any] = {
        "qualifying_executor_sha": R5_QUALIFYING_EXECUTOR_SHA,
        "qualifying_release_gate_run": R5_QUALIFYING_RELEASE_GATE_RUN,
        "r4_pass_campaign_id": R5_R4_PASS_CAMPAIGN_ID,
        "candidate_runtime_sha": R4_LOCKED_CANDIDATE_RUNTIME_SHA,
    }

    pass_path = root / "storage" / "status" / "digital-coworker-r4-attempt12-pass-record-4ad74d4.json"
    exec_path = root / "storage" / "status" / "digital-coworker-r4-live-execution-4ad74d4.json"
    review_path = root / "storage" / "status" / "digital-coworker-r4-human-review-scored-b7fd95e.json"
    manifest_path = root / "storage" / "status" / "digital-coworker-r4-manifest-b7fd95e.json"
    candidates_path = root / "storage" / "status" / "digital-coworker-r4-candidates-b7fd95e.json"

    if pass_record is None:
        if not pass_path.is_file():
            blockers.append("r4_pass_record_missing")
            pass_record = {}
        else:
            pass_record = _load_json(pass_path)
    if execution_report is None:
        if not exec_path.is_file():
            blockers.append("r4_execution_report_missing")
            execution_report = {}
        else:
            execution_report = _load_json(exec_path)

    blockers.extend(_verify_r4_pass_record(pass_record))
    blockers.extend(_verify_r4_execution(execution_report))
    blockers.extend(_verify_quarantine(status))

    artifact_blockers, artifact_prov = _verify_locked_artifacts(
        manifest_path=manifest_path,
        candidates_path=candidates_path,
    )
    blockers.extend(artifact_blockers)
    provenance.update(artifact_prov)

    r2_pass, r2_prov, r2_blockers = _verify_r2_human_review(review_path)
    blockers.extend(r2_blockers)
    provenance["r2"] = r2_prov

    r3_pass, r3_prov, r3_blockers = _verify_r3()
    blockers.extend(r3_blockers)
    provenance["r3"] = r3_prov

    r1_pass, r1_prov, r1_blockers = _verify_r1_hermetic(run_hermetic=run_r1_hermetic)
    blockers.extend(r1_blockers)
    provenance["r1"] = r1_prov

    blockers.extend(
        _verify_registry_pre_state(
            expected_sha=R5_QUALIFYING_EXECUTOR_SHA,
            expected_run=R5_QUALIFYING_RELEASE_GATE_RUN,
            allow_already_valid=allow_registry_already_valid,
        )
    )

    if R5_R4_PASS_CAMPAIGN_ID.lower() in {c.lower() for c in R5_QUARANTINED_CAMPAIGN_IDS}:
        blockers.append("r4_pass_in_quarantine_set")

    gates = {
        "R1_HERMETIC": "PASS" if r1_pass else "FAIL",
        "R2_HUMAN_REVIEW": "PASS" if r2_pass else "FAIL",
        "R3_LIVE_CANARY": "PASS" if r3_pass else "FAIL",
        "R4_LIVE_CAMPAIGN": "PASS" if not any(b.startswith("r4_") for b in blockers) else "FAIL",
        "R5_CLOSURE": "PASS" if not blockers else "PENDING",
        "automatic_gmail": "false",
        "production_activation": "false",
    }
    return R5ClosureEvidenceResult(
        passed=not blockers,
        blockers=sorted(set(blockers)),
        provenance=provenance,
        gates=gates,
    )


def build_r5_evidence_freeze_report(
    result: R5ClosureEvidenceResult,
    *,
    closure_merge_sha: str | None = None,
    closure_release_gate_run: str | None = None,
) -> dict[str, Any]:
    """Build frozen evidence artifact (write-free metadata only)."""
    report = result.to_dict()
    report["evidence_artifacts"] = {
        "r4_pass_record": R5_PASS_RECORD_REL,
        "r4_execution": R5_EXECUTION_REPORT_REL,
        "r4_reconciliation": R5_RECONCILIATION_REL,
        "r2_human_review": R5_HUMAN_REVIEW_REL,
        "r3_result_doc": R5_R3_RESULT_DOC,
        "r1_contract": HERMETIC_COWORKER_CONTRACT_VERSION,
    }
    report["quarantined_campaign_ids"] = sorted(R5_QUARANTINED_CAMPAIGN_IDS)
    report["registry_target"] = {
        "id": QUALIFICATION_COWORKER_REPLY,
        "status": "VALID",
        "source_sha": R5_QUALIFYING_EXECUTOR_SHA,
        "source_workflow_run": R5_QUALIFYING_RELEASE_GATE_RUN,
    }
    if closure_merge_sha:
        report["closure_postmerge_evidence"] = {
            "closure_merge_sha": closure_merge_sha,
            "closure_release_gate_run": closure_release_gate_run,
            "note": "closure PR evidence only; does not replace registry provenance",
        }
    report["external_writes"] = 0
    report["gmail_triggers"] = 0
    report["gmail_replies"] = 0
    report["llm_calls"] = 0
    return report
