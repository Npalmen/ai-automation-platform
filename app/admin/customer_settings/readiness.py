"""Effective readiness for active customer settings (read-only aggregate GET)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.admin.customer_settings.automation_projection import (
    AutomationProjectionError,
    compute_automation_runtime_projection,
)
from app.admin.customer_settings.domains import READINESS_DOMAINS_BY_SETTINGS_DOMAIN
from app.admin.customer_settings.validation import (
    integrations_draft_from_tenant,
    modules_draft_from_tenant,
)
from app.admin.integrations.selection_resolver import (
    _has_tenant_credential,
    _has_verified_config,
    derive_integration_selection,
)
from app.admin.onboarding.integration_groups import (
    build_finance_destination_status,
    evaluate_required_integration_groups,
    module_required_canonical_keys,
)
from app.admin.onboarding.registries import PRODUCT_CAPABILITIES, preset_snapshot, resolve_preset
from app.admin.onboarding.runtime_evaluation import evaluate_all_runtime_requirements
from app.repositories.postgres.tenant_config_models import TenantConfigRecord

_SETTINGS_DOMAIN_BY_READINESS_DOMAIN = {
    readiness_domain: settings_domain
    for settings_domain, readiness_domains in READINESS_DOMAINS_BY_SETTINGS_DOMAIN.items()
    for readiness_domain in readiness_domains
}


def _readiness_meta(settings: dict[str, Any]) -> dict[str, Any]:
    meta = settings.get("_readiness")
    return dict(meta) if isinstance(meta, dict) else {}


def _stale_domains(record: TenantConfigRecord) -> list[str]:
    settings = record.settings or {}
    is_stale = (
        record.readiness_config_version is not None
        and int(record.readiness_config_version) != int(record.config_version or 1)
    )
    if not is_stale:
        return []
    stored = _readiness_meta(settings).get("stale_domains") or []
    if stored:
        return sorted({str(item) for item in stored})
    return sorted(_SETTINGS_DOMAIN_BY_READINESS_DOMAIN.keys())


def mark_readiness_stale_domains(settings: dict[str, Any], domains: list[str]) -> dict[str, Any]:
    merged = dict(settings or {})
    meta = _readiness_meta(merged)
    existing = set(meta.get("stale_domains") or [])
    existing.update(domains)
    meta["stale_domains"] = sorted(existing)
    merged["_readiness"] = meta
    return merged


def _blocker(
    *,
    blocker_id: str,
    message: str,
    domain: str,
    group_key: str | None = None,
) -> dict[str, Any]:
    return {
        "id": blocker_id,
        "message": message,
        "domain": domain,
        "group_key": group_key,
    }


def _warning(
    *,
    warning_id: str,
    message: str,
    domain: str,
) -> dict[str, Any]:
    return {
        "id": warning_id,
        "message": message,
        "domain": domain,
    }


def _runtime_snapshot(settings: dict[str, Any], capability_keys: list[str]) -> dict[str, Any]:
    try:
        projection = compute_automation_runtime_projection(
            settings,
            capability_keys=capability_keys,
        )
    except AutomationProjectionError:
        return {}
    automation = settings.get("automation") or {}
    preset_key = automation.get("preset_key")
    if not preset_key and automation.get("approval_first"):
        preset_key = "approval_first"
    preset_version = int(automation.get("preset_version") or 1)
    preset = resolve_preset(str(preset_key or ""), preset_version) if preset_key else None
    if preset is None:
        return {
            "auto_actions": projection.get("auto_actions") or {},
            "automation_flags": projection.get("automation_flags") or {},
        }
    snapshot = preset_snapshot(preset)
    snapshot["auto_actions"] = projection.get("auto_actions") or {}
    snapshot["automation_flags"] = projection.get("automation_flags") or {}
    return snapshot


def _affected_capabilities(capability_keys: list[str], blockers: list[dict[str, Any]]) -> list[str]:
    if not blockers:
        return []
    blocker_domains = {item.get("domain") for item in blockers}
    affected: list[str] = []
    for key in capability_keys:
        cap = PRODUCT_CAPABILITIES.get(key)
        if not cap:
            continue
        if "modules" in blocker_domains or "integrations" in blocker_domains:
            if cap.required_integration_groups or cap.required_integrations:
                affected.append(key)
                continue
        if "routing" in blocker_domains and "invoice_handling" == key:
            affected.append(key)
            continue
        if "automation" in blocker_domains:
            affected.append(key)
    return sorted(set(affected))


def compute_customer_settings_readiness(
    db: Session,
    record: TenantConfigRecord,
) -> dict[str, Any]:
    """Read-only readiness view for active tenant settings."""
    settings = record.settings or {}
    modules = modules_draft_from_tenant(record)
    capability_keys = list(modules.get("capabilities") or [])
    memory = settings.get("memory") or {}
    routing = settings.get("routing") or {}
    integrations_draft = integrations_draft_from_tenant(settings)

    is_stale = (
        record.readiness_config_version is not None
        and int(record.readiness_config_version) != int(record.config_version or 1)
    )
    stale_domains = _stale_domains(record)

    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    if is_stale:
        blockers.append(
            _blocker(
                blocker_id="readiness.stale_config_version",
                message="Readiness är inaktuell efter config-ändring.",
                domain="readiness",
            )
        )

    group_evaluations = evaluate_required_integration_groups(
        capability_keys=capability_keys,
        integrations_draft=integrations_draft,
        modules_draft=modules,
        service_profile_draft=memory.get("service_profile"),
        routing_draft=routing,
    )
    finance_status = build_finance_destination_status(
        draft=integrations_draft,
        modules_draft=modules,
        service_profile_draft=memory.get("service_profile"),
        routing_draft=routing,
        tenant_id=record.tenant_id,
    )
    group_status = {
        "groups": [
            {
                "group_key": ev.group_key,
                "satisfied": ev.satisfied,
                "implementation": ev.implementation,
                "reason": ev.reason,
            }
            for ev in group_evaluations
        ],
        "finance_destination": finance_status,
    }

    for evaluation in group_evaluations:
        if evaluation.satisfied:
            continue
        domain = "routing" if evaluation.reason == "manual_accounting_routing_missing_routing" else "integrations"
        blockers.append(
            _blocker(
                blocker_id=f"integration_group.{evaluation.group_key}.{evaluation.reason}",
                message=f"Integrationsgrupp '{evaluation.group_key}' är inte uppfylld ({evaluation.reason}).",
                domain=domain,
                group_key=evaluation.group_key,
            )
        )

    if "invoice_handling" in capability_keys and finance_status.get("active_implementation") == "none":
        blockers.append(
            _blocker(
                blocker_id="finance_destination.not_configured",
                message="Ekonomidestination saknas.",
                domain="integrations",
                group_key="finance_destination",
            )
        )

    required_keys = module_required_canonical_keys(capability_keys)
    for canonical in sorted(required_keys):
        derived = derive_integration_selection(db, record, canonical)
        if derived.selection_status != "selected_required":
            continue
        if not (
            _has_tenant_credential(db, record.tenant_id, canonical)
            and _has_verified_config(settings, canonical)
        ):
            blockers.append(
                _blocker(
                    blocker_id=f"integrations.{canonical}.required_not_verified",
                    message=f"Obligatorisk integration '{canonical}' är inte verifierad.",
                    domain="integrations",
                )
            )

    snapshot = _runtime_snapshot(settings, capability_keys)
    automation = settings.get("automation") or {}
    runtime_bundle = evaluate_all_runtime_requirements(
        db,
        capability_keys=capability_keys,
        snapshot=snapshot,
        tenant=record,
        preset_key=automation.get("preset_key"),
        preset_version=int(automation.get("preset_version") or 1)
        if automation.get("preset_version") is not None or automation.get("preset_key")
        else None,
    )
    for item in runtime_bundle.get("readiness_blocking") or []:
        blockers.append(
            _blocker(
                blocker_id=str(item.get("id") or "runtime.blocked"),
                message=str(item.get("message") or "Runtime blocker."),
                domain=str(item.get("step_key") or "automation"),
            )
        )
    for item in runtime_bundle.get("readiness_warnings") or []:
        warnings.append(
            _warning(
                warning_id=str(item.get("id") or "runtime.warning"),
                message=str(item.get("message") or "Runtime varning."),
                domain=str(item.get("step_key") or "automation"),
            )
        )

    blocking_domain = None
    if blockers:
        blocking_domain = str(blockers[0].get("domain") or "integrations")
    action_target = (
        f"/admin/tenants/{record.tenant_id}/settings/{blocking_domain}"
        if blocking_domain and blocking_domain != "readiness"
        else None
    )

    if blockers:
        overall_status = "not_ready"
    elif warnings or runtime_bundle.get("forces_ready_with_warnings"):
        overall_status = "ready_with_warnings"
    else:
        overall_status = "ready"

    return {
        "overall_status": overall_status,
        "is_stale": is_stale,
        "stale_domains": stale_domains,
        "blockers": blockers,
        "warnings": warnings,
        "blocking_domain": blocking_domain,
        "action_target": action_target,
        "integration_group_status": group_status,
        "affected_capabilities": _affected_capabilities(capability_keys, blockers),
    }
