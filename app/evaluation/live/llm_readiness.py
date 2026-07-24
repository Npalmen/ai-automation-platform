"""Offline readiness checks for live LLM eval (0 provider calls)."""

from __future__ import annotations

import os

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.evaluation.live.config import LiveEvalConfig, get_live_eval_config
from app.evaluation.live.constants import (
    ALLOWED_2F3_SCENARIOS,
    PYTEST_MARKER_EXPR,
    S01_LOCKED_SCENARIO_HASH,
)
from app.evaluation.live.readiness import ReadinessReport
from app.evaluation.live.reporting import _FIXTURE_WORKFLOW_SHA_MARKERS
from app.evaluation.live.safety import require_tenant_allowed
from app.evaluation.live.scenario_input import load_locked_scenario_input


def _validate_llm_config(config: LiveEvalConfig) -> list[str]:
    issues: list[str] = []
    if not config.llm_enabled:
        issues.append("LIVE_LLM_EVAL_ALLOWED=yes required for live LLM eval")
    if not config.llm_provider:
        issues.append("LIVE_EVAL_LLM_PROVIDER is empty")
    if not config.llm_model:
        issues.append("LIVE_EVAL_LLM_MODEL is empty")
    if config.llm_timeout <= 0:
        issues.append("LIVE_EVAL_LLM_TIMEOUT must be positive")
    if config.llm_max_tokens <= 0:
        issues.append("LIVE_EVAL_LLM_MAX_TOKENS must be positive")
    if config.max_llm_calls_per_run < 4:
        issues.append("LIVE_EVAL_MAX_LLM_CALLS must be at least 4 for S01")
    return issues


def _validate_workflow_sha() -> list[str]:
    sha = (os.environ.get("BUILD_GIT_SHA") or os.environ.get("GITHUB_SHA") or "").strip()
    if not sha:
        return ["BUILD_GIT_SHA or GITHUB_SHA is required"]
    if sha.lower() in _FIXTURE_WORKFLOW_SHA_MARKERS:
        return ["workflow SHA must not be a fixture marker"]
    return []


def _validate_locked_scenario() -> list[str]:
    issues: list[str] = []
    for scenario_id in ALLOWED_2F3_SCENARIOS:
        try:
            scenario = load_locked_scenario_input(scenario_id)
        except Exception as exc:
            issues.append(f"locked scenario load failed for {scenario_id}: {exc}")
            continue
        if scenario.scenario_id not in ALLOWED_2F3_SCENARIOS:
            issues.append(f"scenario {scenario_id} not allowlisted")
    if "S01_lead_laddbox_quality" in ALLOWED_2F3_SCENARIOS and not S01_LOCKED_SCENARIO_HASH:
        issues.append("S01 locked hash missing")
    return issues


def run_llm_offline_readiness_checks(
    config: LiveEvalConfig | None = None,
) -> ReadinessReport:
    """Verify live LLM eval configuration without provider network calls."""
    config = config or get_live_eval_config()
    issues: list[str] = []
    if not config.enabled:
        issues.append("LIVE_EVAL_ALLOWED=yes required with ENV=test")
    issues.extend(_validate_llm_config(config))
    issues.extend(_validate_workflow_sha())
    issues.extend(_validate_locked_scenario())
    if not config.tenant_ids:
        issues.append("LIVE_EVAL_TENANT_IDS is empty")
    checks: dict = {
        "mode": "llm_offline",
        "pytest_marker_expr": PYTEST_MARKER_EXPR,
        "env_fingerprint": config.env_fingerprint,
        "llm_provider": config.llm_provider or None,
        "llm_requested_model": config.llm_model or None,
        "allowed_scenarios": sorted(ALLOWED_2F3_SCENARIOS),
        "live_llm_calls": 0,
        "gmail_required": False,
    }
    return ReadinessReport(ready=not issues, issues=issues, checks=checks)


def run_llm_readiness_checks(
    db: Session,
    tenant_id: str,
    *,
    config: LiveEvalConfig | None = None,
) -> ReadinessReport:
    """Offline readiness including database and tenant gates (0 LLM calls)."""
    report = run_llm_offline_readiness_checks(config)
    issues = list(report.issues)
    checks = dict(report.checks)
    checks["tenant_id"] = tenant_id

    try:
        require_tenant_allowed(tenant_id, config or get_live_eval_config())
    except Exception as exc:
        issues.append(str(exc))

    try:
        db.execute(text("SELECT 1"))
        checks["database_ok"] = True
    except Exception as exc:
        checks["database_ok"] = False
        issues.append(f"database check failed: {exc}")

    checks["write_policy"] = "fixture_input blocks all external adapter writes"
    checks["gmail_secrets_required"] = False
    return ReadinessReport(ready=not issues, issues=issues, checks=checks)
