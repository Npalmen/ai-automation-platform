"""Readiness gates for profile-driven testbot."""

from __future__ import annotations

import os
from typing import Any

from app.core.canonical_commit import resolve_canonical_commit
from app.evaluation.live.campaign.gates import validate_no_production_resources
from app.evaluation.live.config import get_live_eval_config
from app.evaluation.profile_testbot.campaign.mailbox_readiness import (
    mailbox_hash,
    verify_profile_testbot_mailboxes,
)
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
    "@krowolf.se",
)


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


def _validate_allowlists(config) -> tuple[list[str], dict[str, str | None]]:
    blocking: list[str] = []
    senders = sorted(config.sender_emails)
    recipients = sorted(config.recipient_emails)
    if not senders:
        blocking.append("LIVE_EVAL_SENDER_EMAILS must define exactly one sender allowlist entry")
    if not recipients:
        blocking.append("LIVE_EVAL_RECIPIENT_EMAILS must define exactly one recipient allowlist entry")
    if len(senders) != 1:
        blocking.append(f"sender allowlist must contain exactly one address, got {len(senders)}")
    if len(recipients) != 1:
        blocking.append(
            f"recipient allowlist must contain exactly one address, got {len(recipients)}"
        )

    sender = senders[0] if senders else ""
    recipient = recipients[0] if recipients else ""
    for email, role in ((sender, "sender"), (recipient, "recipient")):
        lowered = email.lower()
        if lowered in _BLOCKED_MAILBOXES:
            blocking.append(f"P1/production mailbox blocked in allowlist ({role})")
        for suffix in _REAL_CUSTOMER_DOMAIN_SUFFIXES:
            if lowered.endswith(suffix):
                blocking.append(f"real customer/production domain blocked ({role})")

    return blocking, {
        "sender_mailbox_hash": mailbox_hash(sender) if sender else None,
        "recipient_mailbox_hash": mailbox_hash(recipient) if recipient else None,
        "sender_email": sender,
        "recipient_email": recipient,
    }


def _parse_competing_consumer_tenants() -> list[str]:
    raw = os.environ.get("LIVE_EVAL_MAILBOX_ACTIVE_CONSUMER_TENANTS", "").strip()
    if not raw:
        return []
    tenants = [item.strip() for item in raw.split(",") if item.strip()]
    return sorted(set(tenants))


def _validate_single_active_consumer(
    *,
    tenant_id: str,
    config,
    senders: list[str],
    recipients: list[str],
) -> tuple[list[str], bool]:
    blocking: list[str] = []
    if tenant_id != LIVE_EVAL_TENANT_ID:
        blocking.append("single-active-consumer requires TENANT_LIVE_EVAL only")
    if config.tenant_ids != {LIVE_EVAL_TENANT_ID}:
        blocking.append(
            f"LIVE_EVAL_TENANT_IDS must contain only {LIVE_EVAL_TENANT_ID}, "
            f"got {sorted(config.tenant_ids)}"
        )

    competing = _parse_competing_consumer_tenants()
    active_consumers = {tenant_id, *competing}
    if len(active_consumers) > 1:
        blocking.append(
            "multiple active mailbox consumers: "
            + ", ".join(sorted(active_consumers))
        )

    combined = {addr.lower() for addr in senders + recipients if addr}
    if len(combined) < 2:
        blocking.append("single-active-consumer requires distinct sender and recipient mailboxes")

    for blocked_mailbox in _BLOCKED_MAILBOXES:
        for email in combined:
            if email == blocked_mailbox:
                blocking.append("P1 mailbox must not be used for eval testbot mailboxes")

    return blocking, not blocking


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


def _build_safety_assertions(*, blocked_tenant_checks: dict[str, bool]) -> list[str]:
    assertions: list[str] = []
    if "TENANT_PRODUCTION_PILOT_01" in BLOCKED_TENANTS:
        assertions.append("production_pilot_tenant_blocked")
    if "T_NIKLAS_DEMO_001" in BLOCKED_TENANTS:
        assertions.append("demo_tenant_blocked")
    for tenant_id, blocked in blocked_tenant_checks.items():
        if blocked:
            assertions.append(f"{tenant_id}_blocked")
    assertions.append("p1_mailbox_blocked")
    assertions.append("forbidden_integrations_blocked:sheets,monday,visma")
    return assertions


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
    blocking_failures: list[str] = []
    warnings: list[str] = []
    profile = load_customer_profile(profile_id)
    hermetic = generate_hermetic_campaign(profile, seed=seed)
    semi_auto = _semi_auto_manifest(profile_id, seed=seed)
    config = get_live_eval_config()

    blocking_failures.extend(validate_profile_testbot_tenant(tenant_id))
    blocking_failures.extend(
        validate_no_production_resources(
            database_url=database_url or os.environ.get("DATABASE_URL", ""),
            app_base_url=app_base_url,
            tenant_id=tenant_id,
        )
    )

    blocked_tenant_checks: dict[str, bool] = {}
    for blocked_tenant in ("T_NIKLAS_DEMO_001", "TENANT_PRODUCTION_PILOT_01"):
        tenant_issues = validate_no_production_resources(tenant_id=blocked_tenant)
        blocked_tenant_checks[blocked_tenant] = bool(tenant_issues)
        if not tenant_issues:
            blocking_failures.append(
                f"{blocked_tenant} must be blocked for profile testbot campaigns"
            )

    allowlist_issues, allowlists = _validate_allowlists(config)
    blocking_failures.extend(allowlist_issues)

    consumer_issues, single_active_consumer = _validate_single_active_consumer(
        tenant_id=tenant_id,
        config=config,
        senders=[allowlists.get("sender_email") or ""],
        recipients=[allowlists.get("recipient_email") or ""],
    )
    blocking_failures.extend(consumer_issues)

    mailbox_report = verify_profile_testbot_mailboxes(
        sender_email=allowlists.get("sender_email") or "",
        recipient_email=allowlists.get("recipient_email") or "",
        config=config,
    )
    blocking_failures.extend(mailbox_report.get("blocking_failures", []))

    if len(hermetic) < 120:
        blocking_failures.append(
            f"hermetic generator produced {len(hermetic)} scenarios, expected >= 120"
        )
    if not config.enabled:
        blocking_failures.append("LIVE_EVAL_ALLOWED=yes and ENV=test required")
    if not _env_truthy("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED"):
        blocking_failures.append(
            "FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED=yes required for campaign readiness"
        )
    if semi_auto["scenario_manifest_count"] != SEMI_AUTO_SCENARIO_TARGET:
        blocking_failures.append(
            f"semi-auto manifest count {semi_auto['scenario_manifest_count']} != {SEMI_AUTO_SCENARIO_TARGET}"
        )
    if semi_auto["send_after_approval_count"] < SEMI_AUTO_SEND_AFTER_APPROVAL_MIN:
        blocking_failures.append(
            f"send_after_approval count {semi_auto['send_after_approval_count']} < {SEMI_AUTO_SEND_AFTER_APPROVAL_MIN}"
        )
    if semi_auto["hold_reject_no_reply_count"] < SEMI_AUTO_HOLD_EDGE_MIN:
        blocking_failures.append(
            f"hold/reject/no_reply count {semi_auto['hold_reject_no_reply_count']} < {SEMI_AUTO_HOLD_EDGE_MIN}"
        )
    if config.max_gmail_replies_per_run < semi_auto["send_budget_total"]:
        blocking_failures.append(
            f"LIVE_EVAL_MAX_GMAIL_REPLIES={config.max_gmail_replies_per_run} "
            f"< semi-auto send budget {semi_auto['send_budget_total']}"
        )

    oauth = _oauth_readiness()
    if not oauth["oauth_ready"]:
        blocking_failures.append(
            "Gmail OAuth env not ready (refresh tokens + client id required)"
        )

    qualifications = qualification_index()
    live_quals = {
        QUALIFICATION_SEMI_AUTO: qualifications.get(QUALIFICATION_SEMI_AUTO, {}).get("status"),
        QUALIFICATION_AUTOMATIC: qualifications.get(QUALIFICATION_AUTOMATIC, {}).get("status"),
        QUALIFICATION_PASS: qualifications.get(QUALIFICATION_PASS, {}).get("status"),
    }
    if live_quals[QUALIFICATION_SEMI_AUTO] != "PENDING":
        blocking_failures.append(
            f"{QUALIFICATION_SEMI_AUTO} must remain PENDING until live semi-auto PASS"
        )

    cleanup_ready = os.path.isdir(config.storage_root) or _env_truthy("LIVE_EVAL_PURGE_ALLOWED")
    if not cleanup_ready:
        blocking_failures.append(
            "cleanup readiness: live_eval storage root missing and LIVE_EVAL_PURGE_ALLOWED not set"
        )

    safety_assertions = _build_safety_assertions(blocked_tenant_checks=blocked_tenant_checks)
    ready = not blocking_failures
    return {
        "runtime_sha": _runtime_sha(),
        "profile_id": profile.profile_id,
        "profile_snapshot_hash": profile.profile_snapshot_hash,
        "tenant_id": tenant_id,
        "eval_tenant": LIVE_EVAL_TENANT_ID,
        "production_pilot_tenant_blocked": blocked_tenant_checks.get(
            "TENANT_PRODUCTION_PILOT_01", False
        ),
        "demo_tenant_blocked": blocked_tenant_checks.get("T_NIKLAS_DEMO_001", False),
        "sender_mailbox_hash": mailbox_report.get("sender_mailbox_hash"),
        "recipient_mailbox_hash": mailbox_report.get("recipient_mailbox_hash"),
        "sender_provider_verified": mailbox_report.get("sender_provider_verified"),
        "recipient_deliverability_verified": mailbox_report.get(
            "recipient_deliverability_verified"
        ),
        "single_active_consumer": single_active_consumer,
        "real_customer_mailboxes_blocked": True,
        "p1_mailboxes_blocked": True,
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
        "blocking_failures": blocking_failures,
        "safety_assertions": safety_assertions,
        "warnings": warnings,
        "issues": blocking_failures,
        "blockers": blocking_failures,
        "ready_for_live_semi_auto": ready,
        "operator_stop": None if ready else OPERATOR_STOP_SEMI_AUTO,
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
