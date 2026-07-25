"""Fail-closed safety gates for full-system testbot campaigns."""

from __future__ import annotations

import os
import re

from app.evaluation.live.campaign.modes import CAMPAIGN_TYPE_REPLY_BUDGET, CAMPAIGN_TYPE_SEND_BUDGET
from app.evaluation.live.campaign.registry import get_campaign_scenario, get_campaign_scenario_ids
from app.evaluation.live.config import LiveEvalConfig, get_live_eval_config
from app.evaluation.live.constants import ALLOWED_2F2_SCENARIOS
from app.evaluation.live.errors import LiveEvalSafetyError
from app.evaluation.live.safety import require_live_eval_enabled, require_tenant_allowed

_PRODUCTION_DB_TOKENS = ("prod", "production", "live", "rds.amazonaws.com")
_PRODUCTION_HOST_TOKENS = ("api.krowolf.se", "krowolf.se")
_BLOCKED_RECIPIENT_PATTERNS = (
    re.compile(r"@gmail\.com$", re.I),  # only allowlisted eval addresses
)


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("yes", "true", "1")


def campaign_enabled(config: LiveEvalConfig | None = None) -> bool:
    config = config or get_live_eval_config()
    return config.enabled and _env_truthy("FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED")


def require_campaign_enabled(config: LiveEvalConfig | None = None) -> LiveEvalConfig:
    config = require_live_eval_enabled(config)
    if not campaign_enabled(config):
        raise LiveEvalSafetyError(
            "FULL_SYSTEM_TESTBOT_CAMPAIGN_ALLOWED=yes is required for campaign scenarios"
        )
    return config


def require_campaign_scenario_allowed(scenario_id: str) -> None:
    if scenario_id in ALLOWED_2F2_SCENARIOS:
        return
    if scenario_id not in get_campaign_scenario_ids():
        raise LiveEvalSafetyError(
            f"scenario_id {scenario_id!r} is not allowlisted for live Gmail (2F.2 or campaign)"
        )


def require_scenario_allowed_for_live_gmail(scenario_id: str) -> None:
    """Unified allowlist for 2F.2 S01 and full-system campaign scenarios."""
    if scenario_id in ALLOWED_2F2_SCENARIOS:
        return
    require_campaign_enabled()
    require_campaign_scenario_allowed(scenario_id)


def validate_no_production_resources(
    *,
    database_url: str = "",
    app_base_url: str = "",
    tenant_id: str = "",
) -> list[str]:
    """Return issues if environment appears to target production resources."""
    issues: list[str] = []
    db_lower = (database_url or "").lower()
    for token in _PRODUCTION_DB_TOKENS:
        if token in db_lower and "live_eval" not in db_lower and "test" not in db_lower:
            issues.append(f"DATABASE_URL appears production-like (token={token!r})")

    url_lower = (app_base_url or "").lower()
    for token in _PRODUCTION_HOST_TOKENS:
        if token in url_lower:
            issues.append(f"app_base_url targets production host ({token!r})")

    if tenant_id == "T_NIKLAS_DEMO_001":
        issues.append("pilot tenant T_NIKLAS_DEMO_001 is not allowed for testbot campaigns")

    return issues


def validate_campaign_budget_config(
    *,
    campaign_type: str,
    config: LiveEvalConfig | None = None,
) -> list[str]:
    config = require_campaign_enabled(config)
    issues: list[str] = []
    ceiling = CAMPAIGN_TYPE_SEND_BUDGET.get(campaign_type)
    if ceiling is None:
        issues.append(f"unknown campaign_type: {campaign_type!r}")
        return issues

    if config.max_scenarios_per_run > ceiling:
        issues.append(
            f"LIVE_EVAL_MAX_SCENARIOS_PER_RUN={config.max_scenarios_per_run} exceeds "
            f"campaign ceiling {ceiling} for {campaign_type!r}"
        )
    if config.max_gmail_sends_per_run > ceiling:
        issues.append(
            f"LIVE_EVAL_MAX_GMAIL_SENDS={config.max_gmail_sends_per_run} exceeds "
            f"campaign ceiling {ceiling} for {campaign_type!r}"
        )
    if not config.sender_emails:
        issues.append("LIVE_EVAL_SENDER_EMAILS is empty")
    if not config.recipient_emails:
        issues.append("LIVE_EVAL_RECIPIENT_EMAILS is empty")
    if len(config.sender_emails) != 1:
        issues.append("exactly one LIVE_EVAL_SENDER_EMAILS entry required")
    if len(config.recipient_emails) != 1:
        issues.append("exactly one LIVE_EVAL_RECIPIENT_EMAILS entry required")
    return issues


def validate_campaign_scenario_mode(
    scenario_id: str,
    *,
    expected_mode: str | None = None,
) -> list[str]:
    issues: list[str] = []
    try:
        scenario = get_campaign_scenario(scenario_id)
    except LiveEvalSafetyError as exc:
        return [str(exc)]

    if expected_mode and scenario.mode != expected_mode:
        issues.append(
            f"scenario {scenario_id!r} mode {scenario.mode!r} != expected {expected_mode!r}"
        )
    if scenario.budgets.gmail_replies > 0 and scenario.mode == "observe":
        issues.append(f"observe scenario {scenario_id!r} must not budget gmail_replies > 0")
    if scenario.budgets.external_writes > 0 and scenario.mode == "observe":
        issues.append(f"observe scenario {scenario_id!r} must not budget external_writes > 0")
    if scenario.mode == "semi_automatic":
        reply_ceiling = CAMPAIGN_TYPE_REPLY_BUDGET.get(scenario.campaign_type, 0)
        if scenario.budgets.gmail_replies > reply_ceiling and reply_ceiling:
            issues.append(
                f"semi_automatic scenario {scenario_id!r} gmail_replies exceeds campaign ceiling"
            )
    return issues


def validate_campaign_tenant(tenant_id: str, config: LiveEvalConfig | None = None) -> list[str]:
    issues: list[str] = []
    try:
        require_tenant_allowed(tenant_id, config)
    except LiveEvalSafetyError as exc:
        issues.append(str(exc))
    if tenant_id != "TENANT_LIVE_EVAL":
        issues.append(
            f"full-system testbot requires TENANT_LIVE_EVAL, got {tenant_id!r}"
        )
    return issues
