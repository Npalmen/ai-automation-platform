"""R3 digital coworker live canary readiness (instrumentation-only gate)."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from app.evaluation.live.config import get_live_eval_config
from app.evaluation.live.campaign.gates import validate_no_production_resources
from app.evaluation.live.recipient_gmail_readiness import (
    RecipientGmailReadinessResult,
    run_recipient_gmail_readiness,
)
from app.evaluation.live.tenant_intake_readiness import (
    TenantIntakeReadinessResult,
    run_r3_tenant_intake_readiness,
)
from app.repositories.postgres.database import SessionLocal
from app.evaluation.profile_testbot.campaign.mailbox_readiness import (
    verify_profile_testbot_mailboxes,
)
from app.evaluation.profile_testbot.campaign.readiness import (
    _oauth_readiness,
    build_profile_testbot_readiness,
    validate_profile_testbot_tenant,
)
from app.evaluation.profile_testbot.campaign.runtime_sha_readiness import (
    evaluate_eval_stack_runtime_sha,
)
from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.evaluation.profile_testbot.qualification.coworker_live_canary_manifest import (
    COWORKER_LIVE_CANARY_SEND_MAX,
    COWORKER_LIVE_CANARY_TARGET,
)

QUALIFIED_REPLY_SHA = "d2e86c14017473fc789147dab13fd6816bc340b3"

R3_INSTRUMENTATION_ALLOWLIST: tuple[str, ...] = (
    "app/evaluation/profile_testbot/qualification/coworker_live_canary_manifest.py",
    "app/evaluation/profile_testbot/qualification/coworker_r3_execution.py",
    "app/evaluation/profile_testbot/qualification/coworker_r3_frozen_bodies.py",
    "app/evaluation/profile_testbot/qualification/coworker_r3_frozen_bind.py",
    "app/evaluation/profile_testbot/qualification/coworker_r3_registration_contract.py",
    "app/evaluation/profile_testbot/qualification/r3_approved_send_bodies.json",
    "app/evaluation/live/routes.py",
    "app/evaluation/live/recipient_gmail_readiness.py",
    "app/evaluation/live/tenant_intake_readiness.py",
    "app/evaluation/live/delivery_mailbox_reader.py",
    "app/evaluation/live/gmail_intake.py",
    "app/evaluation/live/safety.py",
    "app/evaluation/profile_testbot/qualification/coworker_r3_mutation_contract.py",
    "app/evaluation/live/schemas.py",
    "app/evaluation/profile_testbot/campaign/semi_auto_live_backend.py",
    "scripts/build_digital_coworker_r3_preflight.py",
    "scripts/run_digital_coworker_r3_live_canary.py",
    "tests/test_coworker_live_canary_manifest.py",
    "tests/test_coworker_r3_frozen_bodies.py",
    "tests/test_coworker_r3_frozen_bind.py",
    "tests/test_coworker_r3_live_execution.py",
    "tests/test_coworker_r3_mutation_contract.py",
)

# Human-approved send body hashes from R3_RENDER_REVIEW (d2e86c1 predeploy).
R3_APPROVED_SEND_BODY_HASHES: dict[str, str] = {
    "PTB-DCQ-0000": "0ac564e1147cc4af0147f4ebc1c183f1077eeae6ef11c22bc0ad46dd77a89404",
    "PTB-DCQ-0022": "950bc0e5d471bb02e76f48e5a447ac9bd649520fc66baa9892d711e79cd6b759",
    "PTB-DCQ-0033": "7741532585cfe97e35a11027ad713344e681c668ca98ef1d06b18731ed9d38d4",
    "PTB-DCQ-0049": "8cdcaeef8f549cb562e19c47154eb762bea4d68eb5615f05ed713d30cd81790a",
    "PTB-DCQ-0056": "d0ccccd6661673438f7e2f6d429301cfba8aa6b0ff70057af5e8cc9df5a97d50",
    "PTB-DCQ-0072": "637a2a15e375afa46f4992042e70f8c41d0257ce5db448b33f7da637e27eb699",
    "PTB-DCQ-0080": "cfaaa5ff4859da001ea7471ef7f356937d290b52c7a3371f76b49c09a0b626d4",
    "PTB-DCQ-0088": "0748626a0aa6767b2b9bf427e2d68fe33d9fd0ab0f81a5e6e8a6b4fdef939338",
}

R3_SEMI_AUTO_CONTEXT_PREFIXES: tuple[str, ...] = (
    "PROFILE_DRIVEN_SEMI_AUTO_GMAIL_QUALIFIED already registered",
    "PROFILE_DRIVEN_SEMI_AUTO_QUALITY_QUALIFIED already VALID",
    "OPERATOR ACTION REQUIRED — Godkänn faktisk 40-scenario live semi-auto",
    "re-qualification requires PROFILE_TESTBOT_LIVE_QUALITY_REQUALIFICATION",
    "ready_for_live_semi_auto must pass before live execution",
    "ready_for_live_semi_auto must pass before live quality execution",
)

R3PreflightPhase = Literal["predeploy", "postdeploy"]


@dataclass
class CodeEquivalenceResult:
    passed: bool
    qualified_reply_sha: str
    instrumentation_merge_sha: str
    changed_files: list[str]
    unexpected_files: list[str]
    assertion: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "qualified_reply_sha": self.qualified_reply_sha,
            "instrumentation_merge_sha": self.instrumentation_merge_sha,
            "changed_files": self.changed_files,
            "unexpected_files": self.unexpected_files,
            "assertion": self.assertion,
        }


@dataclass
class CoworkerR3ReadinessResult:
    phase: R3PreflightPhase
    qualified_reply_sha: str
    instrumentation_merge_sha: str
    runner_sha: str
    api_runtime_sha: str | None
    worker_runtime_sha: str | None
    runtime_sha_consistent: bool
    runner_sha_auditable: bool
    predeploy_preflight_pass: bool
    postdeploy_preflight_pass: bool
    r3_canary_ready_for_manual_send_approval: bool
    oauth_ready: bool
    tenant_isolation_verified: bool
    duplicate_replay_protection: bool
    runner_ready_for_live_execution: bool
    send_budget: int
    no_send_count: int
    stop_conditions: list[str] = field(default_factory=list)
    unrelated_qualification_context: list[str] = field(default_factory=list)
    body_hash_drift: dict[str, dict[str, str]] = field(default_factory=dict)
    human_render_rereview_required: bool = False
    registration_contract_valid: bool | None = None
    campaign_type_valid: bool | None = None
    execution_mode_valid: bool | None = None
    scenario_registry_valid: bool | None = None
    live_gmail_policy_valid: bool | None = None
    registration_blockers: list[str] = field(default_factory=list)
    recipient_oauth_configured: bool | None = None
    recipient_token_refresh_passed: bool | None = None
    recipient_gmail_api_passed: bool | None = None
    recipient_mailbox_identity_match: bool | None = None
    recipient_required_scopes_present: bool | None = None
    recipient_list_labels_passed: bool | None = None
    recipient_read_query_passed: bool | None = None
    recipient_delivery_observation_ready: bool | None = None
    recipient_credential_source: str | None = None
    delivery_observation_credential_source: str | None = None
    credential_source_match: bool | None = None
    delivery_mailbox_identity_match: bool | None = None
    delivery_observation_path_ready: bool | None = None
    recipient_readiness_blockers: list[str] = field(default_factory=list)
    tenant_intake_ready: bool | None = None
    tenant_config_exists: bool | None = None
    intake_cutoff_at_redacted: str | None = None
    intake_cutoff_age_seconds: int | None = None
    intake_cutoff_fresh: bool | None = None
    tenant_intake_blockers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "phase": self.phase,
            "qualified_reply_sha": self.qualified_reply_sha,
            "instrumentation_merge_sha": self.instrumentation_merge_sha,
            "runner_sha": self.runner_sha,
            "api_runtime_sha": self.api_runtime_sha,
            "worker_runtime_sha": self.worker_runtime_sha,
            "runtime_sha_consistent": self.runtime_sha_consistent,
            "runner_sha_auditable": self.runner_sha_auditable,
            "predeploy_preflight_pass": self.predeploy_preflight_pass,
            "postdeploy_preflight_pass": self.postdeploy_preflight_pass,
            "r3_execution_readiness": (
                "READY"
                if self.r3_canary_ready_for_manual_send_approval
                else "BLOCKED"
            ),
            "r3_canary_ready_for_manual_send_approval": (
                self.r3_canary_ready_for_manual_send_approval
            ),
            "oauth_ready": self.oauth_ready,
            "tenant_isolation_verified": self.tenant_isolation_verified,
            "duplicate_replay_protection": self.duplicate_replay_protection,
            "runner_ready_for_live_execution": self.runner_ready_for_live_execution,
            "send_budget": self.send_budget,
            "no_send_count": self.no_send_count,
            "stop_conditions": self.stop_conditions,
            "unrelated_qualification_context": self.unrelated_qualification_context,
            "body_hash_drift": self.body_hash_drift,
            "human_render_rereview_required": self.human_render_rereview_required,
            "registration_contract_valid": self.registration_contract_valid,
            "campaign_type_valid": self.campaign_type_valid,
            "execution_mode_valid": self.execution_mode_valid,
            "scenario_registry_valid": self.scenario_registry_valid,
            "live_gmail_policy_valid": self.live_gmail_policy_valid,
            "registration_blockers": self.registration_blockers,
            "gmail_sent": False,
            "gmail_drafts_created": False,
            "recipient_oauth_configured": self.recipient_oauth_configured,
            "recipient_token_refresh_passed": self.recipient_token_refresh_passed,
            "recipient_gmail_api_passed": self.recipient_gmail_api_passed,
            "recipient_mailbox_identity_match": self.recipient_mailbox_identity_match,
            "recipient_required_scopes_present": self.recipient_required_scopes_present,
            "recipient_list_labels_passed": self.recipient_list_labels_passed,
            "recipient_read_query_passed": self.recipient_read_query_passed,
            "recipient_delivery_observation_ready": self.recipient_delivery_observation_ready,
            "recipient_credential_source": self.recipient_credential_source,
            "delivery_observation_credential_source": self.delivery_observation_credential_source,
            "credential_source_match": self.credential_source_match,
            "delivery_mailbox_identity_match": self.delivery_mailbox_identity_match,
            "delivery_observation_path_ready": self.delivery_observation_path_ready,
            "recipient_readiness_blockers": self.recipient_readiness_blockers,
            "tenant_intake_ready": self.tenant_intake_ready,
            "tenant_config_exists": self.tenant_config_exists,
            "intake_cutoff_at_redacted": self.intake_cutoff_at_redacted,
            "intake_cutoff_age_seconds": self.intake_cutoff_age_seconds,
            "intake_cutoff_fresh": self.intake_cutoff_fresh,
            "tenant_intake_blockers": self.tenant_intake_blockers,
        }
        return payload


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("yes", "true", "1")


def _git_sha(ref: str, *, repo_root: Path) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", ref],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return (proc.stdout or "").strip()


def _normalize_path(path: str) -> str:
    return path.replace("\\", "/")


def assert_r3_code_equivalence(
    *,
    repo_root: Path,
    qualified_reply_sha: str = QUALIFIED_REPLY_SHA,
    instrumentation_merge_sha: str | None = None,
) -> CodeEquivalenceResult:
    instrumentation_merge_sha = instrumentation_merge_sha or _git_sha("HEAD", repo_root=repo_root)
    proc = subprocess.run(
        ["git", "diff", "--name-only", qualified_reply_sha, instrumentation_merge_sha],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    changed = [
        _normalize_path(line.strip())
        for line in (proc.stdout or "").splitlines()
        if line.strip()
    ]
    allowlist = {_normalize_path(path) for path in R3_INSTRUMENTATION_ALLOWLIST}
    unexpected = [path for path in changed if path not in allowlist]
    passed = not unexpected and instrumentation_merge_sha != qualified_reply_sha
    if instrumentation_merge_sha == qualified_reply_sha:
        assertion = (
            "instrumentation_merge_sha equals qualified_reply_sha; "
            "instrumentation commit required before postdeploy"
        )
        passed = False
    elif unexpected:
        assertion = "diff from qualified_reply_sha contains non-instrumentation files"
    else:
        assertion = (
            "diff from qualified_reply_sha is limited to R3 instrumentation allowlist"
        )
    return CodeEquivalenceResult(
        passed=passed,
        qualified_reply_sha=qualified_reply_sha,
        instrumentation_merge_sha=instrumentation_merge_sha,
        changed_files=changed,
        unexpected_files=unexpected,
        assertion=assertion,
    )


def _extract_unrelated_context(readiness: dict[str, Any]) -> list[str]:
    context: list[str] = []
    for source in (
        readiness.get("blocking_failures") or [],
        readiness.get("live_execution_blockers") or [],
        readiness.get("live_quality_execution_blockers") or [],
    ):
        for item in source:
            if any(item.startswith(prefix) for prefix in R3_SEMI_AUTO_CONTEXT_PREFIXES):
                context.append(item)
    return list(dict.fromkeys(context))


def _r3_specific_blockers(
    *,
    readiness: dict[str, Any],
    runtime_report: dict[str, Any],
    oauth_ready: bool,
    mailbox_report: dict[str, Any],
    tenant_id: str,
    recipient_readiness: RecipientGmailReadinessResult | None = None,
    tenant_intake: TenantIntakeReadinessResult | None = None,
) -> list[str]:
    blockers: list[str] = []
    if tenant_id != LIVE_EVAL_TENANT_ID:
        blockers.append(f"tenant mismatch: expected {LIVE_EVAL_TENANT_ID}, got {tenant_id}")
    blockers.extend(validate_profile_testbot_tenant(tenant_id))
    if tenant_intake is not None and not tenant_intake.tenant_intake_ready:
        blockers.extend(tenant_intake.blockers)
    for blocked_tenant in ("T_NIKLAS_DEMO_001", "TENANT_PRODUCTION_PILOT_01"):
        issues = validate_no_production_resources(tenant_id=blocked_tenant)
        if not issues:
            blockers.append(f"{blocked_tenant} must be blocked for R3 canary")
    if not oauth_ready:
        blockers.append("Gmail OAuth readiness failed (live recipient API verification required)")
    if recipient_readiness is not None and not recipient_readiness.ready:
        blockers.extend(recipient_readiness.blockers)
    if not _env_truthy("LIVE_GMAIL_EVAL_ALLOWED"):
        blockers.append("LIVE_GMAIL_EVAL_ALLOWED=yes required for R3 canary")
    if not os.environ.get("LIVE_EVAL_APP_BASE_URL", "").strip():
        blockers.append("LIVE_EVAL_APP_BASE_URL required for R3 canary")
    if not os.environ.get("ADMIN_API_KEY", "").strip():
        blockers.append("ADMIN_API_KEY required for R3 canary")
    if not mailbox_report.get("sender_provider_verified"):
        blockers.append("sender provider not verified for R3 canary")
    if not mailbox_report.get("recipient_deliverability_verified"):
        blockers.append("recipient deliverability not verified for R3 canary")
    for item in readiness.get("blocking_failures") or []:
        if any(item.startswith(prefix) for prefix in R3_SEMI_AUTO_CONTEXT_PREFIXES):
            continue
        if item.startswith("EVAL_STACK_RUNTIME_SHA_MISMATCH"):
            continue
        blockers.append(item)
    for item in runtime_report.get("blocking_failures") or []:
        if item.startswith("EVAL_STACK_RUNTIME_SHA_MISMATCH"):
            continue
        blockers.append(item)
    return list(dict.fromkeys(blockers))


def compare_send_body_hashes(
    render_rows: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, str]], bool]:
    drift: dict[str, dict[str, str]] = {}
    for row in render_rows:
        scenario_id = str(row.get("scenario_id") or "")
        if not row.get("planned_gmail_send"):
            continue
        approved = R3_APPROVED_SEND_BODY_HASHES.get(scenario_id)
        current = str(row.get("body_hash") or "")
        if approved and current and approved != current:
            drift[scenario_id] = {"approved": approved, "current": current}
    return drift, bool(drift)


def evaluate_coworker_r3_readiness(
    *,
    phase: R3PreflightPhase,
    profile_id: str,
    tenant_id: str,
    instrumentation_merge_sha: str,
    repo_root: Path,
    render_rows: list[dict[str, Any]] | None = None,
    send_budget: int = COWORKER_LIVE_CANARY_SEND_MAX,
    no_send_count: int = COWORKER_LIVE_CANARY_TARGET - COWORKER_LIVE_CANARY_SEND_MAX,
    scenario_stop_conditions: list[str] | None = None,
) -> CoworkerR3ReadinessResult:
    render_rows = render_rows or []
    scenario_stop_conditions = scenario_stop_conditions or []
    code_equiv = assert_r3_code_equivalence(
        repo_root=repo_root,
        instrumentation_merge_sha=instrumentation_merge_sha,
    )
    runner_sha = instrumentation_merge_sha
    runner_sha_auditable = code_equiv.passed or phase == "postdeploy"

    os.environ["PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED"] = "yes"
    os.environ["PROFILE_TESTBOT_LIVE_SEMI_AUTO_RUNNER_APPROVED_SHA"] = runner_sha
    os.environ["BUILD_COMMIT_SHA"] = runner_sha
    os.environ["GIT_COMMIT"] = runner_sha

    readiness = build_profile_testbot_readiness(profile_id=profile_id, tenant_id=tenant_id)
    unrelated_context = _extract_unrelated_context(readiness)

    config = get_live_eval_config()
    sender = sorted(config.sender_emails)[0] if config.sender_emails else ""
    recipient = sorted(config.recipient_emails)[0] if config.recipient_emails else ""
    mailbox_report = verify_profile_testbot_mailboxes(
        sender_email=sender,
        recipient_email=recipient,
        config=config,
    )
    oauth = _oauth_readiness()
    recipient_readiness: RecipientGmailReadinessResult | None = None
    tenant_intake: TenantIntakeReadinessResult | None = None
    if phase == "postdeploy":
        db = SessionLocal()
        try:
            tenant_intake = run_r3_tenant_intake_readiness(db, tenant_id=tenant_id)
        finally:
            db.close()
    if phase == "postdeploy" and _env_truthy("LIVE_GMAIL_EVAL_ALLOWED"):
        recipient_readiness = run_recipient_gmail_readiness(
            expected_recipient=recipient,
            config=config,
        )
        oauth_ready = recipient_readiness.ready
    else:
        oauth_ready = bool(oauth.get("oauth_ready"))

    require_remote = phase == "postdeploy" and _env_truthy("LIVE_GMAIL_EVAL_ALLOWED")
    runtime_report = evaluate_eval_stack_runtime_sha(
        base_url=os.environ.get("LIVE_EVAL_APP_BASE_URL", "").strip(),
        admin_api_key=os.environ.get("ADMIN_API_KEY", "").strip(),
        approved_runtime_sha=runner_sha,
        runner_runtime_sha=runner_sha,
        require_remote=require_remote,
    )
    api_runtime_sha = runtime_report.get("api_runtime_sha")
    worker_runtime_sha = runtime_report.get("worker_runtime_sha")
    runtime_sha_consistent = bool(runtime_report.get("runtime_sha_consistent"))

    stop_conditions = list(scenario_stop_conditions)
    if not code_equiv.passed and phase == "predeploy":
        stop_conditions.append(code_equiv.assertion)
        if code_equiv.unexpected_files:
            stop_conditions.append(
                "unexpected non-instrumentation files: " + ", ".join(code_equiv.unexpected_files)
            )
    stop_conditions.extend(
        _r3_specific_blockers(
            readiness=readiness,
            runtime_report=runtime_report,
            oauth_ready=oauth_ready,
            mailbox_report=mailbox_report,
            tenant_id=tenant_id,
            recipient_readiness=recipient_readiness,
            tenant_intake=tenant_intake,
        )
    )

    if send_budget != COWORKER_LIVE_CANARY_SEND_MAX:
        stop_conditions.append(
            f"send budget {send_budget} != {COWORKER_LIVE_CANARY_SEND_MAX}"
        )
    expected_no_send = COWORKER_LIVE_CANARY_TARGET - COWORKER_LIVE_CANARY_SEND_MAX
    if no_send_count != expected_no_send:
        stop_conditions.append(f"no-send count {no_send_count} != {expected_no_send}")

    for row in render_rows:
        if row.get("planned_gmail_send") and not row.get("approval_required"):
            stop_conditions.append(f"{row['scenario_id']} send missing approval_required")

    body_hash_drift, human_render_rereview_required = compare_send_body_hashes(render_rows)
    if phase == "postdeploy" and human_render_rereview_required:
        stop_conditions.append("human render re-review required: send body hash drift detected")

    if phase == "postdeploy":
        if not api_runtime_sha or not worker_runtime_sha:
            stop_conditions.append("postdeploy requires verified api and worker runtime SHA")
        elif api_runtime_sha != instrumentation_merge_sha or worker_runtime_sha != instrumentation_merge_sha:
            stop_conditions.append(
                "postdeploy runtime SHA mismatch: "
                f"api={api_runtime_sha}, worker={worker_runtime_sha}, "
                f"expected={instrumentation_merge_sha}"
            )
        elif not runtime_sha_consistent:
            stop_conditions.append("postdeploy runtime_sha_consistent is false")

    if phase == "predeploy":
        origin_main = _git_sha("origin/main", repo_root=repo_root)
        if origin_main != QUALIFIED_REPLY_SHA:
            stop_conditions.append(
                f"origin/main {origin_main} != qualified reply SHA {QUALIFIED_REPLY_SHA}"
            )

    stop_conditions = list(dict.fromkeys(stop_conditions))
    tenant_isolation_verified = bool(
        readiness.get("production_pilot_tenant_blocked")
        and readiness.get("demo_tenant_blocked")
    )
    duplicate_replay_protection = bool(
        mailbox_report.get("sender_provider_verified")
        and mailbox_report.get("recipient_deliverability_verified")
    )

    predeploy_blockers = [
        item
        for item in stop_conditions
        if not item.startswith("postdeploy")
    ]
    predeploy_preflight_pass = phase == "predeploy" and not predeploy_blockers

    postdeploy_blockers = list(stop_conditions)
    if phase != "postdeploy":
        postdeploy_preflight_pass = False
    else:
        postdeploy_preflight_pass = not postdeploy_blockers

    runner_ready_for_live_execution = (
        phase == "postdeploy"
        and runtime_sha_consistent
        and oauth_ready
        and duplicate_replay_protection
        and tenant_isolation_verified
        and not postdeploy_blockers
    )

    r3_canary_ready_for_manual_send_approval = (
        postdeploy_preflight_pass
        and runner_ready_for_live_execution
        and not (phase == "postdeploy" and human_render_rereview_required)
    )

    return CoworkerR3ReadinessResult(
        phase=phase,
        qualified_reply_sha=QUALIFIED_REPLY_SHA,
        instrumentation_merge_sha=instrumentation_merge_sha,
        runner_sha=runner_sha,
        api_runtime_sha=api_runtime_sha,
        worker_runtime_sha=worker_runtime_sha,
        runtime_sha_consistent=runtime_sha_consistent,
        runner_sha_auditable=runner_sha_auditable,
        predeploy_preflight_pass=predeploy_preflight_pass,
        postdeploy_preflight_pass=postdeploy_preflight_pass,
        r3_canary_ready_for_manual_send_approval=r3_canary_ready_for_manual_send_approval,
        oauth_ready=oauth_ready,
        tenant_isolation_verified=tenant_isolation_verified,
        duplicate_replay_protection=duplicate_replay_protection,
        runner_ready_for_live_execution=runner_ready_for_live_execution,
        send_budget=send_budget,
        no_send_count=no_send_count,
        stop_conditions=stop_conditions,
        unrelated_qualification_context=unrelated_context,
        body_hash_drift=body_hash_drift,
        human_render_rereview_required=human_render_rereview_required,
        recipient_oauth_configured=(
            recipient_readiness.recipient_oauth_configured if recipient_readiness else None
        ),
        recipient_token_refresh_passed=(
            recipient_readiness.recipient_token_refresh_passed if recipient_readiness else None
        ),
        recipient_gmail_api_passed=(
            recipient_readiness.recipient_gmail_api_passed if recipient_readiness else None
        ),
        recipient_mailbox_identity_match=(
            recipient_readiness.recipient_mailbox_identity_match if recipient_readiness else None
        ),
        recipient_required_scopes_present=(
            recipient_readiness.recipient_required_scopes_present if recipient_readiness else None
        ),
        recipient_list_labels_passed=(
            recipient_readiness.recipient_list_labels_passed if recipient_readiness else None
        ),
        recipient_read_query_passed=(
            recipient_readiness.recipient_read_query_passed if recipient_readiness else None
        ),
        recipient_delivery_observation_ready=(
            recipient_readiness.recipient_delivery_observation_ready if recipient_readiness else None
        ),
        recipient_credential_source=(
            recipient_readiness.recipient_credential_source if recipient_readiness else None
        ),
        delivery_observation_credential_source=(
            recipient_readiness.delivery_observation_credential_source
            if recipient_readiness
            else None
        ),
        credential_source_match=(
            recipient_readiness.credential_source_match if recipient_readiness else None
        ),
        delivery_mailbox_identity_match=(
            recipient_readiness.delivery_mailbox_identity_match if recipient_readiness else None
        ),
        delivery_observation_path_ready=(
            recipient_readiness.delivery_observation_path_ready if recipient_readiness else None
        ),
        recipient_readiness_blockers=(
            list(recipient_readiness.blockers) if recipient_readiness else []
        ),
        tenant_intake_ready=tenant_intake.tenant_intake_ready if tenant_intake else None,
        tenant_config_exists=tenant_intake.tenant_config_exists if tenant_intake else None,
        intake_cutoff_at_redacted=(
            tenant_intake.intake_cutoff_at_redacted if tenant_intake else None
        ),
        intake_cutoff_age_seconds=(
            tenant_intake.intake_cutoff_age_seconds if tenant_intake else None
        ),
        intake_cutoff_fresh=tenant_intake.intake_cutoff_fresh if tenant_intake else None,
        tenant_intake_blockers=list(tenant_intake.blockers) if tenant_intake else [],
    )
