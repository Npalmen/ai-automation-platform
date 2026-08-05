"""R4 live campaign manual-send approval artifact contract (unsigned schema)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_APPROVAL_TYPE,
    R4_EXECUTE_AI_MODE,
    R4_EXECUTION_MODE,
    R4_LIVE_QUALITY_CAMPAIGN_TYPE,
    R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
    R4_LOCKED_CANDIDATE_RUNTIME_SHA,
    R4_LOCKED_MANIFEST_SEMANTIC_HASH,
    R4_LOCKED_REVIEW_ARTIFACT_SHA256,
    R4_NO_SEND_SCENARIO_IDS,
    R4_SEND_MAX,
    R4_SEND_SCENARIO_IDS,
    R4_TENANT_ID,
)

_SECRET_MARKERS = (
    "sk-",
    "refresh_token",
    "client_secret",
    "ADMIN_API_KEY",
    "Authorization",
    "Bearer ",
)


@dataclass
class R4ApprovalArtifact:
    path: Path
    payload: dict[str, Any]
    artifact_hash: str

    @property
    def approved(self) -> bool:
        return (
            self.payload.get("approval_type") == R4_APPROVAL_TYPE
            and self.payload.get("manual_execution_approved") is True
        )


@dataclass
class R4ApprovalValidation:
    valid: bool
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "blockers": self.blockers}


def compute_file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_r4_approval_artifact(path: Path) -> R4ApprovalArtifact:
    payload = json.loads(path.read_text(encoding="utf-8"))
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    ).hexdigest()
    return R4ApprovalArtifact(path=path, payload=payload, artifact_hash=digest)


def build_r4_approval_artifact_example(
    *,
    candidate_runtime_sha: str = R4_LOCKED_CANDIDATE_RUNTIME_SHA,
    executor_runtime_sha: str,
    manifest_path: str,
    candidate_package_path: str,
    human_review_path: str,
    body_hashes: dict[str, str],
    recipient_allowlist: list[str],
) -> dict[str, Any]:
    """Unsigned example structure only — not a signed approval."""
    return {
        "approval_type": R4_APPROVAL_TYPE,
        "manual_execution_approved": False,
        "unsigned_example": True,
        "candidate_runtime_sha": candidate_runtime_sha,
        "executor_runtime_sha": executor_runtime_sha,
        "manifest_path": manifest_path,
        "manifest_semantic_hash": R4_LOCKED_MANIFEST_SEMANTIC_HASH,
        "candidate_package_path": candidate_package_path,
        "candidate_package_semantic_hash": R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
        "human_review_path": human_review_path,
        "human_review_sha256": R4_LOCKED_REVIEW_ARTIFACT_SHA256,
        "send_scenario_ids": list(R4_SEND_SCENARIO_IDS),
        "no_send_scenario_ids": list(R4_NO_SEND_SCENARIO_IDS),
        "body_hashes": body_hashes,
        "human_review_failures": 0,
        "human_review_pending": 0,
        "unresolved_blocking_notes": 0,
        "send_budget": R4_SEND_MAX,
        "no_automatic_retry": True,
        "drafts_allowed": False,
        "recipient_allowlist": recipient_allowlist,
        "tenant_id": R4_TENANT_ID,
        "campaign_type": R4_LIVE_QUALITY_CAMPAIGN_TYPE,
        "execution_mode": R4_EXECUTION_MODE,
        "ai_mode": R4_EXECUTE_AI_MODE,
        "approved_at": None,
        "notes": "UNSIGNED EXAMPLE — do not use for --execute",
    }


def validate_r4_approval_artifact(
    approval: R4ApprovalArtifact,
    *,
    candidate_runtime_sha: str,
    executor_runtime_sha: str,
    manifest_semantic_hash: str,
    candidate_package_semantic_hash: str,
    human_review_sha256: str,
    body_hashes: dict[str, str],
    require_manual_approved: bool = True,
) -> R4ApprovalValidation:
    blockers: list[str] = []
    p = approval.payload
    if p.get("approval_type") != R4_APPROVAL_TYPE:
        blockers.append("approval_type_mismatch")
    if require_manual_approved and p.get("manual_execution_approved") is not True:
        blockers.append("manual_execution_approved_false")
    if p.get("unsigned_example") is True and require_manual_approved:
        blockers.append("unsigned_example_cannot_authorize_execute")
    if p.get("candidate_runtime_sha") != candidate_runtime_sha:
        blockers.append("candidate_runtime_sha_mismatch")
    if p.get("executor_runtime_sha") != executor_runtime_sha:
        blockers.append("executor_runtime_sha_mismatch")
    if p.get("manifest_semantic_hash") != manifest_semantic_hash:
        blockers.append("manifest_semantic_hash_mismatch")
    if p.get("candidate_package_semantic_hash") != candidate_package_semantic_hash:
        blockers.append("candidate_package_semantic_hash_mismatch")
    if p.get("human_review_sha256") != human_review_sha256:
        blockers.append("human_review_sha256_mismatch")
    if list(p.get("send_scenario_ids") or []) != list(R4_SEND_SCENARIO_IDS):
        blockers.append("send_scenario_ids_mismatch")
    if list(p.get("no_send_scenario_ids") or []) != list(R4_NO_SEND_SCENARIO_IDS):
        blockers.append("no_send_scenario_ids_mismatch")
    art_hashes = dict(p.get("body_hashes") or {})
    if set(art_hashes) != set(body_hashes) or any(
        art_hashes.get(k) != v for k, v in body_hashes.items()
    ):
        blockers.append("body_hashes_mismatch")
    if int(p.get("human_review_failures") or 0) != 0:
        blockers.append("human_review_failures!=0")
    if int(p.get("human_review_pending") or 0) != 0:
        blockers.append("human_review_pending!=0")
    if int(p.get("unresolved_blocking_notes") or 0) != 0:
        blockers.append("unresolved_blocking_notes!=0")
    if int(p.get("send_budget") or 0) != R4_SEND_MAX:
        blockers.append("send_budget!=20")
    if p.get("no_automatic_retry") is not True:
        blockers.append("no_automatic_retry_required")
    if p.get("drafts_allowed") is not False:
        blockers.append("drafts_must_be_forbidden")
    if p.get("tenant_id") != R4_TENANT_ID:
        blockers.append("tenant_mismatch")
    if p.get("campaign_type") != R4_LIVE_QUALITY_CAMPAIGN_TYPE:
        blockers.append("campaign_type_mismatch")
    if p.get("execution_mode") != R4_EXECUTION_MODE:
        blockers.append("execution_mode_mismatch")
    blob = json.dumps(p, ensure_ascii=False)
    if any(m in blob for m in _SECRET_MARKERS):
        blockers.append("secrets_exposed_in_approval_artifact")
    return R4ApprovalValidation(valid=not blockers, blockers=blockers)
