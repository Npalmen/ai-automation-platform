"""Readiness gates for profile-driven testbot."""

from __future__ import annotations

import os
from typing import Any

from app.core.canonical_commit import resolve_canonical_commit
from app.evaluation.live.campaign.gates import validate_no_production_resources
from app.evaluation.live.config import get_live_eval_config
from app.evaluation.profile_testbot.constants import (
    BLOCKED_TENANTS,
    LIVE_EVAL_TENANT_ID,
    OPERATOR_STOP_AUTOMATIC,
    OPERATOR_STOP_SEMI_AUTO,
    QUALIFICATION_AUTOMATIC,
    QUALIFICATION_PASS,
    QUALIFICATION_SEMI_AUTO,
    SEMI_AUTO_HOLD_EDGE_MIN,
    SEMI_AUTO_SCENARIO_TARGET,
    SEMI_AUTO_SEND_AFTER_APPROVAL_MIN,
)
from app.evaluation.profile_testbot.generator.profile_generator import (
    generate_hermetic_campaign,
    generate_semi_auto_campaign,
)
from app.evaluation.profile_testbot.profile_contract import load_customer_profile
from app.evaluation.regression.qualification_registry import qualification_index

_BLOCKED_MAILBOXES = frozenset(
    {
        "niklas.palm@sol-f.se",
    }
)
_REAL_CUSTOMER_DOMAIN_SUFFIXES = (
    "@sol-f.se",
    "@gmail.com",
    "@krowolf.se",
)
_EVAL_TEST_DOMAIN_SUFFIX = "@eval.test"


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("yes", "true", "1")


def _runtime_sha() -> str:
    return resolve_canonical_commit() or "unknown"


def validate_profile_testbot_tenant(tenant_id: str) -> list[str]:
    issues: list[str] = []
    if tenant_id != LIVE_EVAL_TENANT_ID:
        issues.append(f"tenant must be {LIVE_EVAL_TENANT_ID}")
    if tenant_id in BLOCKED_TENANTS:
        issues.append(f"tenant {tenant_id!r} is blocked for profile testbot")
    return issues


def _validate_allowlists(
  config,
) -> tuple[list[str], dict[str, list[str]]]:
    issues: list[str] = []
    senders = sorted(config.sender_emails)
    recipients = sorted(config.recipient_emails)
    if not senders:
        issues.append("LIVE_EVAL_SENDER_EMAILS must define exactly one sender allowlist entry")
    if not recipients:
        issues.append("LIVE_EVAL_RECIPIENT_EMAILS must define exactly one recipient allowlist entry")
    for email in senders + recipients:
        lowered = email.lower()
        if lowered in _BLOCKED_MAILBOXES:
            issues.append(f"P1/production mailbox blocked in allowlist: {email}")
        if not lowered.endswith(_EVAL_TEST_DOMAIN_SUFFIX):
            issues.append(f"allowlist address must use eval.test domain: {email}")
        for suffix in _REAL_CUSTOMER_DOMAIN_SUFFIXES:
            if lowered.endswith(suffix):
                issues.append(f"real customer/production domain blocked: {email}")
    if len(senders) != 1:
        issues.append(f"sender allowlist must contain exactly one address, got {len(senders)}")
    if len(recipients) != 1:
        issues.append(f"recipient allowlist must contain exactly one address, got {len(recipients)}")
    return issues, {"sender_allowlist": senders, "recipient_allowlist": recipients}


def _validate_single_active_consumer(*, tenant_id: str, senders: list[str], recipients: list[str]) -> list[str]:
    issues: list[str] = []
    for blocked in BLOCKED_TENANTS:
        issues.extend(validate_no_production_resources(tenant_id=blocked))
    if tenant_id != LIVE_EVAL_TENANT_ID:
        issues.append("single-active-consumer requires TENANT_LIVE_EVAL only")
    combined = {addr.lower() for addr in senders + recipients}
    if len(combined) < 2:
        issues.append("single-active-consumer requires distinct sender and recipient mailboxes")
    return issues


def _oauth_readiness() -> dict[str, Any]:
    required = (
        "LIVE_EVAL_SENDER_GMAIL_REFRESH_TOKEN",
        "LIVE_EVAL_RECIPIENT_GMAIL_REFRESH_TOKEN",
    )
    optional_client = (
        "LIVE_EVAL_SENDER_GMAIL_CLIENT_ID",
        "LIVE_EVAL_RECIPIENT_GMAIL_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_ID",
    )
    present = {name: bool(os.environ.get(name, "").strip()) for name in required}
    client_present = any(os.environ.get(name, "").strip() for name in optional_client)
    ready = all(present.values()) and client_present
    return {
        "oauth_ready": ready,
        "oauth_token_exposed": False,
        "credential_env_present": present,
        "oauth_client_configured": client_present,
    }


def _semi_auto_manifest(profile_id: str, *, seed: int = 0) -> dict[str, Any]:
    profile = load_customer_profile(profile_id)
    scenarios = generate_semi_auto_campaign(profile, seed=seed)
    send_after = [s for s in scenarios if s.expected_send_behavior == "send_after_approval"]
    hold_edge = [
        s
        for s in scenarios
        if s.expected_send_behavior in {"hold", "reject", "no_reply", "observe_only", "draft_for_approval"}
    ]
    return {
        "scenario_manifest_count": len(scenarios),
        "send_after_approval_count": len(send_after),
        "hold_reject_no_reply_count": len(hold_edge),
        "scenario_ids": [s.scenario_id for s in scenarios],
        "send_budget_total": sum(
            1 for s in scenarios if s.expected_send_behavior == "send_after_approval"
        ),
        "max_send_per_scenario": 1,
    }


def build_profile_testbot_readiness(
    *,
    profile_id: str = "pilot-service-company-v1",
    tenant_id: str = LIVE_EVAL_TENANT_ID,
    database_url: str = "",
    app_base_url: str = "",
    seed: int = 0,
) -> dict[str, Any]:
    issues: list[str] = []
    blockers: list[str] = []
    profile = load_customer_profile(profile_id)
    hermetic = generate_hermetic_campaign(profile, seed=seed)
    semi_auto = _semi_auto_manifest(profile_id, seed=seed)
    config = get_live_eval_config()

    issues.extend(validate_profile_testbot_tenant(tenant_id))
    issues.extend(
        validate_no_production_resources(
            database_url=database_url or os.environ.get("DATABASE_URL", ""),
            app_base_url=app_base_url,
            tenant_id=tenant_id,
        )
    )
    for blocked_tenant in ("T_NIKLAS_DEMO_001", "TENANT_PRODUCTION_PILOT_01"):
        demo_issues = validate_no_production_resources(tenant_id=blocked_tenant)
        if not demo_issues:
            issues.append(f"{blocked_tenant} must be blocked for profile testbot campaigns")

    allowlist_issues, allowlists = _validate_allowlists(config)
    issues.extend(allowlist_issues)
    issues.extend(
        _validate_single_active_consumer(
            tenant_id=tenant_id,
            senders=allowlists.get("sender_allowlist", []),
            recipients=allowlists.get("recipient_allowlist", []),
        )
    )

    if len(hermetic) < 120:
        issues.append(f"hermetic generator produced {len(hermetic)} scenarios, expected >= 120")
    if not config.enabled:
        issues.append("LIVE_EVAL_ALLOWED=yes and ENV=test required")
    if not _env_truthy("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED"):
        issues.append("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED=yes required for campaign readiness")
    if semi_auto["scenario_manifest_count"] != SEMI_AUTO_SCENARIO_TARGET:
        issues.append(
            f"semi-auto manifest count {semi_auto['scenario_manifest_count']} != {SEMI_AUTO_SCENARIO_TARGET}"
        )
    if semi_auto["send_after_approval_count"] < SEMI_AUTO_SEND_AFTER_APPROVAL_MIN:
        issues.append(
            f"send_after_approval count {semi_auto['send_after_approval_count']} < {SEMI_AUTO_SEND_AFTER_APPROVAL_MIN}"
        )
    if semi_auto["hold_reject_no_reply_count"] < SEMI_AUTO_HOLD_EDGE_MIN:
        issues.append(
            f"hold/reject/no_reply count {semi_auto['hold_reject_no_reply_count']} < {SEMI_AUTO_HOLD_EDGE_MIN}"
        )
    if config.max_gmail_replies_per_run < semi_auto["send_budget_total"]:
        issues.append(
            f"LIVE_EVAL_MAX_GMAIL_REPLIES={config.max_gmail_replies_per_run} "
            f"< semi-auto send budget {semi_auto['send_budget_total']}"
        )

    oauth = _oauth_readiness()
    if not oauth["oauth_ready"]:
        issues.append("Gmail OAuth env not ready (refresh tokens + client id required)")

    qualifications = qualification_index()
    live_quals = {
        QUALIFICATION_SEMI_AUTO: qualifications.get(QUALIFICATION_SEMI_AUTO, {}).get("status"),
        QUALIFICATION_AUTOMATIC: qualifications.get(QUALIFICATION_AUTOMATIC, {}).get("status"),
        QUALIFICATION_PASS: qualifications.get(QUALIFICATION_PASS, {}).get("status"),
    }
    if live_quals[QUALIFICATION_SEMI_AUTO] != "PENDING":
        issues.append(f"{QUALIFICATION_SEMI_AUTO} must remain PENDING until live semi-auto PASS")

    cleanup_ready = os.path.isdir(config.storage_root) or _env_truthy("LIVE_EVAL_PURGE_ALLOWED")
    if not cleanup_ready:
        issues.append("cleanup readiness: live_eval storage root missing and LIVE_EVAL_PURGE_ALLOWED not set")

    blockers = list(issues)
    return {
        "runtime_sha": _runtime_sha(),
        "profile_id": profile.profile_id,
        "profile_snapshot_hash": profile.profile_snapshot_hash,
        "tenant_id": tenant_id,
        "eval_tenant": LIVE_EVAL_TENANT_ID,
        "production_pilot_tenant_blocked": "TENANT_PRODUCTION_PILOT_01"
        in BLOCKED_TENANTS,
        "demo_tenant_blocked": "T_NIKLAS_DEMO_001" in BLOCKED_TENANTS,
        "sender_allowlist": allowlists.get("sender_allowlist", []),
        "recipient_allowlist": allowlists.get("recipient_allowlist", []),
        "real_customer_mailboxes_blocked": True,
        "p1_mailboxes_blocked": True,
        "single_active_consumer_verified": not any(
            "single-active-consumer" in issue for issue in issues
        ),
        "oauth": oauth,
        "gmail_send_budget_semi_auto": semi_auto["send_budget_total"],
        "max_send_per_scenario": 1,
        "external_writes": {
            "sheets": 0,
            "monday": 0,
            "visma": 0,
            "automatic_verify": 0,
            "automatic_link": 0,
            "automatic_merge": 0,
        },
        "cleanup_ready": cleanup_ready,
        "hermetic_scenario_count": len(hermetic),
        "semi_auto_manifest": semi_auto,
        "oracle_authority": {
            "hard_safety": "QUALIFICATION_AUTHORITY",
            "decision": "QUALIFICATION_AUTHORITY",
            "reply_contract": "QUALIFICATION_AUTHORITY",
            "semantic_judge": "STUB_NOT_QUALIFICATION_AUTHORITY",
        },
        "live_qualifications": live_quals,
        "issues": issues,
        "blockers": blockers,
        "ready_for_live_semi_auto": not blockers,
        "operator_stop": None if not blockers else OPERATOR_STOP_SEMI_AUTO,
    }


def require_live_semi_auto_approval() -> str | None:
    if _env_truthy("PROFILE_TESTBOT_LIVE_SEMI_AUTO_APPROVED"):
        return None
    return OPERATOR_STOP_SEMI_AUTO


def require_automatic_canary_approval(*, qualifications: list[str] | None = None) -> str | None:
    registered = set(qualifications or qualification_index().keys())
    if QUALIFICATION_SEMI_AUTO not in registered and not _env_truthy("PROFILE_TESTBOT_SEMI_AUTO_QUALIFIED"):
        return f"{QUALIFICATION_SEMI_AUTO} required before automatic canary"
    if _env_truthy("PROFILE_TESTBOT_AUTOMATIC_CANARY_APPROVED"):
        return None
    return OPERATOR_STOP_AUTOMATIC
