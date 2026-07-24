"""Fail-closed safety gates for live evaluation."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from app.evaluation.live.config import LiveEvalConfig, get_live_eval_config
from app.evaluation.live.constants import (
    ALLOWED_AI_MODES,
    ALLOWED_TRANSPORT_MODES,
    LIVE_EVAL_MUTATION_CLEANUP_ARCHIVE,
    RUN_STATUS_ABORTED,
    RUN_STATUS_ACTIVE,
    RUN_STATUS_REGISTERED,
    TERMINAL_RUN_STATUSES,
)
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.reporting import _FIXTURE_WORKFLOW_SHA_MARKERS
from app.repositories.postgres.live_eval_models import LiveEvalRunRow


def require_live_eval_enabled(config: LiveEvalConfig | None = None) -> LiveEvalConfig:
    config = config or get_live_eval_config()
    if not config.enabled:
        raise LiveEvalSafetyError("LIVE_EVAL_ALLOWED is not enabled for ENV=test")
    return config


def require_tenant_allowed(tenant_id: str, config: LiveEvalConfig | None = None) -> LiveEvalConfig:
    config = require_live_eval_enabled(config)
    if tenant_id not in config.tenant_ids:
        raise LiveEvalSafetyError(f"tenant_id {tenant_id!r} is not in LIVE_EVAL_TENANT_IDS")
    return config


def validate_registration_request(
    *,
    tenant_id: str,
    transport_mode: str,
    ai_mode: str,
    scenario_id: str,
    expected_sender: str | None = None,
    expected_recipient: str | None = None,
    llm_provider: str | None = None,
    llm_requested_model: str | None = None,
    config: LiveEvalConfig | None = None,
) -> LiveEvalConfig:
    config = require_tenant_allowed(tenant_id, config)
    if transport_mode not in ALLOWED_TRANSPORT_MODES:
        raise LiveEvalSafetyError(f"transport_mode {transport_mode!r} is not allowed")
    if ai_mode not in ALLOWED_AI_MODES:
        raise LiveEvalSafetyError(f"ai_mode {ai_mode!r} is not allowed")
    if transport_mode == "live_gmail" and ai_mode == "live_llm":
        raise LiveEvalSafetyError("live_gmail + live_llm is not allowed")
    if transport_mode == "fixture_input" and ai_mode == "fixture_ai":
        raise LiveEvalSafetyError("fixture_input + fixture_ai is not allowed")
    if ai_mode == "live_llm" and not config.llm_enabled:
        raise LiveEvalSafetyError("LIVE_LLM_EVAL_ALLOWED is required for live_llm runs")
    if transport_mode == "fixture_input":
        validate_fixture_input_registration(
            transport_mode=transport_mode,
            ai_mode=ai_mode,
            scenario_id=scenario_id,
            llm_provider=llm_provider,
            llm_requested_model=llm_requested_model,
        )
        return config
    sender = (expected_sender or "").strip().lower()
    recipient = (expected_recipient or "").strip().lower()
    if sender not in config.sender_emails:
        raise LiveEvalSafetyError("expected_sender is not allowlisted")
    if recipient not in config.recipient_emails:
        raise LiveEvalSafetyError("expected_recipient is not allowlisted")
    return config


def validate_run_row_for_intake(
    row: LiveEvalRunRow,
    *,
    tenant_id: str,
    scenario_id: str,
    attempt_id: int,
    sender_email: str,
    recipient_email: str,
    query: str,
    config: LiveEvalConfig | None = None,
    require_registered: bool = False,
) -> None:
    config = require_tenant_allowed(tenant_id, config)
    now = datetime.now(timezone.utc)
    if row.tenant_id != tenant_id:
        raise LiveEvalSafetyError("run tenant mismatch")
    if row.scenario_id != scenario_id:
        raise LiveEvalSafetyError("run scenario_id mismatch")
    if row.attempt_id != attempt_id:
        raise LiveEvalSafetyError("run attempt_id mismatch")
    if require_registered and row.status != RUN_STATUS_REGISTERED:
        raise LiveEvalSafetyError(
            f"run status must be registered for root intake, got {row.status!r}"
        )
    if row.status in TERMINAL_RUN_STATUSES:
        raise LiveEvalSafetyError(f"run status is terminal: {row.status}")
    if row.expires_at.tzinfo is None:
        expires_at = row.expires_at.replace(tzinfo=timezone.utc)
    else:
        expires_at = row.expires_at
    if expires_at < now:
        raise LiveEvalSafetyError("run has expired")
    if sender_email.strip().lower() != row.expected_sender.strip().lower():
        raise LiveEvalSafetyError("sender does not match registered expected_sender")
    if recipient_email.strip().lower() != row.expected_recipient.strip().lower():
        raise LiveEvalSafetyError("recipient does not match registered expected_recipient")
    label_token = f"label:{config.intake_label}"
    if label_token not in (query or "").replace(" ", "").lower():
        raise LiveEvalSafetyError(f"intake query must include {label_token}")


def require_live_eval_external_mutation_enabled(
    config: LiveEvalConfig | None = None,
) -> LiveEvalConfig:
    """Gate for live-eval mutations (send, intake trigger, cleanup)."""
    config = require_gmail_eval_enabled(config)
    if not config.external_side_effects_enabled:
        raise LiveEvalSafetyError("EXTERNAL_SIDE_EFFECT_TESTS=yes is required for live mutations")
    return config


def require_scenario_allowed_for_2f3(scenario_id: str) -> None:
    from app.evaluation.live.constants import ALLOWED_2F3_SCENARIOS

    if scenario_id not in ALLOWED_2F3_SCENARIOS:
        raise LiveEvalSafetyError(
            f"scenario_id {scenario_id!r} is not allowed for 2F.3 fixture_input live LLM"
        )


def require_workflow_sha_for_fixture_input() -> str:
    sha = (os.environ.get("BUILD_GIT_SHA") or os.environ.get("GITHUB_SHA") or "").strip()
    if not sha:
        raise LiveEvalSafetyError("BUILD_GIT_SHA or GITHUB_SHA is required for fixture_input")
    if sha.lower() in _FIXTURE_WORKFLOW_SHA_MARKERS:
        raise LiveEvalSafetyError("fixture_input requires a real workflow SHA")
    return sha


def validate_fixture_input_registration(
    *,
    transport_mode: str,
    ai_mode: str,
    scenario_id: str,
    llm_provider: str | None,
    llm_requested_model: str | None,
) -> None:
    if transport_mode != "fixture_input":
        return
    require_scenario_allowed_for_2f3(scenario_id)
    if ai_mode != "live_llm":
        raise LiveEvalSafetyError("fixture_input requires ai_mode live_llm")
    if ai_mode == "fixture_ai":
        raise LiveEvalSafetyError("fixture_input + fixture_ai is not allowed")
    if not llm_provider or not llm_requested_model:
        raise LiveEvalSafetyError(
            "llm_provider and llm_requested_model are required for fixture_input"
        )
    require_workflow_sha_for_fixture_input()


def validate_fixture_input_run_for_intake(
    row: LiveEvalRunRow,
    *,
    tenant_id: str,
) -> None:
    require_tenant_allowed(tenant_id)
    if row.tenant_id != tenant_id:
        raise LiveEvalSafetyError("run tenant mismatch")
    if row.transport_mode != "fixture_input":
        raise LiveEvalSafetyError("transport_mode must be fixture_input")
    if row.ai_mode != "live_llm":
        raise LiveEvalSafetyError("ai_mode must be live_llm")
    require_scenario_allowed_for_2f3(row.scenario_id)
    if row.status not in (RUN_STATUS_REGISTERED, RUN_STATUS_ACTIVE):
        raise LiveEvalSafetyError(f"run status {row.status!r} does not allow fixture intake")
    now = datetime.now(timezone.utc)
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        raise LiveEvalSafetyError("run has expired")


def require_scenario_allowed_for_2f2(scenario_id: str) -> None:
    from app.evaluation.live.constants import ALLOWED_2F2_SCENARIOS

    if scenario_id not in ALLOWED_2F2_SCENARIOS:
        raise LiveEvalSafetyError(
            f"scenario_id {scenario_id!r} is not allowed for 2F.2 live Gmail transport"
        )


def require_gmail_eval_enabled(config: LiveEvalConfig | None = None) -> LiveEvalConfig:
    config = require_live_eval_enabled(config)
    if not config.gmail_enabled:
        raise LiveEvalSafetyError("LIVE_GMAIL_EVAL_ALLOWED is required for Gmail readiness")
    return config


def validate_config_readiness(config: LiveEvalConfig | None = None) -> list[str]:
    """Return list of missing/invalid gate messages (empty = ready)."""
    config = config or get_live_eval_config()
    issues: list[str] = []
    if config.enabled is False:
        issues.append("LIVE_EVAL_ALLOWED=yes required with ENV=test")
    if not config.tenant_ids:
        issues.append("LIVE_EVAL_TENANT_IDS is empty")
    if not config.sender_emails:
        issues.append("LIVE_EVAL_SENDER_EMAILS is empty")
    if not config.recipient_emails:
        issues.append("LIVE_EVAL_RECIPIENT_EMAILS is empty")
    if not config.intake_label:
        issues.append("LIVE_EVAL_GMAIL_LABEL is empty")
    if config.max_scenarios_per_run != 1:
        issues.append("LIVE_EVAL_MAX_SCENARIOS_PER_RUN must be 1 for 2F.2")
    if config.max_gmail_sends_per_run != 1:
        issues.append("LIVE_EVAL_MAX_GMAIL_SENDS must be 1 for 2F.2")
    if config.max_gmail_replies_per_run != 0:
        issues.append("LIVE_EVAL_MAX_GMAIL_REPLIES must be 0 for 2F.2")
    return issues


def validate_live_gmail_registration(
    *,
    transport_mode: str,
    scenario_id: str,
    ai_mode: str,
) -> None:
    if transport_mode != "live_gmail":
        return
    require_scenario_allowed_for_2f2(scenario_id)
    if ai_mode != "fixture_ai":
        raise LiveEvalSafetyError("live_gmail transport requires ai_mode fixture_ai")


def require_live_eval_mutation_context(
    tenant_id: str,
    config: LiveEvalConfig | None = None,
) -> LiveEvalConfig:
    """All mutation gates for live-eval Gmail routes."""
    config = require_live_eval_external_mutation_enabled(config)
    return require_tenant_allowed(tenant_id, config)


def _validate_post_claim_cleanup_binding(
    row: LiveEvalRunRow,
    recipient_message_id: str | None,
) -> None:
    if not row.root_gmail_message_id or not row.root_job_id:
        raise LiveEvalSafetyError("post_claim cleanup requires trusted root binding")
    if not recipient_message_id:
        raise LiveEvalSafetyError("post_claim cleanup requires exact recipient_gmail_message_id")
    if recipient_message_id != row.root_gmail_message_id:
        raise LiveEvalSafetyError("recipient message id does not match registry root")


def _validate_aborted_pre_claim_cleanup(
    row: LiveEvalRunRow,
    recipient_message_id: str | None,
) -> None:
    if row.root_job_id:
        raise LiveEvalSafetyError("pre_claim cleanup not allowed when root_job_id is set")
    if row.root_gmail_message_id:
        raise LiveEvalSafetyError("pre_claim cleanup not allowed when root binding exists")
    if not recipient_message_id:
        raise LiveEvalSafetyError("pre_claim cleanup requires exact recipient_gmail_message_id")

    from app.evaluation.live.cleanup_resolver import resolve_recipient_from_journal
    from app.evaluation.live.journal import load_checkpoint

    checkpoint = load_checkpoint(row.evaluation_run_id)
    resolution = resolve_recipient_from_journal(checkpoint)
    if not resolution.resolved:
        raise LiveEvalSafetyError(resolution.blocked_reason or "journal_resolution_failed")
    if resolution.recipient_gmail_message_id != recipient_message_id:
        raise LiveEvalSafetyError("recipient message id does not match journal delivery_confirmed")


def validate_live_gmail_run_for_mutation(
    row: LiveEvalRunRow,
    *,
    tenant_id: str,
    recipient_message_id: str | None = None,
    mutation_operation: str | None = None,
    cleanup_phase: str | None = None,
) -> None:
    require_tenant_allowed(tenant_id)
    if row.tenant_id != tenant_id:
        raise LiveEvalSafetyError("run tenant mismatch")
    require_scenario_allowed_for_2f2(row.scenario_id)
    if row.ai_mode != "fixture_ai":
        raise LiveEvalSafetyError("fixture_ai required for live Gmail mutation")
    if row.transport_mode != "live_gmail":
        raise LiveEvalSafetyError("transport_mode must be live_gmail")
    now = datetime.now(timezone.utc)
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < now:
        raise LiveEvalSafetyError("run has expired")

    is_post_claim_cleanup_archive = (
        mutation_operation == LIVE_EVAL_MUTATION_CLEANUP_ARCHIVE
        and cleanup_phase == "post_claim"
    )
    is_pre_claim_cleanup_archive = (
        mutation_operation == LIVE_EVAL_MUTATION_CLEANUP_ARCHIVE
        and cleanup_phase == "pre_claim"
    )

    if row.status == RUN_STATUS_ABORTED:
        if is_post_claim_cleanup_archive:
            _validate_post_claim_cleanup_binding(row, recipient_message_id)
            return
        if is_pre_claim_cleanup_archive:
            _validate_aborted_pre_claim_cleanup(row, recipient_message_id)
            return
        raise LiveEvalSafetyError(f"run status is terminal: {row.status}")

    if row.status in TERMINAL_RUN_STATUSES:
        raise LiveEvalSafetyError(f"run status is terminal: {row.status}")

    if row.status == RUN_STATUS_REGISTERED:
        return

    if row.status == RUN_STATUS_ACTIVE:
        if is_pre_claim_cleanup_archive:
            _validate_aborted_pre_claim_cleanup(row, recipient_message_id)
            return
        if not row.root_gmail_message_id or not row.root_job_id:
            raise LiveEvalSafetyError("active run missing root binding")
        if is_post_claim_cleanup_archive:
            _validate_post_claim_cleanup_binding(row, recipient_message_id)
        return

    raise LiveEvalSafetyError(f"run status {row.status!r} does not allow mutation")


def validate_delivery_observation_allowed(row: LiveEvalRunRow) -> None:
    if row.status == RUN_STATUS_REGISTERED:
        return
    if row.status == RUN_STATUS_ACTIVE:
        if row.root_gmail_message_id and row.root_job_id:
            return
        raise LiveEvalSafetyError("active run missing root binding for delivery observation")
    if row.status in TERMINAL_RUN_STATUSES:
        raise LiveEvalSafetyError(f"run status is terminal: {row.status}")
    raise LiveEvalSafetyError(f"run status {row.status!r} not allowed for delivery observation")
