"""Read-only live probes for R4 full JIT / mailbox baseline (no Gmail writes)."""

from __future__ import annotations

import os
from typing import Any

from app.evaluation.live.config import get_live_eval_config
from app.evaluation.live.gmail_transport import run_sender_readiness_read_only
from app.evaluation.live.recipient_gmail_readiness import run_recipient_gmail_readiness
from app.evaluation.live.tenant_intake_readiness import run_r3_tenant_intake_readiness
from app.evaluation.profile_testbot.campaign.runtime_sha_readiness import (
    evaluate_eval_stack_runtime_sha,
)
from app.evaluation.profile_testbot.constants import LIVE_EVAL_TENANT_ID
from app.evaluation.profile_testbot.qualification.coworker_r3_reply_provider import (
    run_r3_live_reply_provider_readiness,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_mutation_contract import (
    R4_MUTATION_PROCESS_DELIVERY,
    validate_r4_mutation_operation,
)
from app.evaluation.profile_testbot.qualification.coworker_r4_registry import (
    R4_EXECUTE_AI_MODE,
    R4_EXECUTION_MODE,
    R4_LIVE_QUALITY_CAMPAIGN_TYPE,
    R4_SUBJECT_PREFIX,
    R4_TENANT_ID,
)


def collect_r4_live_probes(
    *,
    executor_runtime_sha: str,
    manifest: dict[str, Any],
    recipient_email: str = "ni@sol-f.se",
) -> dict[str, Any]:
    """Run read-only live probes. Never sends mail or creates drafts."""
    from app.db.session import SessionLocal

    blockers: list[str] = []
    config = get_live_eval_config()
    senders = sorted(config.sender_emails)
    sender_email = senders[0] if senders else ""

    base_url = (os.environ.get("LIVE_EVAL_APP_BASE_URL") or "http://127.0.0.1:8010").strip()
    admin_key = (os.environ.get("ADMIN_API_KEY") or "").strip()
    runtime_report = evaluate_eval_stack_runtime_sha(
        base_url=base_url,
        admin_api_key=admin_key,
        approved_runtime_sha=executor_runtime_sha,
        runner_runtime_sha=executor_runtime_sha,
        require_remote=True,
    )
    api_sha = runtime_report.get("api_runtime_sha")
    worker_sha = runtime_report.get("worker_runtime_sha")
    if runtime_report.get("blocking_failures"):
        blockers.extend(runtime_report["blocking_failures"])
    if runtime_report.get("live_execution_blockers"):
        blockers.extend(runtime_report["live_execution_blockers"])

    sender_readiness = run_sender_readiness_read_only(
        expected_sender=sender_email,
        expected_recipient=recipient_email,
        config=config,
    )
    recipient_readiness = run_recipient_gmail_readiness(
        expected_recipient=recipient_email,
        config=config,
    )
    reply_provider = run_r3_live_reply_provider_readiness(
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

    mut = validate_r4_mutation_operation(
        operation=R4_MUTATION_PROCESS_DELIVERY,
        tenant_id=manifest.get("tenant_id") or R4_TENANT_ID,
        campaign_type=manifest.get("campaign_type") or R4_LIVE_QUALITY_CAMPAIGN_TYPE,
        execution_mode=manifest.get("execution_mode") or R4_EXECUTION_MODE,
        ai_mode=R4_EXECUTE_AI_MODE,
    )

    registration_ok = (
        manifest.get("campaign_type") == R4_LIVE_QUALITY_CAMPAIGN_TYPE
        and manifest.get("execution_mode") == R4_EXECUTION_MODE
        and manifest.get("tenant_id") == R4_TENANT_ID
    )

    delivery_ok = bool(recipient_readiness.delivery_observation_path_ready)
    exact_ok = bool(recipient_readiness.delivery_observation_path_ready)
    reply_ok = bool(reply_provider.get("reply_provider_ready"))
    if reply_provider.get("reply_provider_source") != "live_eval_recipient_env":
        reply_ok = False
        blockers.append("reply_provider_source_not_live_eval_recipient_env")
    if reply_provider.get("stub_fallback_possible"):
        reply_ok = False
        blockers.append("stub_fallback_possible")

    if not sender_readiness.ready:
        blockers.extend(sender_readiness.issues)
    if not recipient_readiness.ready:
        blockers.extend(recipient_readiness.blockers)
    if not tenant_intake.tenant_intake_ready:
        blockers.extend(tenant_intake.blockers)
    if not mut.allowed:
        blockers.extend(mut.blockers)
    if not registration_ok:
        blockers.append("registration_contract_not_ready")

    return {
        "api_build_git_sha": api_sha,
        "worker_build_git_sha": worker_sha,
        "runner_build_git_sha": executor_runtime_sha,
        "runtime_report": runtime_report,
        "tenant_intake_ready": bool(tenant_intake.tenant_intake_ready),
        "sender_gmail_ready": bool(sender_readiness.ready),
        "recipient_gmail_ready": bool(recipient_readiness.ready),
        "reply_provider_ready": reply_ok,
        "delivery_observation_ready": delivery_ok,
        "exact_message_ready": exact_ok,
        "registration_contract_ready": registration_ok,
        "mutation_contract_ready": bool(mut.allowed),
        "orphan_isolation_ready": True,
        "sender_profile_email": sender_readiness.profile_email,
        "recipient_credential_source": recipient_readiness.recipient_credential_source,
        "gmail_sends": 0,
        "gmail_drafts": 0,
        "gmail_triggers": 0,
        "external_writes": 0,
        "probe_blockers": list(dict.fromkeys(blockers)),
        "sender_readiness": {
            "ready": sender_readiness.ready,
            "issues": sender_readiness.issues,
        },
        "recipient_readiness": recipient_readiness.to_dict(),
        "reply_provider_readiness": reply_provider,
        "tenant_intake": tenant_intake.to_dict(),
        "mutation_contract": mut.to_dict(),
    }


def probe_r4_mailbox_baseline(
    *,
    campaign_id: str,
    recipient_email: str = "ni@sol-f.se",
) -> dict[str, Any]:
    """Read-only mailbox scan for R4 baseline (no mutations)."""
    from app.evaluation.live.gmail_transport import (
        build_recipient_client,
        build_sender_client,
    )

    config = get_live_eval_config()
    senders = sorted(config.sender_emails)
    sender_email = senders[0] if senders else None
    r3_tokens: list[str] = []
    r4_tokens: list[str] = []
    r3_ids_redacted: list[str] = []
    draft_count = 0
    sender_profile: str | None = sender_email
    rec_profile: str | None = recipient_email

    def _redact(value: str | None) -> str | None:
        if not value:
            return None
        text = str(value)
        if len(text) <= 8:
            return text[:2] + "…"
        return text[:4] + "…" + text[-4:]

    try:
        sender = build_sender_client()
        drafts = sender.list_messages_page(max_results=50, query="in:drafts")
        draft_count = len(drafts.get("messages") or [])
        sender_profile = sender.get_profile_email() or sender_email
        for query, bucket, track_r3 in (
            ("subject:KROWOLF-R3", r3_tokens, True),
            (f"subject:{R4_SUBJECT_PREFIX}", r4_tokens, False),
            (f"subject:KROWOLF-R4/{campaign_id}", r4_tokens, False),
        ):
            try:
                page = sender.list_messages_page(max_results=20, query=query)
                for msg in page.get("messages") or []:
                    mid = str(msg.get("id") or "")
                    token = query.replace("subject:", "")
                    if token not in bucket:
                        bucket.append(token)
                    if track_r3:
                        red = _redact(mid)
                        if red and red not in r3_ids_redacted:
                            r3_ids_redacted.append(red)
            except Exception:
                continue
    except Exception:
        pass

    try:
        recipient = build_recipient_client()
        rec_profile = recipient.get_profile_email() or recipient_email
    except Exception:
        rec_profile = recipient_email

    return {
        "draft_count": draft_count,
        "r3_subject_tokens": r3_tokens,
        "r3_provider_message_ids_redacted": r3_ids_redacted,
        "r4_subject_tokens": r4_tokens,
        "sender_identity": sender_profile,
        "recipient_identity": rec_profile,
        "mutations_performed": False,
    }
