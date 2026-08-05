"""R4-only hold→pending materialization for PTB-DCQ-0088 reviewed candidates.

Does NOT call or generalize R3 hold override. Never returns execution_allowed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_0088_CONTRACT_ID,
    R4_0088_REVIEWED_BODY_HASH,
    R4_EXECUTE_AI_MODE,
    R4_EXECUTION_MODE,
    R4_LIVE_QUALITY_CAMPAIGN_TYPE,
    R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH,
    R4_LOCKED_REVIEW_ARTIFACT_SHA256,
    R4_TENANT_ID,
)

R4_0088_SCENARIO_ID = "PTB-DCQ-0088"

R4_0088_BLOCKED_RISK_TAGS: frozenset[str] = frozenset(
    {
        "prompt_injection",
        "prompt-injection",
        "secrets",
        "secret_exposure",
        "fraud",
        "payment",
        "bank",
        "legal",
        "legal_commitment",
        "privacy",
        "deletion",
        "gdpr",
        "threat",
        "threats",
        "violence",
        "unsafe_electrical",
        "electrical_emergency",
        "unknown_high_risk",
        "unknown_critical_risk",
        "high_risk",
        "critical_risk",
    }
)


@dataclass
class R4HoldMaterializationResolution:
    eligible: bool
    authorization: str | None
    blockers: list[str] = field(default_factory=list)
    base_policy_authorization: str | None = None
    contract_id: str = R4_0088_CONTRACT_ID
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "authorization": self.authorization,
            "blockers": self.blockers,
            "base_policy_authorization": self.base_policy_authorization,
            "contract_id": self.contract_id,
            "details": self.details,
        }


def resolve_r4_0088_hold_materialization(
    *,
    scenario_id: str,
    base_authorization: str | None,
    reviewed_body_hash: str | None,
    candidate_package_semantic_hash: str | None,
    human_review_artifact_hash: str | None,
    campaign_type: str | None = None,
    execution_mode: str | None = None,
    ai_mode: str | None = None,
    tenant_id: str | None = None,
    risk_tags: list[str] | tuple[str, ...] | None = None,
    policy_reasons: list[str] | tuple[str, ...] | None = None,
) -> R4HoldMaterializationResolution:
    blockers: list[str] = []
    if scenario_id != R4_0088_SCENARIO_ID:
        return R4HoldMaterializationResolution(
            eligible=False,
            authorization=None,
            blockers=["scenario_not_r4_0088"],
            base_policy_authorization=base_authorization,
        )
    if tenant_id not in (None, R4_TENANT_ID):
        blockers.append("tenant_mismatch")
    if campaign_type not in (None, R4_LIVE_QUALITY_CAMPAIGN_TYPE):
        blockers.append("campaign_type_mismatch")
    if execution_mode not in (None, R4_EXECUTION_MODE):
        blockers.append("execution_mode_mismatch")
    if ai_mode not in (None, R4_EXECUTE_AI_MODE, "live_llm"):
        blockers.append("ai_mode_mismatch")
    if base_authorization != "hold_for_review":
        blockers.append(f"base_policy_not_hold:{base_authorization}")
    if reviewed_body_hash != R4_0088_REVIEWED_BODY_HASH:
        blockers.append("r4_0088_body_hash_mismatch")
    if candidate_package_semantic_hash != R4_LOCKED_CANDIDATE_PACKAGE_SEMANTIC_HASH:
        blockers.append("candidate_package_semantic_hash_mismatch")
    if human_review_artifact_hash != R4_LOCKED_REVIEW_ARTIFACT_SHA256:
        blockers.append("human_review_artifact_hash_mismatch")

    tags = {str(t).lower() for t in (risk_tags or [])}
    blocked = tags & {t.lower() for t in R4_0088_BLOCKED_RISK_TAGS}
    if blocked:
        blockers.append(f"blocked_risk_tags:{sorted(blocked)}")

    if blockers:
        return R4HoldMaterializationResolution(
            eligible=False,
            authorization=None,
            blockers=blockers,
            base_policy_authorization=base_authorization,
            details={"policy_reasons": list(policy_reasons or []), "risk_tags": list(tags)},
        )

    return R4HoldMaterializationResolution(
        eligible=True,
        authorization="approval_required",
        blockers=[],
        base_policy_authorization=base_authorization,
        details={
            "preserves_base_hold": True,
            "never_execution_allowed": True,
            "r3_override_reused": False,
            "audit_trail": [
                "base_policy_hold",
                "r4_reviewed_candidate_contract",
                "pending_approval",
                "explicit_approval",
                "gmail_execution",
            ],
        },
    )


def should_materialize_r4_0088_action_dispatch_despite_hold(
    *,
    scenario_id: str,
    resolution: R4HoldMaterializationResolution | None,
) -> bool:
    return (
        scenario_id == R4_0088_SCENARIO_ID
        and resolution is not None
        and resolution.eligible
        and resolution.authorization == "approval_required"
    )


def should_materialize_r4_0088_from_job(
    *,
    job: Any,
    policy_payload: dict[str, Any] | None = None,
) -> bool:
    """Orchestrator hook: allow ACTION_DISPATCH for R4 0088 hold→pending only."""
    policy_payload = policy_payload or {}
    if policy_payload.get("decision") != "hold_for_review":
        return False
    input_data = getattr(job, "input_data", None) or {}
    live = input_data.get("live_eval") or {}
    snap = live.get("r4_reviewed_body_snapshot") or {}
    scenario_id = str(
        snap.get("scenario_id")
        or live.get("scenario_id")
        or input_data.get("scenario_id")
        or ""
    )
    if scenario_id != R4_0088_SCENARIO_ID:
        return False
    resolution = resolve_r4_0088_hold_materialization(
        scenario_id=scenario_id,
        base_authorization="hold_for_review",
        reviewed_body_hash=str(snap.get("reviewed_body_hash") or ""),
        candidate_package_semantic_hash=str(snap.get("candidate_package_semantic_hash") or ""),
        human_review_artifact_hash=str(snap.get("human_review_artifact_hash") or ""),
        campaign_type=str(snap.get("campaign_type") or live.get("campaign_type") or ""),
        execution_mode=str(snap.get("execution_mode") or live.get("execution_mode") or ""),
        ai_mode=str(live.get("ai_mode") or snap.get("ai_mode") or ""),
        tenant_id=str(getattr(job, "tenant_id", "") or ""),
    )
    return should_materialize_r4_0088_action_dispatch_despite_hold(
        scenario_id=scenario_id,
        resolution=resolution,
    )


def apply_r4_0088_hold_materialization_to_action(
    action: dict[str, Any],
    *,
    resolution: R4HoldMaterializationResolution,
) -> dict[str, Any]:
    """Annotate action for pending approval only — never execution_allowed."""
    if not resolution.eligible:
        return action
    out = dict(action)
    out["_needs_approval"] = True
    out["_authorization"] = "approval_required"
    out["_skip"] = False
    out["_r4_hold_materialization"] = resolution.to_dict()
    out["_r4_contract_id"] = R4_0088_CONTRACT_ID
    out["_r4_0088_materialized"] = True
    if out.get("_authorization") == "execution_allowed":
        out["_authorization"] = "approval_required"
    return out


def apply_r4_0088_hold_materialization_from_job(
    *,
    job: Any,
    action: dict[str, Any],
    policy_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy_payload = policy_payload or {}
    input_data = getattr(job, "input_data", None) or {}
    live = input_data.get("live_eval") or {}
    snap = live.get("r4_reviewed_body_snapshot") or {}
    scenario_id = str(
        snap.get("scenario_id")
        or live.get("scenario_id")
        or input_data.get("scenario_id")
        or ""
    )
    resolution = resolve_r4_0088_hold_materialization(
        scenario_id=scenario_id,
        base_authorization="hold_for_review",
        reviewed_body_hash=str(snap.get("reviewed_body_hash") or ""),
        candidate_package_semantic_hash=str(snap.get("candidate_package_semantic_hash") or ""),
        human_review_artifact_hash=str(snap.get("human_review_artifact_hash") or ""),
        campaign_type=str(snap.get("campaign_type") or live.get("campaign_type") or ""),
        execution_mode=str(snap.get("execution_mode") or live.get("execution_mode") or ""),
        ai_mode=str(live.get("ai_mode") or ""),
        tenant_id=str(getattr(job, "tenant_id", "") or ""),
    )
    if not resolution.eligible:
        return action
    return apply_r4_0088_hold_materialization_to_action(action, resolution=resolution)
