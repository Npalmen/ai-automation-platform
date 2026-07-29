"""Phase-separated automation readiness for automatic Gmail canary."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.evaluation.live.campaign.automatic_action_contract import (
    AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE,
    CANARY_AUTO_ACTIONS,
)
from app.evaluation.live.campaign.automatic_fixture_completeness import (
    validate_automatic_fixture_bundle_completeness,
)
from app.evaluation.live.campaign.repo_paths import (
    REQUIRED_AUTOMATIC_CANARY_SCRIPTS,
    validate_required_scripts,
)
from app.evaluation.live.campaign.tenant_automation_lifecycle import (
    hash_auto_actions,
    load_snapshot_file,
    snapshot_tenant_config,
    verify_automation_not_broadly_enabled,
    verify_canary_automation_active,
)
from app.evaluation.live.campaign.tenant_materialization import (
    LIVE_EVAL_TENANT_ID,
    resolve_live_eval_tenant_context,
)
from app.workflows.tenant_automation import FULL_AUTO, normalize_automation_mode

AUTOMATION_PHASE_PRE_SEED = "pre_seed"
AUTOMATION_PHASE_ACTIVE_CANARY = "active_canary"
AUTOMATION_PHASE_RESTORED = "restored"
VALID_AUTOMATION_PHASES = frozenset(
    {
        AUTOMATION_PHASE_PRE_SEED,
        AUTOMATION_PHASE_ACTIVE_CANARY,
        AUTOMATION_PHASE_RESTORED,
    }
)
PHASE_MISMATCH_ERROR = "automatic_canary_automation_phase_mismatch"

BLOCKED_INTEGRATION_KEYS = frozenset({"monday", "sheets", "google_sheets", "visma"})
ALLOWED_CANARY_INTEGRATIONS = frozenset({"google_mail"})


def resolve_automation_phase(explicit: str | None = None) -> str | None:
    if explicit and str(explicit).strip():
        return str(explicit).strip()
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


def _validate_integration_scope(row) -> list[str]:
    issues: list[str] = []
    if row is None:
        return ["tenant record not found for integration scope check"]
    allowed = {str(item).strip().lower() for item in (row.allowed_integrations or [])}
    for blocked in sorted(allowed & BLOCKED_INTEGRATION_KEYS):
        issues.append(f"integration {blocked!r} is not allowed for automatic Gmail canary")
    if allowed and not allowed.issubset(ALLOWED_CANARY_INTEGRATIONS):
        unexpected = sorted(allowed - ALLOWED_CANARY_INTEGRATIONS)
        issues.append(
            "unexpected integrations for automatic Gmail canary: "
            + ", ".join(unexpected)
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
        return ["send_internal_handoff must be disabled/not materialized for canary"]
    return []


def _validate_semantic_auto_reply_scope(auto_actions: dict[str, Any] | None) -> list[str]:
    """Require lead auto_execute semantics without broader auto automation."""
    issues: list[str] = []
    actions = auto_actions or {}
    lead_mode = normalize_automation_mode(actions.get("lead"))
    if lead_mode != FULL_AUTO:
        issues.append(
            "send_customer_auto_reply must be auto_execute (lead=auto), "
            f"got lead mode {lead_mode!r}"
        )
    for job_type, raw in sorted(actions.items()):
        if job_type == "lead":
            continue
        if normalize_automation_mode(raw) == FULL_AUTO:
            issues.append(
                f"broad auto automation not allowed for job_type={job_type!r}"
            )
    return issues


def _snapshot_path() -> Path | None:
    raw = os.environ.get("LIVE_EVAL_AUTOMATIC_CANARY_SNAPSHOT_PATH", "").strip()
    if not raw:
        return None
    return Path(raw)


def validate_automatic_automation_readiness(
    *,
    automation_phase: str,
    tenant_id: str = LIVE_EVAL_TENANT_ID,
    baseline_snapshot_path: Path | str | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Validate automation readiness for the requested phase."""
    matrix: dict[str, Any] = {"automation_phase": automation_phase}
    issues: list[str] = []

    if automation_phase not in VALID_AUTOMATION_PHASES:
        issues.append(
            f"{PHASE_MISMATCH_ERROR}: unknown phase {automation_phase!r}"
        )
        return issues, matrix

    issues.extend(validate_required_scripts(REQUIRED_AUTOMATIC_CANARY_SCRIPTS))
    matrix["required_scripts"] = list(REQUIRED_AUTOMATIC_CANARY_SCRIPTS)

    snapshot_path = baseline_snapshot_path or _snapshot_path()
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

    elif automation_phase == AUTOMATION_PHASE_ACTIVE_CANARY:
        if snapshot_path is None or not Path(snapshot_path).is_file():
            issues.append("rollback snapshot unavailable before active canary readiness")
        else:
            baseline = load_snapshot_file(snapshot_path)
            matrix["pre_run_config_hash"] = baseline.config_hash
            matrix["active_run_config_hash"] = runtime_snapshot.config_hash
            if runtime_snapshot.config_hash == baseline.config_hash:
                issues.append(
                    f"{PHASE_MISMATCH_ERROR}: active canary config must differ from baseline"
                )
        issues.extend(verify_canary_automation_active(runtime_snapshot.auto_actions))
        issues.extend(_validate_semantic_auto_reply_scope(runtime_snapshot.auto_actions))
        issues.extend(_validate_handoff_disabled(tenant_id, tenant_settings))
        issues.extend(_validate_integration_scope(row))

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
        "lead_representation": CANARY_AUTO_ACTIONS.get("lead"),
    }
    return issues, matrix


def build_automatic_campaign_readiness_gates(
    *,
    automation_phase: str | None,
    tenant_id: str = LIVE_EVAL_TENANT_ID,
    campaign_type: str,
    selected_scenario_ids: tuple[str, ...] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Entry point for automatic-gmail-canary automation gates."""
    if campaign_type != AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE:
        return [], {}
    phase = resolve_automation_phase(automation_phase)
    if phase is None:
        return [
            f"{PHASE_MISMATCH_ERROR}: automation_phase is required for "
            f"{AUTOMATIC_GMAIL_CANARY_CAMPAIGN_TYPE}"
        ], {}
    issues, matrix = validate_automatic_automation_readiness(
        automation_phase=phase,
        tenant_id=tenant_id,
    )
    if phase in (AUTOMATION_PHASE_PRE_SEED, AUTOMATION_PHASE_ACTIVE_CANARY):
        bundle_issues, bundle_matrix = validate_automatic_fixture_bundle_completeness(
            selected_scenario_ids=selected_scenario_ids,
        )
        issues.extend(bundle_issues)
        matrix["fixture_bundle_completeness"] = bundle_matrix
    return issues, matrix
