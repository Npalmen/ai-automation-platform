"""Phase-separated automation readiness for automatic Gmail campaigns."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.evaluation.live.campaign.automatic_action_contract import (
    AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE,
    CANARY_AUTO_ACTIONS,
)
from app.evaluation.live.campaign.automatic_action_contract_core import (
    AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE,
    CORE_AUTO_ACTIONS,
)
from app.evaluation.live.campaign.automatic_fixture_completeness import (
    validate_automatic_fixture_bundle_completeness,
)
from app.evaluation.live.campaign.repo_paths import (
    REQUIRED_AUTOMATIC_CAMPAIGN_SCRIPTS,
    validate_required_scripts,
)
from app.evaluation.live.campaign.tenant_automation_lifecycle import (
    hash_auto_actions,
    load_snapshot_file,
    snapshot_tenant_config,
    verify_automation_not_broadly_enabled,
    verify_profile_automation_active,
)
from app.evaluation.live.campaign.tenant_materialization import (
    LIVE_EVAL_TENANT_ID,
    resolve_live_eval_tenant_context,
)
from app.workflows.tenant_automation import FULL_AUTO, normalize_automation_mode

AUTOMATION_PHASE_PRE_SEED = "pre_seed"
AUTOMATION_PHASE_ACTIVE_CANARY = "active_canary"
AUTOMATION_PHASE_ACTIVE_CORE = "active_core"
AUTOMATION_PHASE_RESTORED = "restored"
VALID_AUTOMATION_PHASES = frozenset(
    {
        AUTOMATION_PHASE_PRE_SEED,
        AUTOMATION_PHASE_ACTIVE_CANARY,
        AUTOMATION_PHASE_ACTIVE_CORE,
        AUTOMATION_PHASE_RESTORED,
    }
)
PHASE_MISMATCH_ERROR = "automatic_automation_phase_mismatch"

BLOCKED_INTEGRATION_KEYS = frozenset({"monday", "sheets", "google_sheets", "visma"})
ALLOWED_AUTOMATIC_INTEGRATIONS = frozenset({"google_mail"})

_AUTOMATIC_CAMPAIGN_TYPES = frozenset({
    AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE,
    AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE,
})

_PROFILE_BY_CAMPAIGN: dict[str, dict[str, str]] = {
    AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE: CANARY_AUTO_ACTIONS,
    AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE: CORE_AUTO_ACTIONS,
}

_ACTIVE_PHASE_BY_CAMPAIGN: dict[str, str] = {
    AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE: AUTOMATION_PHASE_ACTIVE_CANARY,
    AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE: AUTOMATION_PHASE_ACTIVE_CORE,
}


def resolve_automation_phase(
    explicit: str | None = None,
    *,
    campaign_type: str | None = None,
) -> str | None:
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    if campaign_type == AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE:
        env_phase = os.environ.get("AUTOMATIC_CORE_AUTOMATION_PHASE", "").strip()
        if env_phase:
            return env_phase
    env_phase = os.environ.get("AUTOMATIC_CANARY_AUTOMATION_PHASE", "").strip()
    return env_phase or None


def _read_tenant_record(tenant_id: str):
    from app.repositories.postgres.database import SessionLocal
    from app.repositories.postgres.tenant_config_models import TenantConfigRecord

    db = SessionLocal()
    try:
        return db.get(TenantConfigRecord, tenant_id)
    finally:
        db.close()


def _validate_integration_scope(row, *, campaign_label: str) -> list[str]:
    issues: list[str] = []
    if row is None:
        return ["tenant record not found for integration scope check"]
    allowed = {str(item).strip().lower() for item in (row.allowed_integrations or [])}
    for blocked in sorted(allowed & BLOCKED_INTEGRATION_KEYS):
        issues.append(f"integration {blocked!r} is not allowed for {campaign_label}")
    if allowed and not allowed.issubset(ALLOWED_AUTOMATIC_INTEGRATIONS):
        unexpected = sorted(allowed - ALLOWED_AUTOMATIC_INTEGRATIONS)
        issues.append(
            f"unexpected integrations for {campaign_label}: " + ", ".join(unexpected)
        )
    settings = dict(row.settings or {})
    integrations = dict(settings.get("integrations") or {})
    for key in ("monday", "sheets", "google_sheets", "visma"):
        if integrations.get(key):
            issues.append(f"integration settings enable {key!r}")
    return issues


def _validate_handoff_disabled(tenant_id: str, tenant_settings: dict[str, Any] | None) -> list[str]:
    ctx = resolve_live_eval_tenant_context(
        tenant_id=tenant_id,
        tenant_settings=tenant_settings,
    )
    if ctx.internal_handoff_enabled:
        return ["send_internal_handoff must be disabled/not materialized for automatic Gmail"]
    return []


def _validate_core_semantic_auto_reply_scope(auto_actions: dict[str, Any] | None) -> list[str]:
    """Require lead + customer_inquiry auto only (eligibility, not sole authorization)."""
    issues: list[str] = []
    actions = auto_actions or {}
    for job_type in ("lead", "customer_inquiry"):
        if normalize_automation_mode(actions.get(job_type)) != FULL_AUTO:
            issues.append(
                f"send_customer_auto_reply eligibility requires {job_type}=auto, "
                f"got {actions.get(job_type)!r}"
            )
    for job_type, raw in sorted(actions.items()):
        if job_type in ("lead", "customer_inquiry"):
            continue
        if normalize_automation_mode(raw) == FULL_AUTO:
            issues.append(
                f"broad auto automation not allowed for job_type={job_type!r}"
            )
    return issues


def _snapshot_path(campaign_type: str) -> Path | None:
    if campaign_type == AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE:
        raw = os.environ.get("LIVE_EVAL_AUTOMATIC_CORE_SNAPSHOT_PATH", "").strip()
        if raw:
            return Path(raw)
    raw = os.environ.get("LIVE_EVAL_AUTOMATIC_CANARY_SNAPSHOT_PATH", "").strip()
    if not raw:
        return None
    return Path(raw)


def validate_automatic_automation_readiness(
    *,
    automation_phase: str,
    campaign_type: str = AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE,
    tenant_id: str = LIVE_EVAL_TENANT_ID,
    baseline_snapshot_path: Path | str | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Validate automation readiness for the requested phase and campaign profile."""
    matrix: dict[str, Any] = {
        "automation_phase": automation_phase,
        "campaign_type": campaign_type,
    }
    issues: list[str] = []
    profile = _PROFILE_BY_CAMPAIGN.get(campaign_type)
    if profile is None:
        return [f"unsupported automatic campaign_type={campaign_type!r}"], matrix

    expected_active_phase = _ACTIVE_PHASE_BY_CAMPAIGN[campaign_type]
    if automation_phase not in VALID_AUTOMATION_PHASES:
        issues.append(f"{PHASE_MISMATCH_ERROR}: unknown phase {automation_phase!r}")
        return issues, matrix

    issues.extend(
        validate_required_scripts(
            REQUIRED_AUTOMATIC_CAMPAIGN_SCRIPTS.get(campaign_type, ())
        )
    )
    matrix["required_scripts"] = list(
        REQUIRED_AUTOMATIC_CAMPAIGN_SCRIPTS.get(campaign_type, ())
    )

    snapshot_path = baseline_snapshot_path or _snapshot_path(campaign_type)
    matrix["snapshot_path_configured"] = snapshot_path is not None

    try:
        runtime_snapshot = snapshot_tenant_config(tenant_id=tenant_id)
    except Exception as exc:
        issues.append(f"tenant automation snapshot failed: {exc}")
        return issues, matrix

    matrix["runtime_config_hash"] = runtime_snapshot.config_hash
    row = _read_tenant_record(tenant_id)
    tenant_settings = dict(row.settings or {}) if row is not None else {}

    if automation_phase == AUTOMATION_PHASE_PRE_SEED:
        issues.extend(verify_automation_not_broadly_enabled(runtime_snapshot.auto_actions))
        if snapshot_path is not None and Path(snapshot_path).is_file():
            issues.append(
                f"{PHASE_MISMATCH_ERROR}: snapshot must not exist before pre-seed capture"
            )
        matrix["internal_handoff_enabled"] = resolve_live_eval_tenant_context(
            tenant_id=tenant_id,
            tenant_settings=tenant_settings,
        ).internal_handoff_enabled

    elif automation_phase == expected_active_phase:
        if snapshot_path is None or not Path(snapshot_path).is_file():
            issues.append("rollback snapshot unavailable before active campaign readiness")
        else:
            baseline = load_snapshot_file(snapshot_path)
            matrix["pre_run_config_hash"] = baseline.config_hash
            matrix["active_run_config_hash"] = runtime_snapshot.config_hash
            if runtime_snapshot.config_hash == baseline.config_hash:
                issues.append(
                    f"{PHASE_MISMATCH_ERROR}: active config must differ from baseline"
                )
        issues.extend(verify_profile_automation_active(runtime_snapshot.auto_actions, profile))
        if campaign_type == AUTOMATIC_GMAIL_CORE_CAMPAIGN_TYPE:
            issues.extend(_validate_core_semantic_auto_reply_scope(runtime_snapshot.auto_actions))
        issues.extend(_validate_handoff_disabled(tenant_id, tenant_settings))
        issues.extend(_validate_integration_scope(row, campaign_label=campaign_type))

    elif automation_phase == AUTOMATION_PHASE_RESTORED:
        if snapshot_path is None or not Path(snapshot_path).is_file():
            issues.append("rollback snapshot unavailable for restored phase check")
        else:
            baseline = load_snapshot_file(snapshot_path)
            matrix["pre_run_config_hash"] = baseline.config_hash
            matrix["post_run_config_hash"] = runtime_snapshot.config_hash
            if runtime_snapshot.config_hash != baseline.config_hash:
                issues.append(
                    "post_run_config_hash does not match pre_run_config_hash after restore"
                )
            issues.extend(verify_automation_not_broadly_enabled(runtime_snapshot.auto_actions))

    matrix["semantic_scope"] = {
        "authorized_action": "send_customer_auto_reply",
        "authorization": "auto_execute",
        "profile": dict(profile),
        "profile_hash": hash_auto_actions(profile),
    }
    return issues, matrix


def build_automatic_campaign_readiness_gates(
    *,
    automation_phase: str | None,
    tenant_id: str = LIVE_EVAL_TENANT_ID,
    campaign_type: str,
    selected_scenario_ids: tuple[str, ...] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Entry point for automatic Gmail campaign automation gates."""
    if campaign_type not in _AUTOMATIC_CAMPAIGN_TYPES:
        return [], {}
    phase = resolve_automation_phase(automation_phase, campaign_type=campaign_type)
    if phase is None:
        return [
            f"{PHASE_MISMATCH_ERROR}: automation_phase is required for {campaign_type!r}"
        ], {}
    issues, matrix = validate_automatic_automation_readiness(
        automation_phase=phase,
        campaign_type=campaign_type,
        tenant_id=tenant_id,
    )
    expected_active = _ACTIVE_PHASE_BY_CAMPAIGN[campaign_type]
    if phase in (AUTOMATION_PHASE_PRE_SEED, expected_active):
        bundle_issues, bundle_matrix = validate_automatic_fixture_bundle_completeness(
            campaign_type=campaign_type,
            selected_scenario_ids=selected_scenario_ids,
        )
        issues.extend(bundle_issues)
        matrix["fixture_bundle_completeness"] = bundle_matrix
    return issues, matrix
