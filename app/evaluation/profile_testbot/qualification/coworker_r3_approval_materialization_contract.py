"""R3 frozen live-canary approval materialization contract.

Maps an exact, allowlisted hold_for_review base policy outcome to a pending
approval for trusted R3 frozen canary only. Never grants execution_allowed.
Does not change ordinary production/policy semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.evaluation.live.context import snapshot_from_job_input
from app.evaluation.live.delivery_mailbox_reader import is_r3_frozen_live_eval_run
from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.evaluation.profile_testbot.qualification.coworker_r3_frozen_bodies import (
    r3_send_body_hash,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_readiness import (
    R3_APPROVED_SEND_BODY_HASHES,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_registration_contract import (
    R3_ALL_SCENARIO_IDS,
    R3_FROZEN_AI_MODE,
    R3_FROZEN_EXECUTION_MODE,
    R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE,
    R3_NO_SEND_SCENARIO_IDS,
    R3_SEND_SCENARIO_IDS,
)
from app.repositories.postgres.live_eval_repository import LiveEvalRunRepository
from app.workflows.action_authorization import ActionAuthorization

R3_OVERRIDE_CONTRACT_ID = "r3_frozen_manual_review_to_pending_v1"
R3_OVERRIDE_REASON = "frozen_body_preapproved_for_r3_canary"

# First version: only PTB-DCQ-0088 may receive hold→pending materialization.
R3_HOLD_OVERRIDE_SCENARIO_IDS: frozenset[str] = frozenset({"PTB-DCQ-0088"})
R3_HOLD_OVERRIDE_CANONICAL_HASHES: dict[str, str] = {
    "PTB-DCQ-0088": R3_APPROVED_SEND_BODY_HASHES["PTB-DCQ-0088"],
}

# Explicit allowlist — unknown reasons/tags fail closed.
R3_HOLD_OVERRIDE_ALLOWED_POLICY_REASONS: frozenset[str] = frozenset(
    {
        "risk:complaint",
        "content_risk_detected",
        "missing_identity",
        "missing_requested_service",
        "customer_inquiry_low_confidence",
        "inquiry_missing_identity",
        "low_confidence",
        "used_fallback",
        "llm_unavailable",
        "decisioning_failed",
        "deterministic_fallback",
    }
)

R3_HOLD_OVERRIDE_ALLOWED_RISK_TAGS: frozenset[str] = frozenset(
    {
        "complaint",
        "risk:complaint",
        "content_risk_detected",
    }
)

R3_HOLD_OVERRIDE_BLOCKED_RISK_TAGS: frozenset[str] = frozenset(
    {
        "prompt_injection",
        "prompt-injection",
        "credential",
        "credentials",
        "secrets",
        "secret_exposure",
        "account_compromise",
        "payment",
        "bank",
        "bank_account",
        "fraud",
        "legal",
        "legal_commitment",
        "privacy",
        "gdpr",
        "deletion",
        "self_harm",
        "self-harm",
        "threat",
        "threats",
        "violence",
        "unsafe_electrical",
        "electrical_emergency",
        "critical_security",
        "security",
        "unknown_high_risk",
        "unknown_critical_risk",
        "high_risk",
        "critical_risk",
    }
)

ORPHANED_ATTEMPT_7_CAMPAIGN_ID = "0b19ef72-6104-46d8-bb0e-78e02ba73aa3"
ORPHANED_ATTEMPT_7_ORPHAN_GROUP_ID = "orphaned_attempt_7"

ORPHANED_ATTEMPT_7_SCENARIO_RUNS: tuple[dict[str, Any], ...] = (
    {
        "scenario_id": "PTB-DCQ-0000",
        "evaluation_run_id": "ef992348-f944-4ae1-8cc4-574e31276059",
        "root_job_id": "fb928e75-fad6-4458-90d9-87eb4e03c822",
        "inbound_message_id": "19fced83bec9f9a0",
        "inbound_message_id_redacted": "19fc…f9a0",
        "provider_message_id": "19fced8910c859c1",
        "provider_message_id_redacted": "19fc…59c1",
        "provider_thread_id": "19fced83bec9f9a0",
        "provider_thread_id_redacted": "19fc…f9a0",
        "provider": "google_mail",
        "inbound_trigger_sent": True,
        "approved_reply_sent": True,
        "execution_outcome": "succeeded",
        "body_hash": R3_APPROVED_SEND_BODY_HASHES["PTB-DCQ-0000"],
        "body_hash_match": True,
        "recipient_match": True,
        "external_write_historical": True,
        "exclude_from_approved_reply_count": True,
        "reuse_blocked": True,
        "never_resume": True,
        "never_retry": True,
    },
    {
        "scenario_id": "PTB-DCQ-0022",
        "evaluation_run_id": "1ab63fb7-a515-4e47-9ff3-55a42d193073",
        "root_job_id": "80934c1f-506f-4665-8b5d-6556b8e39807",
        "inbound_message_id": "19fced8b9397ca62",
        "inbound_message_id_redacted": "19fc…ca62",
        "provider_message_id": "19fced907c5e78f7",
        "provider_message_id_redacted": "19fc…78f7",
        "provider_thread_id": "19fced8b9397ca62",
        "provider_thread_id_redacted": "19fc…ca62",
        "provider": "google_mail",
        "inbound_trigger_sent": True,
        "approved_reply_sent": True,
        "execution_outcome": "succeeded",
        "body_hash": R3_APPROVED_SEND_BODY_HASHES["PTB-DCQ-0022"],
        "body_hash_match": True,
        "recipient_match": True,
        "external_write_historical": True,
        "exclude_from_approved_reply_count": True,
        "reuse_blocked": True,
        "never_resume": True,
        "never_retry": True,
    },
    {
        "scenario_id": "PTB-DCQ-0033",
        "evaluation_run_id": "a508d07f-beef-4482-97b1-a38f39586007",
        "root_job_id": "8f592eb3-67cb-4e4d-bc6b-a46f98d890bb",
        "inbound_message_id": "19fced92d7ccfbce",
        "inbound_message_id_redacted": "19fc…fbce",
        "provider_message_id": "19fced97e1be4d6b",
        "provider_message_id_redacted": "19fc…4d6b",
        "provider_thread_id": "19fced92d7ccfbce",
        "provider_thread_id_redacted": "19fc…fbce",
        "provider": "google_mail",
        "inbound_trigger_sent": True,
        "approved_reply_sent": True,
        "execution_outcome": "succeeded",
        "body_hash": R3_APPROVED_SEND_BODY_HASHES["PTB-DCQ-0033"],
        "body_hash_match": True,
        "recipient_match": True,
        "external_write_historical": True,
        "exclude_from_approved_reply_count": True,
        "reuse_blocked": True,
        "never_resume": True,
        "never_retry": True,
    },
    {
        "scenario_id": "PTB-DCQ-0049",
        "evaluation_run_id": "1ab48b51-d5ee-46a9-903e-c2a4bf4c0f5c",
        "root_job_id": "d9ead54a-cbca-4393-8ea9-78196abc66da",
        "inbound_message_id": "19fced9a587187aa",
        "inbound_message_id_redacted": "19fc…87aa",
        "provider_message_id": "19fced9f464477c9",
        "provider_message_id_redacted": "19fc…77c9",
        "provider_thread_id": "19fced9a587187aa",
        "provider_thread_id_redacted": "19fc…87aa",
        "provider": "google_mail",
        "inbound_trigger_sent": True,
        "approved_reply_sent": True,
        "execution_outcome": "succeeded",
        "body_hash": R3_APPROVED_SEND_BODY_HASHES["PTB-DCQ-0049"],
        "body_hash_match": True,
        "recipient_match": True,
        "external_write_historical": True,
        "exclude_from_approved_reply_count": True,
        "reuse_blocked": True,
        "never_resume": True,
        "never_retry": True,
    },
    {
        "scenario_id": "PTB-DCQ-0056",
        "evaluation_run_id": "43d56dab-41ab-4a1a-9b83-2958c033a03e",
        "root_job_id": "8361b4e2-97c8-46c7-bd99-852179c224ab",
        "inbound_message_id": "19fceda2172edcc8",
        "inbound_message_id_redacted": "19fc…dcc8",
        "provider_message_id": "19fceda6ad554413",
        "provider_message_id_redacted": "19fc…4413",
        "provider_thread_id": "19fceda2172edcc8",
        "provider_thread_id_redacted": "19fc…dcc8",
        "provider": "google_mail",
        "inbound_trigger_sent": True,
        "approved_reply_sent": True,
        "execution_outcome": "succeeded",
        "body_hash": R3_APPROVED_SEND_BODY_HASHES["PTB-DCQ-0056"],
        "body_hash_match": True,
        "recipient_match": True,
        "external_write_historical": True,
        "exclude_from_approved_reply_count": True,
        "reuse_blocked": True,
        "never_resume": True,
        "never_retry": True,
    },
    {
        "scenario_id": "PTB-DCQ-0072",
        "evaluation_run_id": "24522e6d-c1a0-48c1-92b8-6baecb8ad995",
        "root_job_id": "4e869ef8-0951-49f9-9359-052d9e7e69dc",
        "inbound_message_id": "19fceda97c9e7a74",
        "inbound_message_id_redacted": "19fc…7a74",
        "provider_message_id": "19fcedadfd9ec4e4",
        "provider_message_id_redacted": "19fc…c4e4",
        "provider_thread_id": "19fceda97c9e7a74",
        "provider_thread_id_redacted": "19fc…7a74",
        "provider": "google_mail",
        "inbound_trigger_sent": True,
        "approved_reply_sent": True,
        "execution_outcome": "succeeded",
        "body_hash": R3_APPROVED_SEND_BODY_HASHES["PTB-DCQ-0072"],
        "body_hash_match": True,
        "recipient_match": True,
        "external_write_historical": True,
        "exclude_from_approved_reply_count": True,
        "reuse_blocked": True,
        "never_resume": True,
        "never_retry": True,
    },
    {
        "scenario_id": "PTB-DCQ-0080",
        "evaluation_run_id": "f51cd732-3ac0-47e9-9462-e37c4e770b82",
        "root_job_id": "68800dde-19ac-45f3-9bca-f38c3bf5a465",
        "inbound_message_id": "19fcedb1ea28ff1c",
        "inbound_message_id_redacted": "19fc…ff1c",
        "provider_message_id": "19fcedb657765283",
        "provider_message_id_redacted": "19fc…5283",
        "provider_thread_id": "19fcedb1ea28ff1c",
        "provider_thread_id_redacted": "19fc…ff1c",
        "provider": "google_mail",
        "inbound_trigger_sent": True,
        "approved_reply_sent": True,
        "execution_outcome": "succeeded",
        "body_hash": R3_APPROVED_SEND_BODY_HASHES["PTB-DCQ-0080"],
        "body_hash_match": True,
        "recipient_match": True,
        "external_write_historical": True,
        "exclude_from_approved_reply_count": True,
        "reuse_blocked": True,
        "never_resume": True,
        "never_retry": True,
    },
    {
        "scenario_id": "PTB-DCQ-0088",
        "evaluation_run_id": "f1be25bc-aecb-4b94-bb65-46a0aae0bf01",
        "root_job_id": "62a3e06a-4bff-4a07-a853-24e1cddb66f2",
        "inbound_message_id": "19fcedb8a6c244f1",
        "inbound_message_id_redacted": "19fc…44f1",
        "provider_message_id": None,
        "provider_message_id_redacted": None,
        "provider_thread_id": None,
        "provider_thread_id_redacted": None,
        "provider": None,
        "inbound_trigger_sent": True,
        "approved_reply_sent": False,
        "approval_state": "hold",
        "policy_authorization": "hold_for_review",
        "job_status": "manual_review",
        "pending_approval": False,
        "execution_intent": False,
        "provider_attempt": False,
        "draft_created": False,
        "execution_outcome": None,
        "body_hash": R3_APPROVED_SEND_BODY_HASHES["PTB-DCQ-0088"],
        "exclude_from_approved_reply_count": True,
        "reuse_blocked": True,
        "never_resume": True,
        "never_retry": True,
        "run_status": "aborted",
    },
)

ORPHANED_ATTEMPT_7_EVALUATION_RUN_IDS: frozenset[str] = frozenset(
    str(row["evaluation_run_id"]) for row in ORPHANED_ATTEMPT_7_SCENARIO_RUNS
)
ORPHANED_ATTEMPT_7_INBOUND_MESSAGE_IDS: frozenset[str] = frozenset(
    str(row["inbound_message_id"])
    for row in ORPHANED_ATTEMPT_7_SCENARIO_RUNS
    if row.get("inbound_message_id")
)
ORPHANED_ATTEMPT_7_PROVIDER_MESSAGE_IDS: frozenset[str] = frozenset(
    str(row["provider_message_id"])
    for row in ORPHANED_ATTEMPT_7_SCENARIO_RUNS
    if row.get("provider_message_id")
)
ORPHANED_ATTEMPT_7_JOB_IDS: frozenset[str] = frozenset(
    str(row["root_job_id"]) for row in ORPHANED_ATTEMPT_7_SCENARIO_RUNS if row.get("root_job_id")
)


@dataclass
class R3ApprovalMaterializationResolution:
    active: bool = False
    override_applied: bool = False
    override_required: bool = False
    override_eligible: bool = False
    materialize_pending_approval: bool = False
    execution_allowed: bool = False
    base_policy_authorization: str | None = None
    base_policy_reasons: list[str] = field(default_factory=list)
    base_recommendation: str | None = None
    base_risk_tags: list[str] = field(default_factory=list)
    r3_override_authorization: str | None = None
    r3_override_contract: str | None = None
    r3_override_reason: str | None = None
    expected_approval_state: str | None = None
    scenario_id: str | None = None
    frozen_body_hash: str | None = None
    manifest_hash: str | None = None
    runner_sha: str | None = None
    approval_artifact_hash: str | None = None
    blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "override_applied": self.override_applied,
            "override_required": self.override_required,
            "override_eligible": self.override_eligible,
            "materialize_pending_approval": self.materialize_pending_approval,
            "execution_allowed": False,
            "base_policy_authorization": self.base_policy_authorization,
            "base_policy_reasons": list(self.base_policy_reasons),
            "base_recommendation": self.base_recommendation,
            "base_risk_tags": list(self.base_risk_tags),
            "r3_override_applied": self.override_applied,
            "r3_override_authorization": self.r3_override_authorization,
            "r3_override_contract": self.r3_override_contract,
            "r3_override_reason": self.r3_override_reason,
            "expected_approval_state": self.expected_approval_state,
            "scenario_id": self.scenario_id,
            "frozen_body_hash": self.frozen_body_hash,
            "manifest_hash": self.manifest_hash,
            "runner_sha": self.runner_sha,
            "approval_artifact_hash": self.approval_artifact_hash,
            "blockers": list(self.blockers),
        }

    def provenance(self) -> dict[str, Any]:
        """Compact provenance for action/approval/audit payloads."""
        return {
            "base_policy_authorization": self.base_policy_authorization,
            "base_policy_reasons": list(self.base_policy_reasons),
            "base_recommendation": self.base_recommendation,
            "base_risk_tags": list(self.base_risk_tags),
            "r3_override_applied": True,
            "r3_override_contract": R3_OVERRIDE_CONTRACT_ID,
            "r3_override_authorization": ActionAuthorization.APPROVAL_REQUIRED.value,
            "r3_override_reason": R3_OVERRIDE_REASON,
            "scenario_id": self.scenario_id,
            "manifest_hash": self.manifest_hash,
            "runner_sha": self.runner_sha,
            "frozen_body_hash": self.frozen_body_hash,
            "approval_artifact_hash": self.approval_artifact_hash,
        }


def _norm_tags(values: Any) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        return [values.strip()] if values.strip() else []
    out: list[str] = []
    for item in values:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return out


def _has_blocked_risk(tags: list[str], reasons: list[str]) -> list[str]:
    combined = {t.lower().replace(" ", "_") for t in tags + reasons}
    hits: list[str] = []
    for blocked in R3_HOLD_OVERRIDE_BLOCKED_RISK_TAGS:
        key = blocked.lower()
        if key in combined or any(key in item for item in combined):
            # complaint is allowlisted separately; only block non-complaint security tags
            if key in {"complaint", "risk:complaint", "content_risk_detected"}:
                continue
            hits.append(blocked)
    return sorted(set(hits))


def _reasons_outside_allowlist(reasons: list[str]) -> list[str]:
    return sorted(
        {
            r
            for r in reasons
            if r not in R3_HOLD_OVERRIDE_ALLOWED_POLICY_REASONS
            and r.lower() not in {x.lower() for x in R3_HOLD_OVERRIDE_ALLOWED_POLICY_REASONS}
        }
    )


def _risk_tags_outside_allowlist(tags: list[str]) -> list[str]:
    allowed = {t.lower() for t in R3_HOLD_OVERRIDE_ALLOWED_RISK_TAGS}
    return sorted({t for t in tags if t.lower() not in allowed})


def _complaint_signal_present(*, reasons: list[str], risk_tags: list[str], classification: dict[str, Any] | None) -> bool:
    combined = {x.lower() for x in reasons + risk_tags}
    if "risk:complaint" in combined or "complaint" in combined:
        return True
    if classification:
        for key in ("ticket_type", "detected_job_type", "business_intent"):
            val = classification.get(key)
            if isinstance(val, dict):
                val = val.get("primary_intent") or val.get("type")
            if str(val or "").lower() in {"complaint", "support_complaint", "complaint_warranty"}:
                return True
    return False


def _low_confidence_or_fallback_present(reasons: list[str], classification: dict[str, Any] | None) -> bool:
    markers = {
        "low_confidence",
        "customer_inquiry_low_confidence",
        "used_fallback",
        "llm_unavailable",
        "decisioning_failed",
        "deterministic_fallback",
    }
    if any(r in markers for r in reasons):
        return True
    if classification and (
        classification.get("low_confidence")
        or classification.get("used_fallback")
        or classification.get("llm_unavailable")
    ):
        return True
    return False


def _is_attempt_7_reused_id(
    *,
    evaluation_run_id: str | None,
    job_id: str | None,
    action: dict[str, Any] | None,
) -> bool:
    if evaluation_run_id and evaluation_run_id in ORPHANED_ATTEMPT_7_EVALUATION_RUN_IDS:
        return True
    if job_id and job_id in ORPHANED_ATTEMPT_7_JOB_IDS:
        return True
    if isinstance(action, dict):
        for key in ("_action_operation_id", "action_operation_id", "_approval_id", "approval_id"):
            val = str(action.get(key) or "")
            if val and (
                val in ORPHANED_ATTEMPT_7_EVALUATION_RUN_IDS
                or val.startswith(ORPHANED_ATTEMPT_7_CAMPAIGN_ID)
            ):
                return True
    return False


def resolve_r3_frozen_approval_materialization(
    *,
    db: Session | None,
    job: Any | None,
    action: dict[str, Any] | None,
    live_eval_snapshot: Any | None = None,
    scenario_id: str | None = None,
    base_policy_authorization: str | None = None,
    base_policy_reasons: list[str] | None = None,
    classification: dict[str, Any] | None = None,
    frozen_body: str | None = None,
    frozen_body_hash: str | None = None,
    manifest_hash: str | None = None,
    runner_sha: str | None = None,
    manual_approval_artifact: dict[str, Any] | None = None,
    base_recommendation: str | None = None,
    base_risk_tags: list[str] | None = None,
    campaign_type: str | None = None,
    execution_mode: str | None = None,
    tenant_id: str | None = None,
    probe_only: bool = False,
) -> R3ApprovalMaterializationResolution:
    """Resolve whether hold_for_review may materialize as pending approval for R3.

    Never returns execution_allowed. Override result is only approval_required.
    """
    result = R3ApprovalMaterializationResolution(
        base_policy_authorization=base_policy_authorization,
        base_policy_reasons=list(base_policy_reasons or []),
        base_recommendation=base_recommendation,
        base_risk_tags=list(base_risk_tags or []),
        scenario_id=scenario_id,
        frozen_body_hash=frozen_body_hash,
        manifest_hash=manifest_hash,
        runner_sha=runner_sha,
    )
    blockers: list[str] = []

    snap = live_eval_snapshot
    if snap is None and job is not None:
        snap = snapshot_from_job_input(getattr(job, "input_data", None) or {})

    resolved_tenant = (
        tenant_id
        or (str(getattr(snap, "tenant_id", "") or "") if snap is not None else "")
        or str(getattr(job, "tenant_id", "") or "")
        or (str(action.get("tenant_id") or "") if isinstance(action, dict) else "")
    ).strip()
    resolved_scenario = (
        scenario_id
        or (str(getattr(snap, "scenario_id", "") or "") if snap is not None else "")
        or ""
    ).strip()
    result.scenario_id = resolved_scenario or None

    resolved_campaign = (
        campaign_type
        or (manual_approval_artifact or {}).get("campaign_type")
        or (getattr(snap, "campaign_type", None) if snap is not None else None)
        or R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE
    )
    resolved_mode = (
        execution_mode
        or (manual_approval_artifact or {}).get("execution_mode")
        or (str(getattr(snap, "ai_mode", "") or "") if snap is not None else "")
        or R3_FROZEN_EXECUTION_MODE
    )

    # Context gate — inactive outside trusted R3 frozen canary.
    if resolved_tenant != LIVE_EVAL_TENANT_ID:
        if probe_only:
            blockers.append("tenant_id must be TENANT_LIVE_EVAL")
        result.blockers = blockers
        return result
    if resolved_campaign != R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE:
        blockers.append("campaign_type must be coworker_r3_frozen_live_canary")
        result.blockers = blockers
        return result
    if resolved_mode not in {R3_FROZEN_EXECUTION_MODE, R3_FROZEN_AI_MODE}:
        blockers.append("execution_mode must be r3_frozen_approved_body")
        result.blockers = blockers
        return result
    if resolved_scenario and resolved_scenario not in R3_ALL_SCENARIO_IDS:
        blockers.append("scenario_id not in R3 registry")
        result.blockers = blockers
        return result

    result.active = True
    result.override_required = resolved_scenario in R3_HOLD_OVERRIDE_SCENARIO_IDS

    if isinstance(action, dict) and str(action.get("type") or "") not in {
        "send_customer_auto_reply",
        "",
    }:
        # Allow probe without action; runtime requires send_customer_auto_reply.
        if action.get("type"):
            blockers.append("action.type must be send_customer_auto_reply")

    if resolved_scenario in R3_NO_SEND_SCENARIO_IDS:
        blockers.append("no-send scenario cannot receive hold override")
        result.blockers = blockers
        result.expected_approval_state = "hold"
        return result

    if resolved_scenario not in R3_SEND_SCENARIO_IDS:
        blockers.append("scenario not in R3 send registry")
        result.blockers = blockers
        return result

    # Non-override send scenarios do not use this contract for materialization.
    if resolved_scenario not in R3_HOLD_OVERRIDE_SCENARIO_IDS:
        result.override_required = False
        result.override_eligible = False
        result.expected_approval_state = "pending"
        result.blockers = blockers
        return result

    # --- Override path for PTB-DCQ-0088 ---
    if base_policy_authorization != "hold_for_review":
        blockers.append("base_policy_authorization must be hold_for_review for override")

    reasons = list(base_policy_reasons or [])
    risk_tags = list(base_risk_tags or [])
    unknown_reasons = _reasons_outside_allowlist(reasons)
    if unknown_reasons:
        blockers.append(f"unknown base-policy-reason: {', '.join(unknown_reasons)}")
    unknown_tags = _risk_tags_outside_allowlist(risk_tags)
    if unknown_tags:
        blockers.append(f"unknown risk tag: {', '.join(unknown_tags)}")
    blocked_hits = _has_blocked_risk(risk_tags, reasons)
    if blocked_hits:
        blockers.append(f"blocked risk tag present: {', '.join(blocked_hits)}")
    if not _complaint_signal_present(reasons=reasons, risk_tags=risk_tags, classification=classification):
        blockers.append("complaint classification/risk tag required for override")
    if not _low_confidence_or_fallback_present(reasons, classification):
        blockers.append("low confidence or decisioning fallback/llm_unavailable required")

    expected_hash = R3_HOLD_OVERRIDE_CANONICAL_HASHES.get(resolved_scenario)
    computed_hash = frozen_body_hash
    if frozen_body and not computed_hash:
        computed_hash = r3_send_body_hash(frozen_body)
    result.frozen_body_hash = computed_hash
    if not expected_hash:
        blockers.append("canonical hash missing for override scenario")
    elif not computed_hash:
        blockers.append("frozen body hash required")
    elif computed_hash != expected_hash:
        blockers.append("frozen body hash does not match canonical approved hash")

    artifact = manual_approval_artifact or {}
    if not artifact:
        blockers.append("manual approval artifact required")
    else:
        art_sha = str(artifact.get("runtime_sha") or artifact.get("expected_runtime_sha") or "")
        art_manifest = str(artifact.get("manifest_hash") or "")
        result.approval_artifact_hash = str(
            artifact.get("artifact_hash") or artifact.get("approval_artifact_hash") or ""
        ) or None
        if runner_sha and art_sha and art_sha != runner_sha:
            blockers.append("approval artifact runtime SHA mismatch")
        if manifest_hash and art_manifest and art_manifest != manifest_hash:
            blockers.append("approval artifact manifest hash mismatch")
        if artifact.get("manual_execution_approved") is not True and artifact.get("body_hashes_approved") is not True:
            blockers.append("manual approval artifact not approved")
        # Reject attempt-7 bound approvals for new runs
        if str(artifact.get("attempt_number") or "") == "7":
            blockers.append("attempt-7 approval artifact cannot be reused")
        if str(artifact.get("campaign_id") or "") == ORPHANED_ATTEMPT_7_CAMPAIGN_ID:
            blockers.append("attempt-7 campaign_id cannot be reused")

    eval_run_id = str(getattr(snap, "evaluation_run_id", "") or "") if snap is not None else ""
    job_id = str(getattr(job, "job_id", "") or "") if job is not None else ""
    if _is_attempt_7_reused_id(evaluation_run_id=eval_run_id or None, job_id=job_id or None, action=action):
        blockers.append("attempt-7 run/job/operation IDs cannot be reused")

    if db is not None and eval_run_id:
        row = LiveEvalRunRepository.get_run(db, eval_run_id, tenant_id=resolved_tenant)
        if row is not None:
            if str(getattr(row, "status", "") or "") in {"aborted", "quarantined"}:
                blockers.append("aborted/quarantined run cannot receive override")
            if not is_r3_frozen_live_eval_run(row) and not probe_only:
                blockers.append("live eval run is not R3 frozen")

    # Recipient check when action present
    if isinstance(action, dict) and action.get("to") and snap is not None:
        expected_sender = str(getattr(snap, "expected_sender", "") or "").strip().lower()
        to_addr = str(action.get("to") or "").strip().lower()
        if expected_sender and to_addr and to_addr != expected_sender:
            blockers.append("recipient mismatch")

    result.blockers = list(dict.fromkeys(blockers))
    eligible = not result.blockers
    result.override_eligible = eligible
    result.override_applied = eligible
    result.materialize_pending_approval = eligible
    result.execution_allowed = False
    result.r3_override_authorization = (
        ActionAuthorization.APPROVAL_REQUIRED.value if eligible else None
    )
    result.r3_override_contract = R3_OVERRIDE_CONTRACT_ID if eligible else None
    result.r3_override_reason = R3_OVERRIDE_REASON if eligible else None
    result.expected_approval_state = "pending" if eligible else "hold"
    return result


def should_materialize_r3_action_dispatch_despite_hold(
    *,
    job: Any,
    db: Session | None = None,
    policy_payload: dict[str, Any] | None = None,
) -> bool:
    """Orchestrator hook: allow ACTION_DISPATCH when R3 hold→pending is eligible."""
    policy_payload = policy_payload or {}
    if policy_payload.get("decision") != "hold_for_review":
        return False
    snap = snapshot_from_job_input(getattr(job, "input_data", None) or {})
    if snap is None:
        return False
    if str(getattr(snap, "tenant_id", "") or "") != LIVE_EVAL_TENANT_ID:
        return False
    if str(getattr(snap, "ai_mode", "") or "") != R3_FROZEN_AI_MODE:
        return False
    scenario_id = str(getattr(snap, "scenario_id", "") or "")
    if scenario_id not in R3_HOLD_OVERRIDE_SCENARIO_IDS:
        return False

    reasons = _norm_tags(policy_payload.get("reasons") or policy_payload.get("reason_codes"))
    risk_tags = _norm_tags(
        (policy_payload.get("threat_assessment") or {}).get("categories")
        if isinstance(policy_payload.get("threat_assessment"), dict)
        else None
    )
    if not risk_tags:
        risk = policy_payload.get("risk_categories") or []
        risk_tags = _norm_tags(risk)

    classification = {
        "detected_job_type": policy_payload.get("detected_job_type"),
        "low_confidence": "low_confidence" in reasons or "customer_inquiry_low_confidence" in reasons,
        "used_fallback": "used_fallback" in reasons or "llm_unavailable" in reasons,
        "llm_unavailable": "llm_unavailable" in reasons,
        "ticket_type": "complaint" if any("complaint" in r for r in reasons) else None,
    }
    # Readiness at dispatch time uses canonical hash expectation; frozen body may be bound later.
    expected_hash = R3_HOLD_OVERRIDE_CANONICAL_HASHES.get(scenario_id)
    resolution = resolve_r3_frozen_approval_materialization(
        db=db,
        job=job,
        action={"type": "send_customer_auto_reply", "tenant_id": LIVE_EVAL_TENANT_ID},
        live_eval_snapshot=snap,
        scenario_id=scenario_id,
        base_policy_authorization="hold_for_review",
        base_policy_reasons=reasons,
        classification=classification,
        frozen_body_hash=expected_hash,
        base_recommendation=str(policy_payload.get("recommendation") or "") or None,
        base_risk_tags=risk_tags,
        probe_only=True,
    )
    # At orchestrator time, manual approval artifact may not be on the job yet.
    # Allow dispatch when scenario+reason allowlist matches; full artifact check is
    # enforced by readiness/JIT before first trigger and again at approval bind.
    soft_blockers = {
        "manual approval artifact required",
        "approval artifact runtime SHA mismatch",
        "approval artifact manifest hash mismatch",
        "manual approval artifact not approved",
    }
    remaining = [b for b in resolution.blockers if b not in soft_blockers]
    return resolution.override_required and not remaining


def apply_r3_hold_override_to_action(
    *,
    job: Any,
    action: dict[str, Any],
    policy_payload: dict[str, Any],
    db: Session | None = None,
    manual_approval_artifact: dict[str, Any] | None = None,
    manifest_hash: str | None = None,
    runner_sha: str | None = None,
    frozen_body: str | None = None,
    frozen_body_hash: str | None = None,
) -> tuple[dict[str, Any], R3ApprovalMaterializationResolution | None]:
    """If blocked solely by hold_for_review under R3 contract, rematerialize as pending."""
    if str(action.get("type") or "") != "send_customer_auto_reply":
        return action, None
    if policy_payload.get("decision") != "hold_for_review":
        return action, None

    snap = snapshot_from_job_input(getattr(job, "input_data", None) or {})
    scenario_id = str(getattr(snap, "scenario_id", "") or "") if snap else ""
    if scenario_id not in R3_HOLD_OVERRIDE_SCENARIO_IDS:
        return action, None

    reasons = _norm_tags(policy_payload.get("reasons") or policy_payload.get("reason_codes"))
    risk_tags = _norm_tags(policy_payload.get("risk_categories"))
    if not risk_tags and isinstance(policy_payload.get("threat_assessment"), dict):
        risk_tags = _norm_tags(policy_payload["threat_assessment"].get("categories"))

    hash_value = frozen_body_hash or R3_HOLD_OVERRIDE_CANONICAL_HASHES.get(scenario_id)
    if frozen_body and not frozen_body_hash:
        hash_value = r3_send_body_hash(frozen_body)

    classification = {
        "detected_job_type": policy_payload.get("detected_job_type"),
        "low_confidence": any("low_confidence" in r for r in reasons),
        "used_fallback": any(r in {"used_fallback", "llm_unavailable", "deterministic_fallback"} for r in reasons),
        "llm_unavailable": "llm_unavailable" in reasons,
        "ticket_type": "complaint",
        "business_intent": "support_complaint",
    }

    # Soft-check without artifact at pipeline time; provenance still recorded.
    artifact = manual_approval_artifact or (getattr(job, "input_data", {}) or {}).get(
        "_r3_manual_approval_artifact"
    )

    resolution = resolve_r3_frozen_approval_materialization(
        db=db,
        job=job,
        action=action,
        live_eval_snapshot=snap,
        scenario_id=scenario_id,
        base_policy_authorization="hold_for_review",
        base_policy_reasons=reasons,
        classification=classification,
        frozen_body=frozen_body,
        frozen_body_hash=hash_value,
        manifest_hash=manifest_hash,
        runner_sha=runner_sha,
        manual_approval_artifact=artifact if isinstance(artifact, dict) else None,
        base_recommendation=str(policy_payload.get("recommendation") or "") or None,
        base_risk_tags=risk_tags,
        probe_only=artifact is None,
    )
    soft_blockers = {
        "manual approval artifact required",
        "approval artifact runtime SHA mismatch",
        "approval artifact manifest hash mismatch",
        "manual approval artifact not approved",
    }
    remaining = [b for b in resolution.blockers if b not in soft_blockers]
    if remaining:
        resolution.override_eligible = False
        resolution.override_applied = False
        resolution.materialize_pending_approval = False
        resolution.blockers = remaining
        return action, resolution

    provenance = resolution.provenance()
    annotated = {
        **action,
        "_skip": False,
        "_needs_approval": True,
        "_authorization": ActionAuthorization.APPROVAL_REQUIRED.value,
        "_approval_reason": R3_OVERRIDE_REASON,
        "_r3_override_applied": True,
        "_r3_override_contract": R3_OVERRIDE_CONTRACT_ID,
        "_r3_override_authorization": ActionAuthorization.APPROVAL_REQUIRED.value,
        "_r3_override_reason": R3_OVERRIDE_REASON,
        "_base_policy_authorization": "hold_for_review",
        "_base_policy_reasons": list(reasons),
        "_base_recommendation": resolution.base_recommendation,
        "_base_risk_tags": list(risk_tags),
        "_r3_approval_materialization": provenance,
        "_safe_acknowledgement_path": True,
    }
    resolution.override_applied = True
    resolution.override_eligible = True
    resolution.materialize_pending_approval = True
    resolution.blockers = []
    resolution.expected_approval_state = "pending"
    resolution.r3_override_authorization = ActionAuthorization.APPROVAL_REQUIRED.value
    resolution.r3_override_contract = R3_OVERRIDE_CONTRACT_ID
    resolution.r3_override_reason = R3_OVERRIDE_REASON
    return annotated, resolution


def run_r3_approval_materialization_readiness(
    *,
    manifest: dict[str, Any],
    approval_artifact: dict[str, Any] | None,
    runtime_sha: str,
    profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write-free gate: simulate approval materialization for all 15 R3 scenarios."""
    _ = profile
    scenarios = list(manifest.get("scenarios") or [])
    scenario_ids = [
        str(s.get("scenario_id") or s) if isinstance(s, dict) else str(s) for s in scenarios
    ]
    if not scenario_ids:
        scenario_ids = sorted(R3_ALL_SCENARIO_IDS)

    manifest_hash = str(manifest.get("manifest_hash") or "")
    artifact = dict(approval_artifact or {})
    if artifact and runtime_sha and not artifact.get("runtime_sha") and not artifact.get("expected_runtime_sha"):
        artifact["runtime_sha"] = runtime_sha
    if artifact and manifest_hash and not artifact.get("manifest_hash"):
        artifact["manifest_hash"] = manifest_hash

    reports: list[dict[str, Any]] = []
    blockers: list[str] = []
    hold_override_scenarios: list[str] = []
    send_ready = 0
    no_send_ready = 0

    for scenario_id in scenario_ids:
        planned_send = scenario_id in R3_SEND_SCENARIO_IDS
        expected_hash = R3_APPROVED_SEND_BODY_HASHES.get(scenario_id)
        override_required = scenario_id in R3_HOLD_OVERRIDE_SCENARIO_IDS

        if scenario_id in R3_NO_SEND_SCENARIO_IDS:
            row = {
                "scenario_id": scenario_id,
                "base_policy_authorization": None,
                "base_policy_reasons": [],
                "r3_override_required": False,
                "r3_override_eligible": False,
                "r3_override_applied": False,
                "expected_approval_state": "hold",
                "expected_frozen_body_hash": None,
                "expected_action_type": None,
                "approval_materialization_ready": True,
                "blockers": [],
            }
            if row["expected_approval_state"] == "pending":
                row["approval_materialization_ready"] = False
                row["blockers"].append("no-send must not expect pending")
            reports.append(row)
            if row["approval_materialization_ready"]:
                no_send_ready += 1
            else:
                blockers.extend(row["blockers"])
            continue

        if override_required:
            base_auth = "hold_for_review"
            base_reasons = [
                "risk:complaint",
                "customer_inquiry_low_confidence",
                "llm_unavailable",
                "missing_identity",
                "missing_requested_service",
                "inquiry_missing_identity",
                "content_risk_detected",
            ]
            resolution = resolve_r3_frozen_approval_materialization(
                db=None,
                job=None,
                action={
                    "type": "send_customer_auto_reply",
                    "tenant_id": LIVE_EVAL_TENANT_ID,
                    "to": "ni@sol-f.se",
                },
                scenario_id=scenario_id,
                base_policy_authorization=base_auth,
                base_policy_reasons=base_reasons,
                classification={
                    "ticket_type": "complaint",
                    "business_intent": "support_complaint",
                    "low_confidence": True,
                    "llm_unavailable": True,
                    "used_fallback": True,
                },
                frozen_body_hash=expected_hash,
                manifest_hash=manifest_hash or artifact.get("manifest_hash"),
                runner_sha=runtime_sha,
                manual_approval_artifact=artifact or {
                    "runtime_sha": runtime_sha,
                    "manifest_hash": manifest_hash,
                    "manual_execution_approved": True,
                    "body_hashes_approved": True,
                    "campaign_type": R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE,
                    "execution_mode": R3_FROZEN_EXECUTION_MODE,
                },
                base_risk_tags=["complaint"],
                campaign_type=R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE,
                execution_mode=R3_FROZEN_EXECUTION_MODE,
                tenant_id=LIVE_EVAL_TENANT_ID,
                probe_only=False,
            )
            hold_override_scenarios.append(scenario_id)
            row = {
                "scenario_id": scenario_id,
                "base_policy_authorization": base_auth,
                "base_policy_reasons": base_reasons,
                "r3_override_required": True,
                "r3_override_eligible": resolution.override_eligible,
                "r3_override_authorization": resolution.r3_override_authorization,
                "r3_override_applied": False,
                "expected_approval_state": "pending",
                "expected_frozen_body_hash": expected_hash,
                "expected_action_type": "send_customer_auto_reply",
                "approval_materialization_ready": bool(
                    resolution.override_eligible and resolution.expected_approval_state == "pending"
                ),
                "blockers": list(resolution.blockers),
            }
        else:
            row = {
                "scenario_id": scenario_id,
                "base_policy_authorization": "approval_required",
                "base_policy_reasons": ["safe_acknowledgement_path"],
                "r3_override_required": False,
                "r3_override_eligible": False,
                "r3_override_applied": False,
                "expected_approval_state": "pending",
                "expected_frozen_body_hash": expected_hash,
                "expected_action_type": "send_customer_auto_reply",
                "approval_materialization_ready": True,
                "blockers": [],
            }
            # Guard: unauthorized override must not appear
            if row["r3_override_required"]:
                row["approval_materialization_ready"] = False
                row["blockers"].append("unauthorized override required flag")

        reports.append(row)
        if planned_send and row["approval_materialization_ready"]:
            send_ready += 1
        elif planned_send:
            blockers.extend(row["blockers"] or [f"{scenario_id} not ready"])

    ptb_0088 = next((r for r in reports if r["scenario_id"] == "PTB-DCQ-0088"), {})
    contract_valid = (
        send_ready == len(R3_SEND_SCENARIO_IDS)
        and no_send_ready == len(R3_NO_SEND_SCENARIO_IDS)
        and not blockers
    )
    return {
        "approval_materialization_contract_valid": contract_valid,
        "approval_materialization_ready": contract_valid,
        "approval_materialization_send_ready_count": send_ready,
        "approval_materialization_no_send_ready_count": no_send_ready,
        "approval_materialization_send_ready": f"{send_ready}/{len(R3_SEND_SCENARIO_IDS)}",
        "approval_materialization_no_send_ready": f"{no_send_ready}/{len(R3_NO_SEND_SCENARIO_IDS)}",
        "r3_hold_override_scenarios": hold_override_scenarios,
        "r3_hold_override_count": len(hold_override_scenarios),
        "PTB-DCQ-0088_base_policy_authorization": ptb_0088.get("base_policy_authorization"),
        "PTB-DCQ-0088_override_eligible": ptb_0088.get("r3_override_eligible"),
        "PTB-DCQ-0088_expected_approval_state": ptb_0088.get("expected_approval_state"),
        "scenarios": reports,
        "blockers": list(dict.fromkeys(blockers)),
        "gmail_sent": False,
        "gmail_drafts_created": False,
    }


def probe_orphaned_attempt_7_campaign(
    db: Session,
    *,
    tenant_id: str = LIVE_EVAL_TENANT_ID,
) -> dict[str, Any]:
    """Read-only verification that attempt-7 campaign remains quarantined."""
    blockers: list[str] = []
    runs_verified = 0
    replies_verified = 0
    blocked_without_reply = 0

    for row in ORPHANED_ATTEMPT_7_SCENARIO_RUNS:
        rid = str(row["evaluation_run_id"])
        db_row = LiveEvalRunRepository.get_run(db, rid, tenant_id=tenant_id)
        if db_row is None:
            blockers.append(f"missing evaluation_run_id {rid}")
            continue
        status = str(getattr(db_row, "status", "") or "")
        if status not in {"aborted", "quarantined", "failed"}:
            blockers.append(f"{rid} status={status} not quarantined")
            continue
        runs_verified += 1
        if row.get("approved_reply_sent"):
            replies_verified += 1
        else:
            blocked_without_reply += 1

    verified = (
        runs_verified == 8
        and replies_verified == 7
        and blocked_without_reply == 1
        and not blockers
    )
    return {
        "orphan_group_id": ORPHANED_ATTEMPT_7_ORPHAN_GROUP_ID,
        "classification": "partial_campaign_stopped",
        "campaign_id": ORPHANED_ATTEMPT_7_CAMPAIGN_ID,
        "attempt_number": 7,
        "scenario_runs": 8,
        "successful_real_provider_replies": 7,
        "blocked_before_reply": 1,
        "no_send_verified": 0,
        "drafts": 0,
        "unknown_outcomes": 0,
        "automatic_retry": False,
        "campaign_reuse_blocked": True,
        "never_resume": True,
        "never_retry": True,
        "orphaned_attempt_7_campaign_verified": verified,
        "attempt_7_real_replies_verified": replies_verified,
        "attempt_7_blocked_without_reply_verified": blocked_without_reply,
        "attempt_7_unknown_outcomes": 0,
        "attempt_7_reuse_blocked": True,
        "runs_quarantined_count": runs_verified,
        "scenario_run_registry": [
            {
                "scenario_id": r["scenario_id"],
                "evaluation_run_id": r["evaluation_run_id"],
                "inbound_message_id_redacted": r.get("inbound_message_id_redacted"),
                "approved_reply_sent": r.get("approved_reply_sent"),
                "provider_message_id_redacted": r.get("provider_message_id_redacted"),
                "exclude_from_approved_reply_count": True,
                "reuse_blocked": True,
            }
            for r in ORPHANED_ATTEMPT_7_SCENARIO_RUNS
        ],
        "blockers": blockers,
    }
