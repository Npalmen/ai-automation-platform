"""Fail-closed safety gates for live evaluation."""

from __future__ import annotations

from datetime import datetime, timezone

from app.evaluation.live.config import LiveEvalConfig, get_live_eval_config
from app.evaluation.live.constants import (
    ALLOWED_AI_MODES,
    ALLOWED_TRANSPORT_MODES,
    RUN_STATUS_REGISTERED,
    TERMINAL_RUN_STATUSES,
)
from app.evaluation.live.errors import LiveEvalSafetyError
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
    expected_sender: str,
    expected_recipient: str,
    config: LiveEvalConfig | None = None,
) -> LiveEvalConfig:
    config = require_tenant_allowed(tenant_id, config)
    if transport_mode not in ALLOWED_TRANSPORT_MODES:
        raise LiveEvalSafetyError(f"transport_mode {transport_mode!r} is not allowed")
    if ai_mode not in ALLOWED_AI_MODES:
        raise LiveEvalSafetyError(f"ai_mode {ai_mode!r} is not allowed")
    if ai_mode == "live_llm" and not config.llm_enabled:
        raise LiveEvalSafetyError("LIVE_LLM_EVAL_ALLOWED is required for live_llm runs")
    sender = expected_sender.strip().lower()
    recipient = expected_recipient.strip().lower()
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
    return issues
