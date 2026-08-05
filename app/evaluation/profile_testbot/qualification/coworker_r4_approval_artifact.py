"""R4 live campaign manual-send approval artifact contract (unsigned schema)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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

_APPROVED_AT_CLOCK_SKEW = timedelta(seconds=120)


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


def _normalize_path(value: str | Path | None) -> str:
    if value is None:
        return ""
    try:
        return str(Path(value).resolve()).replace("\\", "/").lower()
    except Exception:
        return str(value).replace("\\", "/").lower()


def _parse_approved_at(raw: Any) -> datetime | None:
    if raw is None or raw == "":
        return None
    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


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
    expected_ai_mode: str = R4_EXECUTE_AI_MODE,
    expected_recipient_allowlist: list[str] | None = None,
    live_eval_recipient_allowlist: list[str] | None = None,
    expected_manifest_path: str | Path | None = None,
    expected_candidates_path: str | Path | None = None,
    expected_human_review_path: str | Path | None = None,
    now_utc: datetime | None = None,
) -> R4ApprovalValidation:
    blockers: list[str] = []
    p = approval.payload
    if p.get("approval_type") != R4_APPROVAL_TYPE:
        blockers.append("approval_type_mismatch")
    if require_manual_approved and p.get("manual_execution_approved") is not True:
        blockers.append("manual_execution_approved_false")
    if p.get("unsigned_example") is True and require_manual_approved:
        blockers.append("unsigned_example_cannot_authorize_execute")
    if require_manual_approved and "unsigned_example" in p and p.get("unsigned_example") is not False:
        if p.get("unsigned_example") is not True:
            blockers.append("unsigned_example_must_be_false_or_absent")
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
    if p.get("ai_mode") != expected_ai_mode:
        blockers.append("ai_mode_mismatch")

    allowlist = [str(x).strip().lower() for x in (p.get("recipient_allowlist") or [])]
    expected_allow = [
        str(x).strip().lower() for x in (expected_recipient_allowlist or allowlist)
    ]
    if expected_recipient_allowlist is not None and allowlist != expected_allow:
        blockers.append("recipient_allowlist_mismatch")
    if live_eval_recipient_allowlist is not None:
        live_set = {str(x).strip().lower() for x in live_eval_recipient_allowlist}
        if not allowlist:
            blockers.append("recipient_allowlist_empty")
        if any(r not in live_set for r in allowlist):
            blockers.append("recipient_not_in_live_eval_allowlist")
        if set(allowlist) - live_set:
            blockers.append("extra_recipient_not_allowlisted")

    if require_manual_approved:
        approved_at = _parse_approved_at(p.get("approved_at"))
        if approved_at is None:
            blockers.append("approved_at_missing_or_invalid")
        else:
            now = now_utc or datetime.now(timezone.utc)
            if approved_at > now + _APPROVED_AT_CLOCK_SKEW:
                blockers.append("approved_at_in_future")

    if expected_manifest_path is not None:
        if _normalize_path(p.get("manifest_path")) != _normalize_path(expected_manifest_path):
            blockers.append("manifest_path_mismatch")
    if expected_candidates_path is not None:
        if _normalize_path(p.get("candidate_package_path")) != _normalize_path(
            expected_candidates_path
        ):
            blockers.append("candidate_package_path_mismatch")
    if expected_human_review_path is not None:
        if _normalize_path(p.get("human_review_path")) != _normalize_path(
            expected_human_review_path
        ):
            blockers.append("human_review_path_mismatch")

    blob = json.dumps(p, ensure_ascii=False)
    if any(m in blob for m in _SECRET_MARKERS):
        blockers.append("secrets_exposed_in_approval_artifact")
    return R4ApprovalValidation(valid=not blockers, blockers=blockers)
