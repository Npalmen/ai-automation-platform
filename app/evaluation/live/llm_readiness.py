"""Offline readiness checks for live LLM eval (0 provider calls)."""

from __future__ import annotations

import hashlib
import json
import os

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.evaluation.live.config import LiveEvalConfig, get_live_eval_config
from app.evaluation.live.constants import (
    ALLOWED_2F3_SCENARIOS,
    PYTEST_MARKER_EXPR,
    S01_LOCKED_SCENARIO_HASH,
)
from app.evaluation.live.model_identity import (
    LIVE_EVAL_ALLOWED_RETURNED_MODELS,
    model_identity_registry_fingerprint,
    validate_model_identity_registry,
)
from app.evaluation.live.readiness import ReadinessReport
from app.evaluation.live.reporting import _FIXTURE_WORKFLOW_SHA_MARKERS
from app.evaluation.live.safety import require_tenant_allowed
from app.evaluation.live.scenario_input import load_locked_scenario_input

LIVE_LLM_READINESS_SCHEMA_VERSION = "2f.3c.llm-readiness"
LIVE_LLM_PINNED_PROVIDER = "openai"
LIVE_LLM_PINNED_MODEL = "gpt-4o-mini"
LIVE_LLM_PINNED_API_URL = "https://api.openai.com/v1/chat/completions"
LIVE_LLM_PINNED_TIMEOUT_SECONDS = 60
LIVE_LLM_PINNED_MAX_TOKENS = 2048
LIVE_LLM_PINNED_CALL_BUDGET = 4
LIVE_LLM_PINNED_RETRY_COUNT = 0
LIVE_LLM_PINNED_TEMPERATURE = 0.0

_CI_PLACEHOLDER_SECRETS = frozenset({"ci-admin-key"})


def _validate_secret_binding(settings: Settings, *, required: bool) -> tuple[list[str], dict[str, bool]]:
    issues: list[str] = []
    llm_key = (settings.LLM_API_KEY or "").strip()
    admin_key = (settings.ADMIN_API_KEY or "").strip()

    llm_configured = bool(llm_key) and llm_key not in _CI_PLACEHOLDER_SECRETS
    admin_configured = bool(admin_key) and admin_key not in _CI_PLACEHOLDER_SECRETS

    if required:
        if not llm_key or llm_key in _CI_PLACEHOLDER_SECRETS:
            issues.append("LLM_API_KEY is missing or uses a CI placeholder")
        if not admin_key or admin_key in _CI_PLACEHOLDER_SECRETS:
            issues.append("ADMIN_API_KEY is missing or uses a CI placeholder")

    return issues, {
        "llm_api_key_configured": llm_configured,
        "admin_api_key_configured": admin_configured,
    }


def _validate_pinned_contract(
    config: LiveEvalConfig,
    settings: Settings,
) -> list[str]:
    issues: list[str] = []
    provider = (config.llm_provider or "").strip()
    model = (config.llm_model or "").strip()
    api_url = (settings.LLM_API_URL or "").strip()

    if provider != LIVE_LLM_PINNED_PROVIDER:
        issues.append(
            f"LIVE_EVAL_LLM_PROVIDER must be {LIVE_LLM_PINNED_PROVIDER!r}, got {provider!r}"
        )
    if model != LIVE_LLM_PINNED_MODEL:
        issues.append(
            f"LIVE_EVAL_LLM_MODEL must be {LIVE_LLM_PINNED_MODEL!r}, got {model!r}"
        )
    if api_url != LIVE_LLM_PINNED_API_URL:
        issues.append(
            f"LLM_API_URL must be {LIVE_LLM_PINNED_API_URL!r}, got {api_url!r}"
        )
    if config.max_llm_calls_per_run != LIVE_LLM_PINNED_CALL_BUDGET:
        issues.append(
            f"LIVE_EVAL_MAX_LLM_CALLS must be {LIVE_LLM_PINNED_CALL_BUDGET}, "
            f"got {config.max_llm_calls_per_run}"
        )
    if config.llm_timeout != LIVE_LLM_PINNED_TIMEOUT_SECONDS:
        issues.append(
            f"LIVE_EVAL_LLM_TIMEOUT must be {LIVE_LLM_PINNED_TIMEOUT_SECONDS}, "
            f"got {config.llm_timeout}"
        )
    if config.llm_max_tokens != LIVE_LLM_PINNED_MAX_TOKENS:
        issues.append(
            f"LIVE_EVAL_LLM_MAX_TOKENS must be {LIVE_LLM_PINNED_MAX_TOKENS}, "
            f"got {config.llm_max_tokens}"
        )
    if float(settings.LLM_TEMPERATURE) != LIVE_LLM_PINNED_TEMPERATURE:
        issues.append(
            f"LLM_TEMPERATURE must be {LIVE_LLM_PINNED_TEMPERATURE}, "
            f"got {settings.LLM_TEMPERATURE}"
        )
    if int(settings.LLM_RETRY_ATTEMPTS) != LIVE_LLM_PINNED_RETRY_COUNT:
        issues.append(
            f"LLM_RETRY_ATTEMPTS must be {LIVE_LLM_PINNED_RETRY_COUNT}, "
            f"got {settings.LLM_RETRY_ATTEMPTS}"
        )
    return issues


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
    return issues


def _validate_workflow_sha() -> tuple[list[str], str | None]:
    sha = (os.environ.get("BUILD_GIT_SHA") or os.environ.get("GITHUB_SHA") or "").strip()
    if not sha:
        return ["BUILD_GIT_SHA or GITHUB_SHA is required"], None
    if sha.lower() in _FIXTURE_WORKFLOW_SHA_MARKERS:
        return ["workflow SHA must not be a fixture marker"], None
    return [], sha


def _validate_locked_scenario() -> tuple[list[str], bool]:
    issues: list[str] = []
    scenario_ok = True
    for scenario_id in ALLOWED_2F3_SCENARIOS:
        try:
            scenario = load_locked_scenario_input(scenario_id)
        except Exception as exc:
            issues.append(f"locked scenario load failed for {scenario_id}: {exc}")
            scenario_ok = False
            continue
        if scenario.scenario_id not in ALLOWED_2F3_SCENARIOS:
            issues.append(f"scenario {scenario_id} not allowlisted")
            scenario_ok = False
    if "S01_lead_laddbox_quality" in ALLOWED_2F3_SCENARIOS and not S01_LOCKED_SCENARIO_HASH:
        issues.append("S01 locked hash missing")
        scenario_ok = False
    return issues, scenario_ok


def _config_fingerprint(config: LiveEvalConfig, settings: Settings) -> str:
    payload = {
        "provider": config.llm_provider,
        "requested_model": config.llm_model,
        "api_endpoint": LIVE_LLM_PINNED_API_URL,
        "call_budget": config.max_llm_calls_per_run,
        "timeout_seconds": config.llm_timeout,
        "max_tokens": config.llm_max_tokens,
        "retry_count": LIVE_LLM_PINNED_RETRY_COUNT,
        "temperature": LIVE_LLM_PINNED_TEMPERATURE,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _base_checks(
    config: LiveEvalConfig,
    settings: Settings,
    *,
    build_git_sha: str | None,
    scenario_ok: bool,
    secret_flags: dict[str, bool],
    seed_gate: bool | None,
    database_ok: bool | None = None,
    tenant_id: str | None = None,
    model_identity_contract_ok: bool = True,
) -> dict[str, object]:
    checks: dict[str, object] = {
        "report_schema_version": LIVE_LLM_READINESS_SCHEMA_VERSION,
        "mode": "llm_offline",
        "pytest_marker_expr": PYTEST_MARKER_EXPR,
        "env_fingerprint": config.env_fingerprint,
        "build_git_sha": build_git_sha,
        "config_fingerprint": _config_fingerprint(config, settings),
        "tenant_id": tenant_id,
        "llm_provider": LIVE_LLM_PINNED_PROVIDER,
        "llm_requested_model": LIVE_LLM_PINNED_MODEL,
        "model_identity_registry_fingerprint": model_identity_registry_fingerprint(),
        "model_identity_contract_ok": model_identity_contract_ok,
        "api_endpoint": LIVE_LLM_PINNED_API_URL,
        "call_budget": LIVE_LLM_PINNED_CALL_BUDGET,
        "timeout_seconds": LIVE_LLM_PINNED_TIMEOUT_SECONDS,
        "max_tokens": LIVE_LLM_PINNED_MAX_TOKENS,
        "retry_count": LIVE_LLM_PINNED_RETRY_COUNT,
        "temperature": LIVE_LLM_PINNED_TEMPERATURE,
        "allowed_scenarios": sorted(ALLOWED_2F3_SCENARIOS),
        "scenario_hash_ok": scenario_ok,
        "gmail_required": False,
        "seed_gate": seed_gate,
        "llm_api_key_configured": secret_flags["llm_api_key_configured"],
        "admin_api_key_configured": secret_flags["admin_api_key_configured"],
        "write_policy": "fixture_input blocks all external adapter writes",
        "write_policy_ok": True,
        "live_llm_calls": 0,
        "llm_operations": 0,
        "external_writes": 0,
        "gmail_secrets_required": False,
    }
    if database_ok is not None:
        checks["database_ok"] = database_ok
    return checks


def run_llm_offline_readiness_checks(
    config: LiveEvalConfig | None = None,
    *,
    settings: Settings | None = None,
) -> ReadinessReport:
    """Verify live LLM eval configuration without provider network calls."""
    config = config or get_live_eval_config()
    settings = settings or get_settings()
    issues: list[str] = []
    if not config.enabled:
        issues.append("LIVE_EVAL_ALLOWED=yes required with ENV=test")
    issues.extend(_validate_llm_config(config))
    issues.extend(_validate_pinned_contract(config, settings))
    registry_issues = validate_model_identity_registry()
    issues.extend(registry_issues)
    if (config.llm_model or "").strip() not in LIVE_EVAL_ALLOWED_RETURNED_MODELS:
        issues.append(
            f"requested model {config.llm_model!r} is missing from model identity registry"
        )
    sha_issues, build_git_sha = _validate_workflow_sha()
    issues.extend(sha_issues)
    scenario_issues, scenario_ok = _validate_locked_scenario()
    issues.extend(scenario_issues)
    if not config.tenant_ids:
        issues.append("LIVE_EVAL_TENANT_IDS is empty")
    secret_issues, secret_flags = _validate_secret_binding(settings, required=False)
    issues.extend(secret_issues)
    checks = _base_checks(
        config,
        settings,
        build_git_sha=build_git_sha,
        scenario_ok=scenario_ok and not scenario_issues,
        secret_flags=secret_flags,
        seed_gate=None,
        model_identity_contract_ok=not registry_issues
        and (config.llm_model or "").strip() in LIVE_EVAL_ALLOWED_RETURNED_MODELS,
    )
    return ReadinessReport(ready=not issues, issues=issues, checks=checks)


def run_llm_readiness_checks(
    db: Session,
    tenant_id: str,
    *,
    config: LiveEvalConfig | None = None,
    settings: Settings | None = None,
) -> ReadinessReport:
    """Offline readiness including database and tenant gates (0 LLM calls)."""
    config = config or get_live_eval_config()
    settings = settings or get_settings()
    report = run_llm_offline_readiness_checks(config, settings=settings)
    issues = list(report.issues)
    checks = dict(report.checks)
    checks["tenant_id"] = tenant_id
    checks["mode"] = "llm_transport_readiness"

    if not config.seed_allowed:
        issues.append("LIVE_EVAL_SEED_ALLOWED=yes required for tenant seed")

    secret_issues, secret_flags = _validate_secret_binding(settings, required=True)
    issues.extend(secret_issues)
    checks["llm_api_key_configured"] = secret_flags["llm_api_key_configured"]
    checks["admin_api_key_configured"] = secret_flags["admin_api_key_configured"]
    checks["seed_gate"] = config.seed_allowed

    try:
        require_tenant_allowed(tenant_id, config)
    except Exception as exc:
        issues.append(str(exc))

    try:
        db.execute(text("SELECT 1"))
        checks["database_ok"] = True
    except Exception as exc:
        checks["database_ok"] = False
        issues.append(f"database check failed: {exc}")

    return ReadinessReport(ready=not issues, issues=issues, checks=checks)


def build_llm_readiness_artifact(report: ReadinessReport) -> dict[str, object]:
    """Serialize readiness output for workflow artifacts without credential leakage."""
    payload = {
        "ready": report.ready,
        "issues": report.issues,
        "live_llm_calls": 0,
        "llm_operations": 0,
        "external_writes": 0,
    }
    payload.update(report.checks)
    return payload
