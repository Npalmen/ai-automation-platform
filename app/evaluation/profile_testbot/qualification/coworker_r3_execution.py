"""R3 digital coworker live canary operator execution (dry-run default, fail-closed)."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import httpx

from app.evaluation.live.config import get_live_eval_config
from app.evaluation.live.errors import LiveEvalIntakeSkippedError, LiveEvalSafetyError, LiveEvalSafetyRejectedError
from app.evaluation.live.gmail_transport import run_sender_readiness_read_only
from app.evaluation.live.tenant_intake_readiness import run_r3_tenant_intake_readiness
from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.repositories.postgres.database import SessionLocal
from app.evaluation.live.recipient_gmail_readiness import run_recipient_gmail_readiness
from app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider import (
    run_r3_live_reply_provider_readiness,
)
from app.evaluation.profile_testbot.campaign.semi_auto_live_backend import LiveSemiAutoBackend
from app.evaluation.profile_testbot.campaign.semi_auto_safety import (
    assert_hold_scenario_no_send,
    assert_no_external_writes,
    assert_tenant_isolated,
)
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.profile_testbot.qualification.constants import (
    PTB_SEM_0024_SCENARIO_ID,
    SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND,
)
from app.evaluation.profile_testbot.qualification.coworker_live_canary_manifest import (
    COWORKER_LIVE_CANARY_CAMPAIGN_TYPE,
    COWORKER_LIVE_CANARY_MANIFEST_HASH,
    COWORKER_LIVE_CANARY_SCENARIO_IDS,
    COWORKER_LIVE_CANARY_SEND_MAX,
    COWORKER_LIVE_CANARY_TARGET,
    build_coworker_live_canary_manifest,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_frozen_bodies import (
    resolve_frozen_send_bodies,
    r3_send_body_hash,
    validate_frozen_send_bodies,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_registration_contract import (
    R3_FROZEN_EXECUTION_MODE,
    R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE,
    validate_r3_campaign_registration_contract,
    validate_r3_manifest_registration_contract,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_readiness import (
    R3_APPROVED_SEND_BODY_HASHES,
    evaluate_coworker_r3_readiness,
)
from app.evaluation.profile_testbot.qualification.coworker_r3_approval_materialization_contract import (
    ORPHANED_ATTEMPT_7_CAMPAIGN_ID,
    ORPHANED_ATTEMPT_7_ORPHAN_GROUP_ID,
    ORPHANED_ATTEMPT_7_SCENARIO_RUNS,
)
from app.evaluation.profile_testbot.coworker_quality_oracles import evaluate_coworker_reply_oracles
from app.evaluation.profile_testbot.scenarios.schema import ProfileScenario

R3_APPROVAL_TYPE = "R3_LIVE_CANARY_MANUAL_SEND"
R3_APPROVED_RECIPIENT_DOMAIN = "sol-f.se"
R3_APPROVED_RECIPIENT_LOCAL_PREFIX = "ni"
PROFILE_ID = "niklas-demo-live-eval-v1"

R3_SEND_SCENARIO_IDS: frozenset[str] = frozenset(
    {
        "PTB-DCQ-0000",
        "PTB-DCQ-0022",
        "PTB-DCQ-0033",
        "PTB-DCQ-0049",
        "PTB-DCQ-0056",
        "PTB-DCQ-0072",
        "PTB-DCQ-0080",
        "PTB-DCQ-0088",
    }
)
R3_NO_SEND_SCENARIO_IDS: frozenset[str] = frozenset(
    {
        "PTB-DCQ-0032",
        "PTB-DCQ-0048",
        "PTB-DCQ-0024",
        "PTB-DCQ-0037",
        "PTB-DCQ-0029",
        "PTB-DCQ-0053",
        PTB_SEM_0024_SCENARIO_ID,
    }
)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ExecutionMode = Literal["dry_run", "execute"]

ORPHANED_R3_INBOUND_TRIGGERS: tuple[dict[str, Any], ...] = (
    {
        "orphan_id": "orphaned_attempt_2",
        "attempt": 2,
        "scenario_id": "PTB-DCQ-0000",
        "campaign_id": "e7876c9b-22d3-4baf-95ed-0b11fc15806b",
        "evaluation_run_id": "0a307286-41d7-4b98-8d8b-32b120618210",
        "classification": "inbound_trigger_sent",
        "inbound_trigger_sent": True,
        "approved_reply_sent": False,
        "draft_created": False,
        "sender_message_id_redacted": "19fc…0b09",
        "recipient_message_id_redacted": "19fc…2713",
        "trigger_body_hash": "2ed7d1f0d03cbab262a9443ed9666938596d6a3076ac7c28a06e31cbb88d000a",
        "subject": "KROWOLF-EVAL/0a307286-41d7-4b98-8d8b-32b120618210/PTB-DCQ-0000/1 | Offert solceller Uppsala",
        "sent_at": "2026-08-03T20:53:14Z",
        "reuse_blocked": True,
        "exclude_from_approved_reply_count": True,
    },
    {
        "orphan_id": "orphaned_attempt_3",
        "attempt": 3,
        "scenario_id": "PTB-DCQ-0000",
        "campaign_id": "118b52fe-a7dc-4fbc-a8be-63a88c550e91",
        "evaluation_run_id": "05839824-1fb1-4e98-b8e1-b8025df5db3d",
        "classification": "inbound_trigger_sent",
        "inbound_trigger_sent": True,
        "approved_reply_sent": False,
        "draft_created": False,
        "sender_message_id_redacted": "19fc…be91",
        "recipient_message_id_redacted": None,
        "sent_at": "2026-08-03T22:34:02Z",
        "reuse_blocked": True,
        "exclude_from_approved_reply_count": True,
    },
    {
        "orphan_id": "orphaned_attempt_4",
        "attempt": 4,
        "scenario_id": "PTB-DCQ-0000",
        "campaign_id": "ada5aaf0-83d9-4f09-a8c3-ee4444085915",
        "evaluation_run_id": "ccd9916f-c4b7-4b1c-aabc-fb2da09f89cf",
        "classification": "inbound_trigger_sent",
        "inbound_trigger_sent": True,
        "approved_reply_sent": False,
        "draft_created": False,
        "sender_message_id_redacted": "19fc…cdb3",
        "recipient_message_id_redacted": "19fc…cdb3",
        "sent_at": "2026-08-04T08:43:11Z",
        "reuse_blocked": True,
        "exclude_from_approved_reply_count": True,
    },
    {
        "orphan_id": "orphaned_attempt_5",
        "attempt": 5,
        "scenario_id": "PTB-DCQ-0000",
        "campaign_id": "d3550a0a-8beb-48a5-b433-78684ea00c3b",
        "evaluation_run_id": "b5bbe7ab-7148-4366-8fba-bd92921481f4",
        "classification": "inbound_trigger_sent",
        "inbound_trigger_sent": True,
        "approved_reply_sent": False,
        "draft_created": False,
        "sender_message_id_redacted": "19fc…6263",
        "recipient_message_id_redacted": None,
        "sent_at": "2026-08-04T18:11:56Z",
        "reuse_blocked": True,
        "exclude_from_approved_reply_count": True,
    },
    {
        "orphan_id": "orphaned_attempt_6",
        "attempt": 6,
        "scenario_id": "PTB-DCQ-0000",
        "campaign_id": "13ce2349-0a9d-4b2f-a06b-fc194fe7e86b",
        "evaluation_run_id": "afaf7ec3-69d7-433a-9ba7-8338a0a508c0",
        "classification": "reply_execution_stubbed",
        "failure_stage": "reply_execution_observation",
        "failure_substage": "reply_provider_contract",
        "failure_reason": "internal_stub_without_provider_message_id",
        "inbound_trigger_sent": True,
        "job_created": True,
        "frozen_body_bound": True,
        "approval_created": True,
        "approval_executed": True,
        "external_provider_attempted": False,
        "approved_reply_sent": False,
        "draft_created": False,
        "reply_provider_message_id": None,
        "adapter_provider": "internal_stub",
        "provider_status": "stubbed",
        "automatic_retry": False,
        "unknown_outcome": False,
        "run_status": "aborted",
        "sender_message_id_redacted": "19fc…7f4e",
        "recipient_message_id_redacted": "19fc…7f4e",
        "sent_at": "2026-08-04T21:10:00Z",
        "reuse_blocked": True,
        "exclude_from_approved_reply_count": True,
        "never_resume": True,
        "never_retry": True,
    },
) + tuple(
    {
        "orphan_id": ORPHANED_ATTEMPT_7_ORPHAN_GROUP_ID,
        "orphan_group_id": ORPHANED_ATTEMPT_7_ORPHAN_GROUP_ID,
        "classification": "partial_campaign_stopped",
        "attempt": 7,
        "campaign_id": ORPHANED_ATTEMPT_7_CAMPAIGN_ID,
        "scenario_id": row["scenario_id"],
        "evaluation_run_id": row["evaluation_run_id"],
        "inbound_trigger_sent": row.get("inbound_trigger_sent", True),
        "approved_reply_sent": bool(row.get("approved_reply_sent")),
        "draft_created": False,
        "provider": row.get("provider"),
        "provider_message_id_redacted": row.get("provider_message_id_redacted"),
        "provider_thread_id_redacted": row.get("provider_thread_id_redacted"),
        "sender_message_id_redacted": row.get("inbound_message_id_redacted"),
        "recipient_message_id_redacted": row.get("inbound_message_id_redacted"),
        "execution_outcome": row.get("execution_outcome"),
        "body_hash": row.get("body_hash"),
        "exclude_from_approved_reply_count": True,
        "reuse_blocked": True,
        "never_resume": True,
        "never_retry": True,
        "run_status": "aborted",
        "approval_state": row.get("approval_state"),
        "policy_authorization": row.get("policy_authorization"),
        "external_write_historical": bool(row.get("external_write_historical")),
    }
    for row in ORPHANED_ATTEMPT_7_SCENARIO_RUNS
)

# Attempt 7 registry is defined inline above via ORPHANED_ATTEMPT_7_SCENARIO_RUNS.



@dataclass
class R3ApprovalArtifact:
    path: Path
    payload: dict[str, Any]
    artifact_hash: str

    @property
    def approved(self) -> bool:
        return (
            self.payload.get("approval_type") == R3_APPROVAL_TYPE
            and self.payload.get("body_hashes_approved") is True
            and self.payload.get("human_render_rereview_required") is not True
            and self.payload.get("gmail_sent_at_approval") is not True
            and self.payload.get("gmail_drafts_at_approval") is not True
        )


@dataclass
class R3ScenarioOutcome:
    scenario_id: str
    planned_gmail_send: bool
    status: str
    body_hash: str | None = None
    approved_body_hash: str | None = None
    body_hash_matches_approved: bool | None = None
    recipient_redacted: str | None = None
    approval_operation_id: str | None = None
    reply_operation_id: str | None = None
    approval_state: str | None = None
    execution_outcome: str | None = None
    provider_message_id_redacted: str | None = None
    final_validation_passed: bool | None = None
    blocking_oracle_failures: list[str] = field(default_factory=list)
    audit_events: list[dict[str, Any]] = field(default_factory=list)
    failure_reason: str | None = None
    failure_stage: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "planned_gmail_send": self.planned_gmail_send,
            "status": self.status,
            "body_hash": self.body_hash,
            "approved_body_hash": self.approved_body_hash,
            "body_hash_matches_approved": self.body_hash_matches_approved,
            "recipient_redacted": self.recipient_redacted,
            "approval_operation_id": self.approval_operation_id,
            "reply_operation_id": self.reply_operation_id,
            "approval_state": self.approval_state,
            "execution_outcome": self.execution_outcome,
            "provider_message_id_redacted": self.provider_message_id_redacted,
            "final_validation_passed": self.final_validation_passed,
            "blocking_oracle_failures": self.blocking_oracle_failures,
            "audit_events": self.audit_events,
            "failure_reason": self.failure_reason,
            "failure_stage": self.failure_stage,
        }


@dataclass
class R3ExecutionResult:
    mode: ExecutionMode
    campaign_id: str
    runtime_sha: str
    manifest_hash: str
    approval_artifact_hash: str
    overall_status: str
    planned_sends: int
    successful_sends: int
    failed_sends: int
    unknown_outcomes: int
    no_send_verified: int
    duplicates_blocked: int
    human_render_rereview_required: bool
    stop_reason: str | None
    scenario_outcomes: list[R3ScenarioOutcome] = field(default_factory=list)
    readiness: dict[str, Any] = field(default_factory=dict)
    external_writes: dict[str, int] = field(default_factory=dict)
    secret_scan_issues: list[str] = field(default_factory=list)
    failure_stage: str | None = None
    orphaned_inbound_triggers: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "campaign_id": self.campaign_id,
            "runtime_sha": self.runtime_sha,
            "manifest_hash": self.manifest_hash,
            "approval_artifact_hash": self.approval_artifact_hash,
            "overall_status": self.overall_status,
            "planned_sends": self.planned_sends,
            "successful_sends": self.successful_sends,
            "failed_sends": self.failed_sends,
            "unknown_outcomes": self.unknown_outcomes,
            "no_send_verified": self.no_send_verified,
            "duplicates_blocked": self.duplicates_blocked,
            "human_render_rereview_required": self.human_render_rereview_required,
            "stop_reason": self.stop_reason,
            "scenario_outcomes": [row.to_dict() for row in self.scenario_outcomes],
            "readiness": self.readiness,
            "external_writes": self.external_writes,
            "secret_scan_issues": self.secret_scan_issues,
            "failure_stage": self.failure_stage,
            "orphaned_inbound_triggers": self.orphaned_inbound_triggers,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def body_hash(text: str) -> str:
    return r3_send_body_hash(text)


def _sanitize_http_detail(response: httpx.Response | None) -> str:
    if response is None:
        return "no response body"
    text = (response.text or "").strip()
    if EMAIL_RE.search(text):
        return "HTTP error response redacted (possible secret/email content)"
    return text[:240]


def _format_stage_failure(stage: str, *, detail: str, http_status: int | None = None) -> str:
    if http_status is not None:
        return f"{stage}: HTTP {http_status} — {detail}"
    return f"{stage}: {detail}"


def _failed_scenario_outcome(
    *,
    scenario_id: str,
    planned_gmail_send: bool,
    failure_stage: str,
    failure_reason: str,
) -> R3ScenarioOutcome:
    return R3ScenarioOutcome(
        scenario_id=scenario_id,
        planned_gmail_send=planned_gmail_send,
        status="failed",
        failure_stage=failure_stage,
        failure_reason=failure_reason,
    )


def _format_safety_rejected(exc: LiveEvalSafetyRejectedError) -> str:
    payload = exc.payload or {}
    reason = str(payload.get("safety_reason") or payload.get("reason") or "safety_rejected")
    stage = payload.get("failed_stage")
    http_status = payload.get("http_status")
    if stage and http_status:
        return _format_stage_failure(str(stage), detail=reason, http_status=int(http_status))
    if http_status:
        return _format_stage_failure("intake_observation", detail=reason, http_status=int(http_status))
    return _format_stage_failure("intake_observation", detail=reason)


def _format_intake_skipped(exc: LiveEvalIntakeSkippedError) -> str:
    payload = exc.payload or {}
    reason = str(payload.get("intake_skip_reason") or payload.get("reason") or "intake_skipped")
    return _format_stage_failure("intake_observation", detail=reason)


def validate_r3_pre_execute_gates(
    *,
    runtime_sha: str,
    repo_root: Path,
    render_rows: list[dict[str, Any]],
    approval: R3ApprovalArtifact,
    recipient_email: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    blockers: list[str] = []
    config = get_live_eval_config()
    senders = sorted(config.sender_emails)
    sender_email = senders[0] if senders else ""

    sender_readiness = run_sender_readiness_read_only(
        expected_sender=sender_email,
        expected_recipient=recipient_email,
        config=config,
    )
    recipient_readiness = run_recipient_gmail_readiness(
        expected_recipient=recipient_email,
        config=config,
    )
    reply_provider_readiness = run_r3_live_reply_provider_readiness(
        tenant_id=LIVE_EVAL_TENANT_ID,
        expected_recipient=recipient_email,
        expected_sender=sender_email,
    )
    db = SessionLocal()
    try:
        tenant_intake = run_r3_tenant_intake_readiness(
            db,
            tenant_id=LIVE_EVAL_TENANT_ID,
            manifest=manifest,
        )
    finally:
        db.close()
    if not tenant_intake.tenant_intake_ready:
        blockers.extend(tenant_intake.blockers)
    readiness = evaluate_r3_execution_readiness(
        runtime_sha=runtime_sha,
        repo_root=repo_root,
        render_rows=render_rows,
        approval=approval,
        recipient_email=recipient_email,
        manifest=manifest,
    )
    if not sender_readiness.ready:
        blockers.extend(sender_readiness.issues)
    if not recipient_readiness.ready:
        blockers.extend(recipient_readiness.blockers)
    if not reply_provider_readiness.get("reply_provider_ready"):
        blockers.extend(reply_provider_readiness.get("blockers") or [])
        blockers.append("R3 reply provider not ready — block before inbound trigger")
    if reply_provider_readiness.get("reply_provider_source") != "live_eval_recipient_env":
        blockers.append("reply_provider_source must be live_eval_recipient_env")
    if reply_provider_readiness.get("stub_fallback_possible"):
        blockers.append("stub_fallback_possible must be false for R3 reply provider")
    if reply_provider_readiness.get("tenant_google_mail_used"):
        blockers.append("tenant_google_mail_used must be false for R3 reply provider")

    from app.evaluation.profile_testbot.qualification.coworker_r3_approval_materialization_contract import (
        run_r3_approval_materialization_readiness,
    )

    approval_mat = run_r3_approval_materialization_readiness(
        manifest=manifest,
        approval_artifact=approval.payload,
        runtime_sha=runtime_sha,
    )
    if not approval_mat.get("approval_materialization_contract_valid"):
        blockers.extend(approval_mat.get("blockers") or [])
        blockers.append("approval materialization contract not ready — block before inbound trigger")
    if int(approval_mat.get("approval_materialization_send_ready_count") or 0) != 8:
        blockers.append("approval_materialization_send_ready_count must be 8")
    if int(approval_mat.get("approval_materialization_no_send_ready_count") or 0) != 7:
        blockers.append("approval_materialization_no_send_ready_count must be 7")
    if approval_mat.get("PTB-DCQ-0088_expected_approval_state") != "pending":
        blockers.append("PTB-DCQ-0088 expected_approval_state must be pending via R3 override")
    if approval_mat.get("PTB-DCQ-0088_base_policy_authorization") != "hold_for_review":
        blockers.append("PTB-DCQ-0088 base policy must remain hold_for_review")

    if recipient_readiness.recipient_credential_source != "live_eval_recipient_env":
        blockers.append("recipient credential source must be live_eval_recipient_env")
    if recipient_readiness.delivery_observation_credential_source != "live_eval_recipient_env":
        blockers.append("delivery observation credential source must be live_eval_recipient_env")
    if not recipient_readiness.credential_source_match:
        blockers.append("recipient and delivery observation credential sources must match")
    if not recipient_readiness.delivery_observation_path_ready:
        blockers.append("delivery observation path probe failed")
    blockers.extend(readiness.get("execution_blockers") or [])
    blockers = list(dict.fromkeys(blockers))
    ready = (
        sender_readiness.ready
        and recipient_readiness.ready
        and bool(reply_provider_readiness.get("reply_provider_ready"))
        and tenant_intake.tenant_intake_ready
        and readiness.get("r3_canary_ready_for_execution")
        and not blockers
    )
    return {
        "ready": bool(ready),
        "failure_stage": None if ready else "pre_execute_readiness",
        "blockers": blockers,
        "sender_readiness": {
            "ready": sender_readiness.ready,
            "issues": sender_readiness.issues,
        },
        "recipient_readiness": recipient_readiness.to_dict(),
        "reply_provider_readiness": reply_provider_readiness,
        "reply_provider_ready": bool(reply_provider_readiness.get("reply_provider_ready")),
        "reply_provider_source": reply_provider_readiness.get("reply_provider_source"),
        "stub_fallback_possible": bool(reply_provider_readiness.get("stub_fallback_possible")),
        "approval_materialization_readiness": approval_mat,
        "approval_materialization_contract_valid": bool(
            approval_mat.get("approval_materialization_contract_valid")
        ),
        "approval_materialization_send_ready_count": int(
            approval_mat.get("approval_materialization_send_ready_count") or 0
        ),
        "approval_materialization_no_send_ready_count": int(
            approval_mat.get("approval_materialization_no_send_ready_count") or 0
        ),
        "r3_hold_override_scenarios": list(approval_mat.get("r3_hold_override_scenarios") or []),
        "r3_hold_override_count": int(approval_mat.get("r3_hold_override_count") or 0),
        "PTB-DCQ-0088_base_policy_authorization": approval_mat.get(
            "PTB-DCQ-0088_base_policy_authorization"
        ),
        "PTB-DCQ-0088_override_eligible": approval_mat.get("PTB-DCQ-0088_override_eligible"),
        "PTB-DCQ-0088_expected_approval_state": approval_mat.get(
            "PTB-DCQ-0088_expected_approval_state"
        ),
        "approval_materialization_ready": bool(approval_mat.get("approval_materialization_ready")),
        "recipient_credential_source": recipient_readiness.recipient_credential_source,
        "delivery_observation_credential_source": recipient_readiness.delivery_observation_credential_source,
        "credential_source_match": recipient_readiness.credential_source_match,
        "delivery_observation_path_ready": recipient_readiness.delivery_observation_path_ready,
        "mutation_contract_valid": True,
        "process_delivery_operation_allowed": True,
        "intake_credential_source": recipient_readiness.recipient_credential_source,
        "intake_credential_source_match": recipient_readiness.credential_source_match,
        "exact_message_read_ready": recipient_readiness.delivery_observation_path_ready,
        "process_delivery_path_ready": (
            recipient_readiness.credential_source_match
            and recipient_readiness.delivery_observation_path_ready
            and recipient_readiness.recipient_credential_source == "live_eval_recipient_env"
        ),
        "registration_contract_valid": readiness.get("registration_contract_valid"),
        "tenant_intake_ready": tenant_intake.tenant_intake_ready,
        "tenant_config_exists": tenant_intake.tenant_config_exists,
        "intake_cutoff_at_redacted": tenant_intake.intake_cutoff_at_redacted,
        "intake_cutoff_age_seconds": tenant_intake.intake_cutoff_age_seconds,
        "intake_cutoff_fresh": tenant_intake.intake_cutoff_fresh,
        "tenant_intake_blockers": list(tenant_intake.blockers),
    }


def approval_artifact_hash(payload: dict[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def redact_email(value: str | None) -> str:
    if not value:
        return ""
    local, _, domain = value.partition("@")
    if not domain:
        return "[REDACTED_EMAIL]"
    return f"{local[:2]}…@{domain}"


def redact_provider_id(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return f"{value[:2]}…"
    return f"{value[:4]}…{value[-4:]}"


def approval_operation_id(campaign_id: str, scenario_id: str) -> str:
    return f"{campaign_id}:{scenario_id}:approval"


def reply_operation_id(scenario_id: str) -> str:
    return f"reply-op-{scenario_id.lower()}"


def scan_for_secrets(payload: str) -> list[str]:
    issues: list[str] = []
    if re.search(r"(?i)(refresh_token|access_token|client_secret)\s*[:=]", payload):
        issues.append("token_or_secret_pattern")
    if re.search(r"ya29\.[A-Za-z0-9_-]+", payload):
        issues.append("oauth_access_token_pattern")
    if EMAIL_RE.search(payload) and "[REDACTED_EMAIL]" not in payload:
        raw_emails = EMAIL_RE.findall(payload)
        allowed = {"sender@eval.test"}
        if any(email not in allowed for email in raw_emails):
            issues.append("unredacted_email")
    return issues


def recipient_matches_approval(recipient_email: str) -> bool:
    local, _, domain = recipient_email.lower().partition("@")
    return (
        domain == R3_APPROVED_RECIPIENT_DOMAIN
        and local.startswith(R3_APPROVED_RECIPIENT_LOCAL_PREFIX)
    )


def load_approval_artifact(path: Path) -> R3ApprovalArtifact:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return R3ApprovalArtifact(
        path=path,
        payload=payload,
        artifact_hash=approval_artifact_hash(payload),
    )


def load_manifest_file(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_scenario_allowlist(scenario_ids: list[str]) -> list[str]:
    issues: list[str] = []
    expected = list(COWORKER_LIVE_CANARY_SCENARIO_IDS)
    if scenario_ids != expected:
        issues.append(
            f"scenario allowlist mismatch: expected {expected}, got {scenario_ids}"
        )
    if set(scenario_ids) != R3_SEND_SCENARIO_IDS | R3_NO_SEND_SCENARIO_IDS:
        issues.append("scenario set does not match locked send/no-send union")
    send_ids = [sid for sid in scenario_ids if sid in R3_SEND_SCENARIO_IDS]
    no_send_ids = [sid for sid in scenario_ids if sid in R3_NO_SEND_SCENARIO_IDS]
    if len(send_ids) != COWORKER_LIVE_CANARY_SEND_MAX:
        issues.append(f"send scenario count {len(send_ids)} != {COWORKER_LIVE_CANARY_SEND_MAX}")
    if len(no_send_ids) != COWORKER_LIVE_CANARY_TARGET - COWORKER_LIVE_CANARY_SEND_MAX:
        issues.append(
            f"no-send scenario count {len(no_send_ids)} != "
            f"{COWORKER_LIVE_CANARY_TARGET - COWORKER_LIVE_CANARY_SEND_MAX}"
        )
    return issues


def validate_manifest_contract(manifest: dict[str, Any]) -> list[str]:
    return validate_r3_manifest_registration_contract(manifest)


def validate_approval_artifact(
    approval: R3ApprovalArtifact,
    *,
    recipient_email: str,
    runtime_sha: str,
) -> list[str]:
    issues: list[str] = []
    payload = approval.payload
    if payload.get("approval_type") != R3_APPROVAL_TYPE:
        issues.append("approval_type mismatch")
    if payload.get("tenant_id") != LIVE_EVAL_TENANT_ID:
        issues.append(f"approval tenant {payload.get('tenant_id')!r} != {LIVE_EVAL_TENANT_ID}")
    if not approval.approved:
        issues.append("approval artifact is not in APPROVED state")
    send_ids = list(payload.get("send_scenario_ids") or [])
    if set(send_ids) != R3_SEND_SCENARIO_IDS:
        issues.append("approval send_scenario_ids mismatch")
    if payload.get("body_hashes_approved") is not True:
        issues.append("body_hashes_approved is not true")
    if payload.get("human_render_rereview_required") is True:
        issues.append("human_render_rereview_required is true in approval artifact")
    if not recipient_matches_approval(recipient_email):
        issues.append("recipient does not match approved test recipient")
    return issues


def _load_render_package():
    root = Path(__file__).resolve().parents[4]
    pkg_path = root / "scripts" / "build_digital_coworker_human_review_package.py"
    spec = importlib.util.spec_from_file_location(
        "build_digital_coworker_human_review_package",
        pkg_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load human review package builder")
    pkg = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = pkg
    spec.loader.exec_module(pkg)
    return pkg


def build_r3_diagnostic_live_render_rows(
    *,
    campaign_id: str,
    profile_id: str = PROFILE_ID,
    seed: int = 0,
) -> list[dict[str, Any]]:
    pkg = _load_render_package()
    render_scenario_full = pkg.render_scenario_full
    redact_text = pkg.redact_text
    renderer_label = pkg._renderer_label

    manifest = build_coworker_live_canary_manifest(profile_id=profile_id, seed=seed)
    render_rows: list[dict[str, Any]] = []
    for scenario in manifest.scenarios:
        if scenario.scenario_id == PTB_SEM_0024_SCENARIO_ID:
            render_rows.append(
                {
                    "scenario_id": scenario.scenario_id,
                    "expected_send_behavior": scenario.expected_send_behavior,
                    "planned_gmail_send": False,
                    "approval_required": False,
                    "renderer_mode": "reject_no_reply",
                    "fallback_stage": "reject",
                    "final_customer_text_validation": {
                        "passed": True,
                        "validation_stage": "reject",
                    },
                    "final_customer_text": "",
                    "body_hash": body_hash(""),
                    "approved_body_hash": None,
                    "body_hash_matches_approved": None,
                    "oracle_blocking_failures": [],
                    "oracle_passed": True,
                    "approval_operation_id": approval_operation_id(
                        campaign_id, scenario.scenario_id
                    ),
                    "reply_operation_id": None,
                }
            )
            continue

        item = render_scenario_full(scenario)
        final_validation = (item.render_validation or {}).get(
            "final_customer_text_validation"
        ) or {}
        blocking = [
            o for o in item.oracles if o.get("blocking") and o.get("status") == "fail"
        ]
        planned_send = (
            scenario.expected_send_behavior in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND
            and not blocking
            and bool(item.body.strip())
            and final_validation.get("passed") is not False
        )
        current_hash = item.provenance.get("body_hash") or body_hash(item.body)
        approved_hash = R3_APPROVED_SEND_BODY_HASHES.get(scenario.scenario_id)
        render_rows.append(
            {
                "scenario_id": scenario.scenario_id,
                "expected_send_behavior": scenario.expected_send_behavior,
                "planned_gmail_send": planned_send,
                "approval_required": scenario.expected_send_behavior
                in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND,
                "renderer_mode": renderer_label(item.provenance),
                "fallback_stage": final_validation.get("validation_stage", "n/a"),
                "final_customer_text_validation": final_validation,
                "final_customer_text": redact_text(item.body),
                "body_hash": current_hash,
                "approved_body_hash": approved_hash,
                "body_hash_matches_approved": (
                    approved_hash == current_hash if planned_send else None
                ),
                "oracle_blocking_failures": [o.get("name") for o in blocking],
                "oracle_passed": not blocking,
                "approval_operation_id": approval_operation_id(
                    campaign_id, scenario.scenario_id
                ),
                "reply_operation_id": reply_operation_id(scenario.scenario_id)
                if planned_send
                else None,
            }
        )
    return render_rows


def build_r3_frozen_execution_rows(
    *,
    manifest: dict[str, Any],
    campaign_id: str,
    profile_id: str = PROFILE_ID,
    seed: int = 0,
) -> list[dict[str, Any]]:
    frozen_bodies = resolve_frozen_send_bodies(manifest)
    built = build_coworker_live_canary_manifest(profile_id=profile_id, seed=seed)
    scenarios_by_id = {scenario.scenario_id: scenario for scenario in built.scenarios}
    rows: list[dict[str, Any]] = []
    for scenario_id in COWORKER_LIVE_CANARY_SCENARIO_IDS:
        scenario = scenarios_by_id[scenario_id]
        if scenario_id == PTB_SEM_0024_SCENARIO_ID:
            rows.append(
                {
                    "scenario_id": scenario_id,
                    "expected_send_behavior": scenario.expected_send_behavior,
                    "planned_gmail_send": False,
                    "approval_required": False,
                    "renderer_mode": "reject_no_reply",
                    "fallback_stage": "reject",
                    "body_source": "frozen_no_send",
                    "final_customer_text_validation": {
                        "passed": True,
                        "validation_stage": "reject",
                    },
                    "final_customer_text": "",
                    "frozen_customer_text": "",
                    "body_hash": body_hash(""),
                    "approved_body_hash": None,
                    "body_hash_matches_approved": None,
                    "oracle_blocking_failures": [],
                    "oracle_passed": True,
                    "approval_operation_id": approval_operation_id(
                        campaign_id, scenario_id
                    ),
                    "reply_operation_id": None,
                }
            )
            continue

        frozen_text = frozen_bodies.get(scenario_id, "")
        approved_hash = R3_APPROVED_SEND_BODY_HASHES.get(scenario_id)
        current_hash = body_hash(frozen_text) if frozen_text.strip() else body_hash("")
        oracle_results = evaluate_coworker_reply_oracles(
            scenario=scenario,
            reply_body=frozen_text,
            plan_v2=None,
            provenance=None,
            render_validation={
                "final_customer_text_validation": {
                    "passed": True,
                    "validation_stage": "frozen_approved_body",
                    "validated_body_hash": current_hash,
                }
            },
        )
        blocking = [
            oracle.name
            for oracle in oracle_results
            if oracle.blocker and oracle.status == "fail"
        ]
        final_validation = {
            "passed": bool(frozen_text.strip()) and current_hash == approved_hash and not blocking,
            "validation_stage": "frozen_approved_body",
            "validated_body_hash": current_hash,
            "issues": [] if current_hash == approved_hash else ["frozen body hash mismatch"],
        }
        planned_send = (
            scenario.expected_send_behavior in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND
            and not blocking
            and bool(frozen_text.strip())
            and final_validation.get("passed") is not False
        )
        rows.append(
            {
                "scenario_id": scenario_id,
                "expected_send_behavior": scenario.expected_send_behavior,
                "planned_gmail_send": planned_send,
                "approval_required": scenario.expected_send_behavior
                in SEND_BEHAVIORS_COUNTING_AS_GMAIL_SEND,
                "renderer_mode": "frozen_approved_body",
                "fallback_stage": "frozen_approved_body",
                "body_source": "frozen_manifest",
                "final_customer_text_validation": final_validation,
                "final_customer_text": frozen_text,
                "frozen_customer_text": frozen_text,
                "body_hash": current_hash,
                "approved_body_hash": approved_hash,
                "body_hash_matches_approved": (
                    approved_hash == current_hash if planned_send else None
                ),
                "oracle_blocking_failures": blocking,
                "oracle_passed": not blocking,
                "approval_operation_id": approval_operation_id(campaign_id, scenario_id),
                "reply_operation_id": reply_operation_id(scenario_id)
                if planned_send
                else None,
            }
        )
    return rows


def build_r3_render_rows(
    *,
    manifest: dict[str, Any] | None = None,
    campaign_id: str,
    profile_id: str = PROFILE_ID,
    seed: int = 0,
) -> list[dict[str, Any]]:
    return build_r3_frozen_execution_rows(
        manifest=manifest or {},
        campaign_id=campaign_id,
        profile_id=profile_id,
        seed=seed,
    )


def validate_frozen_execution_rows(render_rows: list[dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    by_id = {row["scenario_id"]: row for row in render_rows}
    if set(by_id) != set(COWORKER_LIVE_CANARY_SCENARIO_IDS):
        issues.append("render rows missing or extra scenarios")
    planned_sends = [row for row in render_rows if row.get("planned_gmail_send")]
    no_send = [row for row in render_rows if not row.get("planned_gmail_send")]
    if len(planned_sends) != COWORKER_LIVE_CANARY_SEND_MAX:
        issues.append(f"planned sends {len(planned_sends)} != {COWORKER_LIVE_CANARY_SEND_MAX}")
    if len(no_send) != COWORKER_LIVE_CANARY_TARGET - COWORKER_LIVE_CANARY_SEND_MAX:
        issues.append(f"no-send rows {len(no_send)} != expected")
    for row in planned_sends:
        if not row.get("approval_required"):
            issues.append(f"{row['scenario_id']} missing approval_required")
        validation = row.get("final_customer_text_validation") or {}
        if validation.get("passed") is False:
            issues.append(f"{row['scenario_id']} final customer text validation failed")
        if row.get("oracle_blocking_failures"):
            issues.append(
                f"{row['scenario_id']} blocking oracles: {row['oracle_blocking_failures']}"
            )
        if not row.get("body_hash_matches_approved"):
            issues.append(f"{row['scenario_id']} body hash does not match approved hash")
    return issues


def validate_render_rows(render_rows: list[dict[str, Any]]) -> list[str]:
    return validate_frozen_execution_rows(render_rows)


def evaluate_r3_execution_readiness(
    *,
    runtime_sha: str,
    repo_root: Path,
    render_rows: list[dict[str, Any]],
    approval: R3ApprovalArtifact,
    recipient_email: str,
    manifest: dict[str, Any],
) -> dict[str, Any]:
    readiness = evaluate_coworker_r3_readiness(
        phase="postdeploy",
        profile_id=PROFILE_ID,
        tenant_id=LIVE_EVAL_TENANT_ID,
        instrumentation_merge_sha=runtime_sha,
        repo_root=repo_root,
        render_rows=render_rows,
        send_budget=COWORKER_LIVE_CANARY_SEND_MAX,
        no_send_count=COWORKER_LIVE_CANARY_TARGET - COWORKER_LIVE_CANARY_SEND_MAX,
    )
    blockers = list(readiness.stop_conditions)
    blockers.extend(validate_manifest_contract(manifest))
    blockers.extend(validate_approval_artifact(approval, recipient_email=recipient_email, runtime_sha=runtime_sha))
    blockers.extend(validate_render_rows(render_rows))
    registration = validate_r3_campaign_registration_contract(
        manifest=manifest,
        runtime_sha=runtime_sha,
        recipient_email=recipient_email,
        render_rows=render_rows,
    )
    blockers.extend(registration.registration_blockers)
    blockers = list(dict.fromkeys(blockers))
    ready = (
        readiness.postdeploy_preflight_pass
        and readiness.runtime_sha_consistent
        and readiness.runner_sha_auditable
        and approval.approved
        and recipient_matches_approval(recipient_email)
        and not readiness.human_render_rereview_required
        and registration.registration_contract_valid
        and not blockers
    )
    frozen_ready = ready and not validate_frozen_send_bodies(manifest=manifest)
    return {
        **readiness.to_dict(),
        **registration.to_dict(),
        "approval_artifact_valid": approval.approved and not validate_approval_artifact(
            approval, recipient_email=recipient_email, runtime_sha=runtime_sha
        ),
        "approval_artifact_hash": approval.artifact_hash,
        "manual_send_approval": "APPROVED" if approval.approved else "BLOCKED",
        "recipient_match": recipient_matches_approval(recipient_email),
        "scenario_allowlist_match": not validate_scenario_allowlist(
            list(manifest.get("scenario_ids") or [])
        ),
        "all_approved_body_hashes_match": not any(
            not row.get("body_hash_matches_approved")
            for row in render_rows
            if row.get("planned_gmail_send")
        ),
        "frozen_approved_bodies_verified": frozen_ready,
        "blocking_oracle_failures": sum(
            len(row.get("oracle_blocking_failures") or [])
            for row in render_rows
        ),
        "r3_canary_ready_for_execution": frozen_ready,
        "execution_blockers": blockers,
        "manual_execution_confirmation": (
            "MANUAL EXECUTION CONFIRMATION REQUIRED — Frozen approved bodies verifierade 8/8; godkänn R3 live-canary från ny execution-SHA"
            if frozen_ready
            else None
        ),
    }


def _assert_no_send_scenario(
    *,
    scenario: ProfileScenario,
    backend: LiveSemiAutoBackend,
    sends_before: int,
    draft_text: str,
    approval_state: str,
) -> None:
    if backend.gmail_sends != sends_before:
        raise LiveEvalSafetyError(
            f"{scenario.scenario_id}: unexpected Gmail send on no-send scenario"
        )
    if scenario.expected_send_behavior in {"reject", "no_reply"} and draft_text.strip():
        raise LiveEvalSafetyError(
            f"{scenario.scenario_id}: reject/no_reply produced customer body"
        )
    if scenario.expected_send_behavior == "draft_for_approval":
        # Internal approval queue may exist; Gmail outbound must remain zero.
        if backend.gmail_sends > sends_before:
            raise LiveEvalSafetyError(
                f"{scenario.scenario_id}: draft_for_approval produced Gmail send"
            )
    if scenario.scenario_id == PTB_SEM_0024_SCENARIO_ID and approval_state == "pending":
        raise LiveEvalSafetyError(f"{scenario.scenario_id}: adversarial reject has pending approval")


def _execute_live_scenario(
    *,
    campaign_id: str,
    scenario: ProfileScenario,
    backend: LiveSemiAutoBackend,
    render_row: dict[str, Any],
    recipient_email: str,
    claimed_operations: set[str],
    gmail_send_budget_remaining: int,
) -> R3ScenarioOutcome:
    scenario_id = scenario.scenario_id
    planned_send = bool(render_row.get("planned_gmail_send"))
    approval_op = approval_operation_id(campaign_id, scenario_id)
    reply_op = reply_operation_id(scenario_id) if planned_send else None
    for op in (approval_op, reply_op):
        if op and op in claimed_operations:
            raise LiveEvalSafetyError(f"duplicate operation claim: {op}")
    if approval_op:
        claimed_operations.add(approval_op)
    if reply_op:
        claimed_operations.add(reply_op)

    outcome = R3ScenarioOutcome(
        scenario_id=scenario_id,
        planned_gmail_send=planned_send,
        status="started",
        approved_body_hash=render_row.get("approved_body_hash"),
        approval_operation_id=approval_op,
        reply_operation_id=reply_op,
        recipient_redacted=redact_email(recipient_email),
    )

    if planned_send and gmail_send_budget_remaining < 1:
        outcome.status = "blocked"
        outcome.failure_reason = "send budget exhausted"
        return outcome

    if scenario_id == PTB_SEM_0024_SCENARIO_ID:
        outcome.status = "verified_no_send"
        outcome.execution_outcome = "reject_no_reply"
        return outcome

    sends_before = backend.gmail_sends
    idempotency_key = f"{campaign_id}:{scenario_id}:send"
    if idempotency_key in backend.sent_keys:
        raise LiveEvalSafetyError(f"duplicate replay blocked: {idempotency_key}")

    try:
        send_result = backend.send_test_message(
            campaign_id=campaign_id,
            scenario=scenario,
            idempotency_key=idempotency_key,
        )
    except httpx.HTTPStatusError as exc:
        outcome.status = "failed"
        outcome.failure_stage = "live_run_registration"
        outcome.failure_reason = _format_stage_failure(
            "live_run_registration",
            detail=_sanitize_http_detail(exc.response),
            http_status=exc.response.status_code if exc.response else None,
        )
        return outcome
    except LiveEvalSafetyError as exc:
        outcome.status = "failed"
        outcome.failure_stage = "inbound_trigger_send"
        outcome.failure_reason = _format_stage_failure("inbound_trigger_send", detail=str(exc))
        return outcome
    outcome.audit_events.append(
        {
            "event": "inbound_trigger_sent",
            "at": _utc_now(),
            "idempotency_key": idempotency_key,
            "provider_message_id": redact_provider_id(send_result.provider_message_id),
            "classification": "inbound_trigger_sent",
        }
    )

    try:
        intake = backend.observe_intake(scenario_id=scenario_id, campaign_id=campaign_id)
    except LiveEvalSafetyRejectedError as exc:
        outcome.status = "failed"
        outcome.failure_stage = "intake_observation"
        outcome.failure_reason = _format_safety_rejected(exc)
        return outcome
    except LiveEvalIntakeSkippedError as exc:
        outcome.status = "failed"
        outcome.failure_stage = "intake_observation"
        outcome.failure_reason = _format_intake_skipped(exc)
        return outcome
    except httpx.HTTPStatusError as exc:
        outcome.status = "failed"
        outcome.failure_stage = "delivery_observation"
        outcome.failure_reason = _format_stage_failure(
            "delivery_observation",
            detail=_sanitize_http_detail(exc.response),
            http_status=exc.response.status_code if exc.response else None,
        )
        return outcome
    except LiveEvalSafetyError as exc:
        outcome.status = "failed"
        outcome.failure_stage = "intake_observation"
        outcome.failure_reason = _format_stage_failure("intake_observation", detail=str(exc))
        return outcome
    if intake.tenant_id != LIVE_EVAL_TENANT_ID:
        raise LiveEvalSafetyError("cross-tenant intake blocked")
    try:
        processing = backend.observe_processing(scenario_id=scenario_id)
    except httpx.HTTPStatusError as exc:
        outcome.status = "failed"
        outcome.failure_stage = "processing_observation"
        outcome.failure_reason = _format_stage_failure(
            "processing_observation",
            detail=_sanitize_http_detail(exc.response),
            http_status=exc.response.status_code if exc.response else None,
        )
        return outcome
    except LiveEvalSafetyError as exc:
        outcome.status = "failed"
        outcome.failure_stage = "processing_observation"
        outcome.failure_reason = _format_stage_failure("processing_observation", detail=str(exc))
        return outcome
    outcome.approval_state = processing.approval_state
    draft_text = processing.draft_text or ""
    frozen_text = str(
        render_row.get("frozen_customer_text")
        or render_row.get("final_customer_text")
        or ""
    )
    frozen_hash = body_hash(frozen_text) if frozen_text.strip() else body_hash("")
    pipeline_hash = body_hash(draft_text) if draft_text.strip() else body_hash("")
    outcome.body_hash = frozen_hash
    validation = render_row.get("final_customer_text_validation") or {}
    outcome.final_validation_passed = validation.get("passed") is not False

    if planned_send:
        approved_hash = str(render_row.get("approved_body_hash") or "")
        outcome.body_hash_matches_approved = frozen_hash == approved_hash
        if not frozen_text.strip():
            outcome.status = "blocked"
            outcome.failure_reason = "missing frozen approved body"
            outcome.execution_outcome = "frozen_body_missing"
            return outcome
        if not outcome.body_hash_matches_approved:
            outcome.status = "blocked"
            outcome.failure_reason = "frozen body hash does not match approved hash"
            outcome.execution_outcome = "hash_mismatch"
            return outcome
        if processing.approval_state != "pending":
            outcome.status = "failed"
            outcome.failure_reason = f"unexpected approval_state={processing.approval_state}"
            return outcome
        if render_row.get("oracle_blocking_failures"):
            outcome.blocking_oracle_failures = list(render_row["oracle_blocking_failures"])
            outcome.status = "failed"
            outcome.failure_reason = "blocking oracle failures in frozen precheck"
            return outcome
        outcome.audit_events.append(
            {
                "event": "frozen_body_verified",
                "at": _utc_now(),
                "body_hash": frozen_hash,
                "body_source": render_row.get("body_source", "frozen_manifest"),
                "pipeline_body_hash": pipeline_hash,
                "pipeline_body_hash_matches_frozen": pipeline_hash == frozen_hash,
            }
        )
        backend.bind_frozen_send_body(
            scenario_id=scenario_id,
            frozen_body=frozen_text,
            expected_body_hash=approved_hash,
        )
        approval = backend.approve_via_lifecycle(
            scenario_id=scenario_id,
            operation_id=approval_op,
            decision="approve",
        )
        if approval.already_resolved:
            raise LiveEvalSafetyError(f"duplicate approval for {approval_op}")
        outcome.audit_events.append(
            {
                "event": "approval_granted",
                "at": _utc_now(),
                "operation_id": approval_op,
                "reply_operation_id": approval.reply_action_operation_id,
            }
        )
        reply = backend.verify_reply(
            scenario=scenario,
            approved=True,
            inbound_provider_message_id=send_result.inbound_provider_message_id,
            inbound_rfc_message_id=send_result.inbound_rfc_message_id,
        )
        if reply.duplicate_send:
            raise LiveEvalSafetyError(f"duplicate send detected for {scenario_id}")
        if reply.reply_execution_status == "outcome_unknown":
            outcome.status = "unknown"
            outcome.execution_outcome = "outcome_unknown"
            outcome.failure_reason = "reply execution outcome unknown — manual reconciliation required"
            return outcome
        if not reply.provider_accepted:
            outcome.status = "failed"
            outcome.execution_outcome = reply.reply_execution_status or "not_observed"
            outcome.failure_reason = f"reply not provider accepted: {reply.reply_execution_status}"
            return outcome
        if not reply.recipient_verified:
            outcome.status = "failed"
            outcome.execution_outcome = "recipient_mismatch"
            outcome.failure_reason = "recipient verification failed"
            return outcome
        outcome.provider_message_id_redacted = redact_provider_id(
            reply.reply_provider_message_id
        )
        outcome.execution_outcome = "sent"
        outcome.status = "sent"
        outcome.audit_events.append(
            {
                "event": "gmail_send_verified",
                "at": _utc_now(),
                "provider_message_id": outcome.provider_message_id_redacted,
                "sent_body_hash": frozen_hash,
                "body_source": render_row.get("body_source", "frozen_manifest"),
            }
        )
        assert_no_external_writes(backend)
        return outcome

    _assert_no_send_scenario(
        scenario=scenario,
        backend=backend,
        sends_before=sends_before,
        draft_text=draft_text,
        approval_state=processing.approval_state,
    )
    reply = backend.verify_reply(scenario=scenario, approved=False)
    assert_hold_scenario_no_send(
        scenario=scenario,
        sends=0,
        adapter_invocations=reply.adapter_invocations,
    )
    outcome.status = "verified_no_send"
    outcome.execution_outcome = "no_send"
    outcome.audit_events.append({"event": "no_send_verified", "at": _utc_now()})
    assert_no_external_writes(backend)
    return outcome


def run_r3_live_canary(
    *,
    mode: ExecutionMode,
    manifest_path: Path,
    approval_path: Path,
    expected_runtime_sha: str,
    repo_root: Path,
    campaign_id: str | None = None,
    base_url: str | None = None,
    admin_api_key: str | None = None,
    backend: LiveSemiAutoBackend | None = None,
) -> R3ExecutionResult:
    campaign_id = campaign_id or str(uuid.uuid4())
    manifest = load_manifest_file(manifest_path)
    approval = load_approval_artifact(approval_path)
    runtime_sha = expected_runtime_sha.strip()

    config = get_live_eval_config()
    senders = sorted(config.sender_emails)
    recipients = sorted(config.recipient_emails)
    sender_email = senders[0] if senders else ""
    recipient_email = recipients[0] if recipients else ""
    base_url = (base_url or os.environ.get("LIVE_EVAL_APP_BASE_URL", "")).strip()
    admin_api_key = (admin_api_key or os.environ.get("ADMIN_API_KEY", "")).strip()

    render_rows = build_r3_frozen_execution_rows(
        manifest=manifest,
        campaign_id=campaign_id,
    )
    readiness = evaluate_r3_execution_readiness(
        runtime_sha=runtime_sha,
        repo_root=repo_root,
        render_rows=render_rows,
        approval=approval,
        recipient_email=recipient_email,
        manifest=manifest,
    )

    if not readiness.get("r3_canary_ready_for_execution"):
        return R3ExecutionResult(
            mode=mode,
            campaign_id=campaign_id,
            runtime_sha=runtime_sha,
            manifest_hash=str(manifest.get("manifest_hash") or ""),
            approval_artifact_hash=approval.artifact_hash,
            overall_status="BLOCKED",
            planned_sends=COWORKER_LIVE_CANARY_SEND_MAX,
            successful_sends=0,
            failed_sends=0,
            unknown_outcomes=0,
            no_send_verified=0,
            duplicates_blocked=0,
            human_render_rereview_required=bool(
                readiness.get("human_render_rereview_required")
            ),
            stop_reason="; ".join(readiness.get("execution_blockers") or ["not ready"]),
            failure_stage="pre_execute_readiness",
            scenario_outcomes=[],
            readiness=readiness,
            orphaned_inbound_triggers=list(ORPHANED_R3_INBOUND_TRIGGERS),
        )

    if mode == "execute":
        pre_execute = validate_r3_pre_execute_gates(
            runtime_sha=runtime_sha,
            repo_root=repo_root,
            render_rows=render_rows,
            approval=approval,
            recipient_email=recipient_email,
            manifest=manifest,
        )
        readiness = {**readiness, **pre_execute}
        if not pre_execute.get("ready"):
            return R3ExecutionResult(
                mode=mode,
                campaign_id=campaign_id,
                runtime_sha=runtime_sha,
                manifest_hash=str(manifest.get("manifest_hash") or ""),
                approval_artifact_hash=approval.artifact_hash,
                overall_status="BLOCKED",
                planned_sends=COWORKER_LIVE_CANARY_SEND_MAX,
                successful_sends=0,
                failed_sends=0,
                unknown_outcomes=0,
                no_send_verified=0,
                duplicates_blocked=0,
                human_render_rereview_required=bool(
                    readiness.get("human_render_rereview_required")
                ),
                stop_reason="; ".join(pre_execute.get("blockers") or ["pre_execute_readiness"]),
                failure_stage="pre_execute_readiness",
                scenario_outcomes=[],
                readiness=readiness,
                orphaned_inbound_triggers=list(ORPHANED_R3_INBOUND_TRIGGERS),
            )

    profile = load_customer_profile(PROFILE_ID)
    built = build_coworker_live_canary_manifest(profile_id=PROFILE_ID, seed=0)
    scenarios_by_id = {s.scenario_id: s for s in built.scenarios}
    render_by_id = {row["scenario_id"]: row for row in render_rows}

    if mode == "dry_run":
        pre_execute = validate_r3_pre_execute_gates(
            runtime_sha=runtime_sha,
            repo_root=repo_root,
            render_rows=render_rows,
            approval=approval,
            recipient_email=recipient_email,
            manifest=manifest,
        )
        readiness = {**readiness, **pre_execute}
        dry_outcomes = []
        for scenario_id in COWORKER_LIVE_CANARY_SCENARIO_IDS:
            row = render_by_id[scenario_id]
            dry_outcomes.append(
                R3ScenarioOutcome(
                    scenario_id=scenario_id,
                    planned_gmail_send=bool(row.get("planned_gmail_send")),
                    status="dry_run_planned",
                    body_hash=row.get("body_hash"),
                    approved_body_hash=row.get("approved_body_hash"),
                    body_hash_matches_approved=row.get("body_hash_matches_approved"),
                    recipient_redacted=redact_email(recipient_email),
                    approval_operation_id=row.get("approval_operation_id"),
                    reply_operation_id=row.get("reply_operation_id"),
                    final_validation_passed=(row.get("final_customer_text_validation") or {}).get(
                        "passed"
                    )
                    is not False,
                    blocking_oracle_failures=list(row.get("oracle_blocking_failures") or []),
                )
            )
        blob = json.dumps(readiness, ensure_ascii=False)
        secret_issues = scan_for_secrets(blob)
        dry_status = "DRY_RUN_PASS" if pre_execute.get("ready") else "DRY_RUN_BLOCKED"
        return R3ExecutionResult(
            mode=mode,
            campaign_id=campaign_id,
            runtime_sha=runtime_sha,
            manifest_hash=str(manifest.get("manifest_hash") or ""),
            approval_artifact_hash=approval.artifact_hash,
            overall_status=dry_status,
            planned_sends=COWORKER_LIVE_CANARY_SEND_MAX,
            successful_sends=0,
            failed_sends=0,
            unknown_outcomes=0,
            no_send_verified=sum(1 for row in dry_outcomes if not row.planned_gmail_send),
            duplicates_blocked=0,
            human_render_rereview_required=False,
            stop_reason=None if dry_status == "DRY_RUN_PASS" else "; ".join(pre_execute.get("blockers") or []),
            failure_stage=None if dry_status == "DRY_RUN_PASS" else "pre_execute_readiness",
            scenario_outcomes=dry_outcomes,
            readiness=readiness,
            secret_scan_issues=secret_issues,
            orphaned_inbound_triggers=list(ORPHANED_R3_INBOUND_TRIGGERS),
        )

    assert_tenant_isolated(LIVE_EVAL_TENANT_ID)
    if backend is None:
        if not base_url or not admin_api_key:
            raise LiveEvalSafetyError("LIVE_EVAL_APP_BASE_URL and ADMIN_API_KEY required")
        backend = LiveSemiAutoBackend(
            campaign_id=campaign_id,
            tenant_id=LIVE_EVAL_TENANT_ID,
            sender_email=sender_email,
            recipient_email=recipient_email,
            base_url=base_url,
            admin_api_key=admin_api_key,
            registration_ai_mode=R3_FROZEN_EXECUTION_MODE,
            registration_campaign_type=R3_FROZEN_LIVE_CANARY_CAMPAIGN_TYPE,
            registration_execution_mode=R3_FROZEN_EXECUTION_MODE,
            registration_manifest_hash=str(manifest.get("manifest_hash") or ""),
        )

    claimed_operations: set[str] = set()
    outcomes: list[R3ScenarioOutcome] = []
    successful_sends = 0
    failed_sends = 0
    unknown_outcomes = 0
    no_send_verified = 0
    stop_reason: str | None = None
    failure_stage: str | None = None
    overall_status = "PASS"

    send_budget_remaining = COWORKER_LIVE_CANARY_SEND_MAX
    for scenario_id in COWORKER_LIVE_CANARY_SCENARIO_IDS:
        scenario = scenarios_by_id[scenario_id]
        row = render_by_id[scenario_id]
        try:
            result = _execute_live_scenario(
                campaign_id=campaign_id,
                scenario=scenario,
                backend=backend,
                render_row=row,
                recipient_email=recipient_email,
                claimed_operations=claimed_operations,
                gmail_send_budget_remaining=send_budget_remaining,
            )
        except LiveEvalSafetyRejectedError as exc:
            result = _failed_scenario_outcome(
                scenario_id=scenario_id,
                planned_gmail_send=bool(row.get("planned_gmail_send")),
                failure_stage="intake_observation",
                failure_reason=_format_safety_rejected(exc),
            )
        except LiveEvalIntakeSkippedError as exc:
            result = _failed_scenario_outcome(
                scenario_id=scenario_id,
                planned_gmail_send=bool(row.get("planned_gmail_send")),
                failure_stage="intake_observation",
                failure_reason=_format_intake_skipped(exc),
            )
        except LiveEvalSafetyError as exc:
            result = _failed_scenario_outcome(
                scenario_id=scenario_id,
                planned_gmail_send=bool(row.get("planned_gmail_send")),
                failure_stage="reconciliation",
                failure_reason=str(exc),
            )
        except httpx.HTTPStatusError as exc:
            result = _failed_scenario_outcome(
                scenario_id=scenario_id,
                planned_gmail_send=bool(row.get("planned_gmail_send")),
                failure_stage="delivery_observation",
                failure_reason=_format_stage_failure(
                    "delivery_observation",
                    detail=_sanitize_http_detail(exc.response),
                    http_status=exc.response.status_code if exc.response else None,
                ),
            )
        outcomes.append(result)
        if result.status == "sent":
            successful_sends += 1
            send_budget_remaining -= 1
        elif result.status == "verified_no_send":
            no_send_verified += 1
        elif result.status == "unknown":
            unknown_outcomes += 1
            stop_reason = result.failure_reason
            overall_status = "PARTIAL"
            break
        elif result.status in {"failed", "blocked"}:
            failed_sends += 1 if result.planned_gmail_send else 0
            stop_reason = result.failure_reason
            overall_status = "FAIL" if result.planned_gmail_send else "PARTIAL"
            failure_stage = result.failure_stage
            break

    if overall_status == "PASS":
        if successful_sends != COWORKER_LIVE_CANARY_SEND_MAX:
            overall_status = "PARTIAL"
            stop_reason = f"successful sends {successful_sends} != {COWORKER_LIVE_CANARY_SEND_MAX}"
        elif no_send_verified != COWORKER_LIVE_CANARY_TARGET - COWORKER_LIVE_CANARY_SEND_MAX:
            overall_status = "PARTIAL"
            stop_reason = f"no-send verified {no_send_verified} != expected"

    report = R3ExecutionResult(
        mode=mode,
        campaign_id=campaign_id,
        runtime_sha=runtime_sha,
        manifest_hash=str(manifest.get("manifest_hash") or ""),
        approval_artifact_hash=approval.artifact_hash,
        overall_status=overall_status,
        planned_sends=COWORKER_LIVE_CANARY_SEND_MAX,
        successful_sends=successful_sends,
        failed_sends=failed_sends,
        unknown_outcomes=unknown_outcomes,
        no_send_verified=no_send_verified,
        duplicates_blocked=0,
        human_render_rereview_required=any(
            o.failure_reason and "HUMAN_RENDER_REREVIEW_REQUIRED" in o.failure_reason
            for o in outcomes
        ),
        stop_reason=stop_reason,
        failure_stage=failure_stage,
        scenario_outcomes=outcomes,
        readiness=readiness,
        external_writes=dict(backend.external_writes),
        orphaned_inbound_triggers=list(ORPHANED_R3_INBOUND_TRIGGERS),
    )
    blob = json.dumps(report.to_dict(), ensure_ascii=False)
    report.secret_scan_issues = scan_for_secrets(blob)
    return report


def write_execution_reports(
    *,
    result: R3ExecutionResult,
    status_dir: Path,
) -> dict[str, Path]:
    short = result.runtime_sha[:7]
    status_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary_json": status_dir / f"digital-coworker-r3-live-canary-{short}.json",
        "summary_md": status_dir / f"digital-coworker-r3-live-canary-{short}.md",
        "sends_md": status_dir / f"digital-coworker-r3-live-sends-{short}.md",
        "no_send_md": status_dir / f"digital-coworker-r3-live-no-send-{short}.md",
        "audit_json": status_dir / f"digital-coworker-r3-live-audit-{short}.json",
        "reconciliation_md": status_dir / f"digital-coworker-r3-live-reconciliation-{short}.md",
    }
    payload = result.to_dict()
    payload["generated_at"] = _utc_now()
    paths["summary_json"].write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    audit_payload = {
        "campaign_id": result.campaign_id,
        "runtime_sha": result.runtime_sha,
        "approval_artifact_hash": result.approval_artifact_hash,
        "scenario_outcomes": [
            {
                "scenario_id": row["scenario_id"],
                "audit_events": row.get("audit_events") or [],
                "approval_operation_id": row.get("approval_operation_id"),
                "reply_operation_id": row.get("reply_operation_id"),
            }
            for row in payload.get("scenario_outcomes") or []
        ],
    }
    paths["audit_json"].write_text(
        json.dumps(audit_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    send_rows = [r for r in result.scenario_outcomes if r.planned_gmail_send]
    no_send_rows = [r for r in result.scenario_outcomes if not r.planned_gmail_send]
    paths["sends_md"].write_text(
        "\n".join(
            [
                f"# digital-coworker-r3-live-sends-{short}.md",
                "",
                f"- campaign_id: `{result.campaign_id}`",
                f"- successful_sends: **{result.successful_sends}**",
                "",
                *[
                    f"## {row.scenario_id}\n- status: `{row.status}`\n- body_hash_match: `{row.body_hash_matches_approved}`\n- provider: `{row.provider_message_id_redacted}`"
                    for row in send_rows
                ],
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    paths["no_send_md"].write_text(
        "\n".join(
            [
                f"# digital-coworker-r3-live-no-send-{short}.md",
                "",
                f"- no_send_verified: **{result.no_send_verified}**",
                "",
                *[
                    f"## {row.scenario_id}\n- status: `{row.status}`\n- execution_outcome: `{row.execution_outcome}`"
                    for row in no_send_rows
                ],
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    paths["summary_md"].write_text(
        "\n".join(
            [
                f"# digital-coworker-r3-live-canary-{short}.md",
                "",
                f"- mode: `{result.mode}`",
                f"- overall_status: **{result.overall_status}**",
                f"- campaign_id: `{result.campaign_id}`",
                f"- runtime_sha: `{result.runtime_sha}`",
                f"- manifest_hash: `{result.manifest_hash}`",
                f"- approval_artifact_hash: `{result.approval_artifact_hash}`",
                f"- planned_sends: **{result.planned_sends}**",
                f"- successful_sends: **{result.successful_sends}**",
                f"- no_send_verified: **{result.no_send_verified}**",
                f"- stop_reason: {result.stop_reason or '(none)'}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    paths["reconciliation_md"].write_text(
        "\n".join(
            [
                f"# digital-coworker-r3-live-reconciliation-{short}.md",
                "",
                f"- overall_status: **{result.overall_status}**",
                f"- failed_sends: **{result.failed_sends}**",
                f"- unknown_outcomes: **{result.unknown_outcomes}**",
                f"- external_writes: `{result.external_writes}`",
                f"- secret_scan_issues: `{result.secret_scan_issues}`",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return paths
